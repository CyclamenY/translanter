"""步骤 1 转写（stable-ts 版）：faster-whisper + 静音抑制的词时间戳精炼。

解决 whisper-ctranslate2 原生 DTW 词时间戳的随机抖动问题：
stable-ts 用波形幅度检测静音段，把词边界重新锁到真实语音边缘，
显著降低 CUDA/float16 下词级时间戳的 ±0.1~0.5s 随机偏移。

用法（bash，CUDA DLL 与 HF 缓存约定同主工作流）：
  export HF_HOME="$PWD/.cache/huggingface"
  export PATH="$PWD/tools/cuda-libs:$PATH"
  venv/Scripts/python tools/transcribe_stable.py <视频文件> \
      --language <语种代码> --output-dir out/<视频名>

默认参数为 issue #19 四素材 A/B 实测定值：beam_size 8 / patience 2，
vad_filter 开启（threshold 0.3 / pad 400ms / min_silence 1000ms），
stable-ts 掩码 vad_threshold 0.2 / min_silence_dur 0.15，no_speech_threshold 0.7。
可选：--initial-prompt "<作品/人名/术语上下文>" 显著降低专名错听。
所有开关可回退旧值（--beam-size 5 --no-vad-filter 等）。

参数解析优先级：命令行显式值 > LANG_PRESETS 语种预设 > GLOBAL_DEFAULTS 全局默认。
LANG_PRESETS 目前为空：issue #19 实测同一组参数在日/中/英均为净收益，
暂无按语种分化的依据；某语种实测出问题后在此表中覆盖对应键即可。

产物（与 whisper-ctranslate2 --output_format all --pretty_json True 兼容）：
  <output-dir>/source.srt   原文字幕
  <output-dir>/source.json  词级时间戳（步骤 2 断句重组的真源）
"""

import argparse
import json
import os

import stable_whisper

# 全局默认（issue #19 四素材 A/B 实测定值）
GLOBAL_DEFAULTS = dict(
    beam_size=8, patience=2.0,
    vad_filter=True, vad_fw_threshold=0.3, speech_pad_ms=400, fw_min_silence_ms=1000,
    vad_threshold=0.2, min_silence_dur=0.15, min_word_dur=None, no_speech_threshold=0.7,
    only_voice_freq=False, denoiser=None,
)

# 语种预设：键 = faster-whisper 语种代码，值 = 需要偏离全局默认的键子集。
# 仅在有实测依据时添加（参考 issue #19 的 A/B 方法论）。
LANG_PRESETS = {
    # 'yue': {'vad_fw_threshold': 0.25},   # 示例：粤语轻声助词多，可实测后放宽阈值
}


