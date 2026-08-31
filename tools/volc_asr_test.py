"""火山引擎豆包语音识别大模型（Seed-ASR）录音文件识别测试脚本。

用法:
  VOLCENGINE_ASR_API_KEY=... python tools/volc_asr_test.py --name ja --url https://xxx.trycloudflare.com/ja.mp3 --out out-asr-test/ja

产出:
  <out>/volc_raw.json   API 原始响应（含 utterances + words）
  <out>/volc.srt        由 utterances 直接转换的 SRT（句级分段）
"""
import argparse
import json
import os
import sys
import time
import uuid

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
RESOURCE_ID = "volc.seedasr.auc"


def headers(request_id: str, sequence: str = "-1") -> dict:
    return {
        "X-Api-Key": os.environ["VOLCENGINE_ASR_API_KEY"],
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": request_id,
        "X-Api-Sequence": sequence,
        "Content-Type": "application/json",
    }


def ms_to_srt(ms: int) -> str:
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def utterances_to_srt(utterances: list) -> str:
    blocks = []
    for i, utt in enumerate(utterances, 1):
        blocks.append(
            f"{i}\n{ms_to_srt(utt['start_time'])} --> {ms_to_srt(utt['end_time'])}\n{utt['text']}\n"
        )
    return "\n".join(blocks)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--url", required=True, help="音频的公网 URL")
    ap.add_argument("--lang", default=None, help="语种代码，如 zh-CN/en-US/ja-JP（放在 audio 字段下）")
    ap.add_argument("--out", required=True, help="输出目录")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    request_id = str(uuid.uuid4())
    payload = {
        "user": {"uid": "translanter-asr-test"},
        "audio": {
            "url": args.url,
            "format": "mp3",
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": False,
            "enable_speaker_info": False,
            "enable_channel_split": False,
            "show_utterances": True,
            "vad_segment": False,
            "sensitive_words_filter": "",
        },
    }

    if args.lang:
        payload["audio"]["language"] = args.lang

    t0 = time.time()
    resp = requests.post(SUBMIT_URL, headers=headers(request_id), json=payload, timeout=60)
    print(f"[{args.name}] submit HTTP {resp.status_code} "
          f"status={resp.headers.get('X-Api-Status-Code')} msg={resp.headers.get('X-Api-Message')}")
    resp.raise_for_status()

    result = None
    for attempt in range(1, 121):  # 最多 10 分钟
        time.sleep(5)
        q = requests.post(QUERY_URL, headers=headers(request_id), json={}, timeout=60)
        status = q.headers.get("X-Api-Status-Code", "?")
        if status == "20000000":
            result = q.json()
            break
        if status not in ("20000001", "20000002"):
            print(f"[{args.name}] 任务失败 status={status} body={q.text[:500]}")
            sys.exit(1)
        if attempt % 6 == 0:
            print(f"[{args.name}] 处理中… {attempt * 5}s")
    if result is None:
        print(f"[{args.name}] 轮询超时")
        sys.exit(1)

    elapsed = time.time() - t0
    raw_path = os.path.join(args.out, "volc_raw.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    utterances = result.get("result", {}).get("utterances", [])
    srt_path = os.path.join(args.out, "volc.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(utterances_to_srt(utterances))

    duration_ms = result.get("result", {}).get("additions", {}).get("duration", "?")
    print(f"[{args.name}] 完成: {len(utterances)} 条 utterance, 音频时长 {duration_ms}ms, "
          f"耗时 {elapsed:.1f}s -> {srt_path}")


if __name__ == "__main__":
    main()