def resolve_config(args):
    """命令行显式值 > 语种预设 > 全局默认。"""
    preset = LANG_PRESETS.get(args.language, {})
    cfg, sources = {}, {}
    for key, default in GLOBAL_DEFAULTS.items():
        cli_val = getattr(args, key)
        if cli_val is not None:
            cfg[key], sources[key] = cli_val, 'cli'
        elif key in preset:
            cfg[key], sources[key] = preset[key], f'preset:{args.language}'
        else:
            cfg[key], sources[key] = default, 'default'
    return cfg, sources


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('media', help='视频/音频文件路径')
    p.add_argument('--language', required=True, help='语种代码，如 en / zh / ja（显式指定，不做自动检测）')
    p.add_argument('--output-dir', required=True)
    p.add_argument('--model', default='large-v3')
    p.add_argument('--device', default='cuda')
    p.add_argument('--compute-type', default='float16')

    # ── 档位 1：解码侧（治错听）────────────────────────────
    p.add_argument('--beam-size', type=int, default=None, help='beam search 宽度（全局默认 8，issue #19 实测定值）')
    p.add_argument('--patience', type=float, default=None, help='beam search patience（全局默认 2，issue #19 实测定值）')
    p.add_argument('--initial-prompt', default=None,
                   help='每个解码窗口的 prompt：术语表/人名/作品名，直接降低专有名词错听')
    p.add_argument('--hotwords', default=None, help='ctranslate2 层词汇加权，逗号分隔')

    # ── 档位 2：VAD 与切分（治漏听）────────────────────────
    p.add_argument('--vad-filter', dest='vad_filter', action='store_true', default=None,
                   help='开启 faster-whisper 解码前 VAD 预过滤（全局默认开）')
    p.add_argument('--no-vad-filter', dest='vad_filter', action='store_false',
                   help='关闭解码前 VAD 预过滤（回退旧行为）')
    p.add_argument('--vad-fw-threshold', type=float, default=None,
                   help='vad_filter 的 silero 语音阈值（全局默认 0.3）')
    p.add_argument('--speech-pad-ms', type=int, default=None, help='vad_filter 语音段两侧 padding（全局默认 400ms）')
    p.add_argument('--fw-min-silence-ms', type=int, default=None,
                   help='vad_filter 判定段间静默的最小时长（全局默认 1000ms）')
    p.add_argument('--vad-threshold', type=float, default=None,
                   help='stable-ts 词边界精修掩码的 VAD 阈值（全局默认 0.2）')
    p.add_argument('--min-silence-dur', type=float, default=None,
                   help='词边界精修允许的最短静音秒数（全局默认 0.15）')
    p.add_argument('--min-word-dur', type=float, default=None, help='静音抑制下每个词的最短时长（默认 0.1s）')
    p.add_argument('--no-speech-threshold', type=float, default=None,
                   help='非语音概率阈值（全局默认 0.7）')

    # ── 档位 3：预处理（BGM/噪声重素材按需启用）────────────
    p.add_argument('--only-voice-freq', action='store_true', default=None, help='只保留 200–5000Hz 人声频段（近零成本削 BGM）')
    p.add_argument('--denoiser', default=None, choices=['demucs', 'dfnet'],
                   help='人声分离/降噪预处理（demucs 明显变慢，仅 BGM 重素材启用）')
    args = p.parse_args()

    cfg, sources = resolve_config(args)

    model = stable_whisper.load_faster_whisper(
        args.model, device=args.device, compute_type=args.compute_type,
    )
    transcribe_kwargs = dict(
        language=args.language,
        vad=True,                       # silero VAD（stable-ts 自己的实现，仅用于词边界精修掩码）
        vad_threshold=cfg['vad_threshold'],
        suppress_silence=True,          # 核心：检测静音并重锁词边界
        suppress_word_ts=True,
        use_word_position=True,
        regroup=False,                  # 分段重组由下游步骤 2 负责，保留原始分段
        condition_on_previous_text=False,
        hallucination_silence_threshold=2,
        verbose=False,
        beam_size=cfg['beam_size'],
        patience=cfg['patience'],
        initial_prompt=args.initial_prompt,
        hotwords=args.hotwords,
        no_speech_threshold=cfg['no_speech_threshold'],
        min_word_dur=cfg['min_word_dur'],
        min_silence_dur=cfg['min_silence_dur'],
        only_voice_freq=cfg['only_voice_freq'],
        denoiser=cfg['denoiser'],
    )
    if cfg['vad_filter']:
        transcribe_kwargs['vad_filter'] = True
        transcribe_kwargs['vad_parameters'] = dict(
            threshold=cfg['vad_fw_threshold'],
            speech_pad_ms=cfg['speech_pad_ms'],
            min_silence_duration_ms=cfg['fw_min_silence_ms'],
        )
    result = model.transcribe(args.media, **transcribe_kwargs)

    os.makedirs(args.output_dir, exist_ok=True)
    srt_path = os.path.join(args.output_dir, 'source.srt')
    json_path = os.path.join(args.output_dir, 'source.json')

    result.to_srt_vtt(srt_path, word_level=False)

    # 转成 whisper-ctranslate2 --pretty_json 的兼容结构（下游重组只依赖 segments[].words）
    segments = []
    for i, seg in enumerate(result.segments, start=1):
        d = seg.to_dict()
        segments.append({
            'id': i,
            'seek': 0,
            'start': d['start'],
            'end': d['end'],
            'text': d['text'],
            'tokens': d.get('tokens', []),
            'avg_logprob': d.get('avg_logprob'),
            'compression_ratio': d.get('compression_ratio'),
            'no_speech_prob': d.get('no_speech_prob'),
            'words': [
                {
                    'start': w['start'],
                    'end': w['end'],
                    'word': w['word'],
                    'probability': w.get('probability'),
                }
                for w in d.get('words', [])
            ],
        })
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(
            {'text': result.text, 'segments': segments, 'language': result.language},
            f, ensure_ascii=False, indent=1,
        )

    n_words = sum(len(s['words']) for s in segments)
    print(f'OK: {len(segments)} segments, {n_words} words')

    # 记录本次实际生效的配置（解析后的最终值 + 来源），便于 A/B 实验溯源
    run_meta = {
        'language': args.language,
        'initial_prompt': args.initial_prompt,
        'hotwords': args.hotwords,
        'resolved_config': cfg,
        'config_sources': sources,
    }
    if cfg['vad_filter']:
        run_meta['vad_parameters'] = transcribe_kwargs['vad_parameters']
    meta_path = os.path.join(args.output_dir, 'run_meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(run_meta, f, ensure_ascii=False, indent=1)

    print(f'  {srt_path}')
    print(f'  {json_path}')
    print(f'  {meta_path}')


if __name__ == '__main__':
    main()
