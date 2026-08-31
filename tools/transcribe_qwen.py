"""步骤 1（新链）：转写 —— 阿里云百炼 Qwen3-ASR（qwen-audio-3.0-asr-flash-filetrans）。

替代 faster-whisper + stable-ts 的本地转写，原生输出整句分段（整句率实测 100%），
省掉原步骤 2 的 LLM 断句重组。

用法:
  set DASHSCOPE_API_KEY=...  （或 User 级环境变量）
  venv/Scripts/python tools/transcribe_qwen.py <视频/音频文件> --output-dir out/<视频名>

产物（与 transcribe_stable.py 相同的工作区约定）：
  <output-dir>/source.srt    整句化原文字幕（>12s 条目已用词级时间戳机械拆分）
  <output-dir>/source.json   词级时间戳（whisper-ctranslate2 --pretty_json 兼容结构）
  <output-dir>/run_meta.json 本次运行的生效配置

依赖：ffmpeg 在 PATH；tools/cloudflared.exe（公网 URL 中转，--protocol http2）。
"""
import argparse
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL = "qwen-audio-3.0-asr-flash-filetrans"
BASE = "https://ws-nefv2l1h6gqljivb.cn-beijing.maas.aliyuncs.com"
SUBMIT_URL = f"{BASE}/api/v1/services/audio/asr/transcription"
CLOUDFLARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared.exe")
MAX_ENTRY_SECONDS = 12.0  # 超过此长度的句子用词级时间戳机械拆分
MIN_SILENCE_SECONDS = 2.0  # 持续这么久的低振幅区段可作优先切分点
SILENCE_DBFS = -40.0       # 低于此 RMS 电平视为静音
POLL_INTERVAL = 5
POLL_MAX = 480  # 40 分钟封顶（实测 3h 音频约 6.5 分钟）


# ---------- 基础设施 ----------

def extract_audio(video_path: str, out_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", video_path,
         "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", out_path],
        check=True,
    )


def start_server(directory: str) -> tuple:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=directory)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def start_tunnel(port: int) -> tuple:
    """启动 cloudflared 临时隧道，返回 (进程, 公网URL)。TUN 代理环境下必须用 http2。"""
    proc = subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--url", f"http://localhost:{port}",
         "--no-autoupdate", "--protocol", "http2"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    url = None
    deadline = time.time() + 90
    for line in proc.stdout:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            url = m.group(0)
            break
        if time.time() > deadline:
            break
    if not url:
        proc.kill()
        raise RuntimeError("cloudflared 隧道 90s 内未就绪")
    # 等边缘侧生效
    for _ in range(12):
        try:
            if requests.head(url, timeout=10).status_code != 530:
                break
        except requests.RequestException:
            pass
        time.sleep(5)
    return proc, url


# ---------- DashScope ----------

def auth() -> dict:
    return {"Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}"}


def transcribe(file_url: str) -> dict:
    resp = requests.post(
        SUBMIT_URL,
        headers={**auth(), "Content-Type": "application/json", "X-DashScope-Async": "enable"},
        json={"model": MODEL, "input": {"file_urls": [file_url]}, "parameters": {"channel_id": [0]}},
        timeout=60,
    )
    resp.raise_for_status()
    task_id = resp.json()["output"]["task_id"]
    print(f"任务已提交: {task_id}")

    for attempt in range(1, POLL_MAX + 1):
        time.sleep(POLL_INTERVAL)
        q = requests.get(f"{BASE}/api/v1/tasks/{task_id}", headers=auth(), timeout=60)
        body = q.json()
        status = body.get("output", {}).get("task_status", "?")
        if status == "SUCCEEDED":
            result_url = body["output"]["transcription_url"]
            break
        if status not in ("PENDING", "RUNNING"):
            raise RuntimeError(f"任务失败: {json.dumps(body, ensure_ascii=False)[:500]}")
        if attempt % 12 == 0:
            print(f"{status}… {attempt * POLL_INTERVAL}s")
    else:
        raise RuntimeError("轮询超时")

    for i in range(6):  # 结果下载偶发 DNS 抽风，重试
        try:
            return requests.get(result_url, timeout=180).json()
        except requests.exceptions.ConnectionError:
            print(f"结果下载失败({i + 1}/6)，5s 后重试")
            time.sleep(5)
    raise RuntimeError(f"结果下载多次失败，签名 URL（有效期内可手动拉取）: {result_url}")


# ---------- 转换与拆分 ----------

def compute_silences(audio_path: str) -> list:
    """解码音频算 100ms 粒度 RMS 包络，返回持续 >= MIN_SILENCE_SECONDS 且电平低于 SILENCE_DBFS 的静音段 [(start_s, end_s)]。"""
    import numpy as np

    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", audio_path, "-f", "f32le", "-acodec", "pcm_f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    samples = np.frombuffer(pcm, dtype=np.float32)
    if len(samples) == 0:
        return []
    win = 1600  # 100ms @16k
    n = len(samples) // win
    rms = np.sqrt(np.mean(samples[: n * win].reshape(n, win) ** 2, axis=1))
    floor = 10 ** (SILENCE_DBFS / 20)
    silent = rms < floor

    silences, start = [], None
    for i, s in enumerate(silent):
        if s and start is None:
            start = i
        elif not s and start is not None:
            if (i - start) * 0.1 >= MIN_SILENCE_SECONDS:
                silences.append((start * 0.1, i * 0.1))
            start = None
    if start is not None and (n - start) * 0.1 >= MIN_SILENCE_SECONDS:
        silences.append((start * 0.1, n * 0.1))
    return silences


def normalize(text: str) -> str:
    return re.sub(r"[\s，。、！？,.!?…・「」『』\"''()（）—\-]+", "", text).lower()


def word_text(word: dict) -> str:
    return word["text"] + word.get("punctuation", "")


def join_words(chunk: list) -> str:
    """词流重建文本：仅相邻两个拉丁词之间补空格，其余直接相连；标点贴回前词。"""
    parts = [word_text(w) for w in chunk]
    out = parts[0]
    for prev, cur in zip(parts, parts[1:]):
        if re.search(r"[A-Za-z0-9]$", prev) and re.match(r"^[A-Za-z0-9]", cur):
            out += " " + cur
        else:
            out += cur
    return out


def split_long_sentence(sent: dict, silences: list) -> list:
    """把 >12s 的句子按词边界机械拆分。

    切点优先级：窗口内最后一个 >=2s 静音段（振幅验证过的真实空白）里的词边界 >
    窗口内最大词间停顿。返回句子列表（结构与输入一致）。
    """
    words = sent.get("words", [])
    if not words:
        return [sent]

    # 校验：词流拼回（去标点空白）须等于句文本，否则不动它（宁留长条，不改文本）
    joined = "".join(word_text(w) for w in words)
    if normalize(joined) != normalize(sent["text"]):
        print(f"  警告: 句 {sent.get('sentence_id')} 词流与句文本不一致，保留 {round((sent['end_time']-sent['begin_time'])/1000,1)}s 长条")
        return [sent]

    def pick_cut(cur: list) -> int:
        """在 cur 里选切点（返回后半段的起始下标）。"""
        win_start, win_end = cur[0]["begin_time"] / 1000, cur[-1]["end_time"] / 1000
        # 与窗口有交集的静音段，取最靠后的
        hits = [(s, e) for s, e in silences if e > win_start and s < win_end]
        if hits:
            s, e = hits[-1]
            # 切在静音段起点之前的最后一个词之后（词不落进静音区）
            for i in range(len(cur) - 1, -1, -1):
                if cur[i]["end_time"] / 1000 <= s:
                    if i + 1 < len(cur):
                        return i + 1
                    break
        gaps = [cur[i + 1]["begin_time"] - cur[i]["end_time"] for i in range(len(cur) - 1)]
        return gaps.index(max(gaps)) + 1 if gaps else len(cur)

    chunks, cur = [], [words[0]]
    for w in words[1:]:
        if (w["end_time"] - cur[0]["begin_time"]) / 1000 > MAX_ENTRY_SECONDS:
            cut = pick_cut(cur)
            if cut == len(cur):  # 无更好切点，就在边界切
                chunks.append(cur)
                cur = [w]
            else:
                chunks.append(cur[:cut])
                cur = cur[cut:] + [w]
        else:
            cur.append(w)
    chunks.append(cur)

    out = []
    for chunk in chunks:
        out.append({
            "begin_time": chunk[0]["begin_time"],
            "end_time": chunk[-1]["end_time"],
            "text": join_words(chunk),
            "words": chunk,
        })
    return out


def to_segments(result: dict, silences: list) -> tuple:
    """qwen 响应 → whisper-ctranslate2 pretty_json 兼容 segments（秒）。"""
    sentences = []
    for tr in result.get("transcripts", []):
        sentences.extend(tr.get("sentences", []))
    sentences.sort(key=lambda s: s["begin_time"])

    split_sents, n_long = [], 0
    for s in sentences:
        if (s["end_time"] - s["begin_time"]) / 1000 > MAX_ENTRY_SECONDS:
            n_long += 1
            split_sents.extend(split_long_sentence(s, silences))
        else:
            split_sents.append(s)
    if n_long:
        print(f"超长条机械拆分: {n_long} 条")

    segments = []
    for i, s in enumerate(split_sents, 1):
        segments.append({
            "id": i,
            "seek": 0,
            "start": s["begin_time"] / 1000,
            "end": s["end_time"] / 1000,
            "text": s["text"],
            "tokens": [],
            "avg_logprob": None,
            "compression_ratio": None,
            "no_speech_prob": None,
            "words": [
                {
                    "start": w["begin_time"] / 1000,
                    "end": w["end_time"] / 1000,
                    "word": w["text"],
                    "probability": w.get("confidence"),
                }
                for w in s.get("words", [])
            ],
        })
    full_text = "".join(s["text"] for s in split_sents)
    return segments, full_text


def ms_to_srt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def write_srt(segments: list, path: str) -> None:
    blocks = [
        f"{seg['id']}\n{ms_to_srt_ts(seg['start'])} --> {ms_to_srt_ts(seg['end'])}\n{seg['text']}\n"
        for seg in segments
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))


# ---------- 主流程 ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="视频或音频文件路径")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--keep-audio", action="store_true", help="保留提取的 16k 单声道 mp3")
    args = ap.parse_args()

    if "DASHSCOPE_API_KEY" not in os.environ:
        sys.exit("缺少环境变量 DASHSCOPE_API_KEY")
    os.makedirs(args.output_dir, exist_ok=True)

    t0 = time.time()
    tmpdir = tempfile.mkdtemp(prefix="qwen_asr_")
    audio_path = os.path.join(tmpdir, "audio.mp3")
    server, tunnel = None, None
    try:
        print("提取音轨…")
        extract_audio(args.video, audio_path)

        server, port = start_server(tmpdir)
        tunnel, public_url = start_tunnel(port)
        file_url = f"{public_url}/audio.mp3"
        print(f"隧道就绪: {file_url}")

        result = transcribe(file_url)

        print("计算静音段（拆分切点用）…")
        silences = compute_silences(audio_path)
        print(f"检测到 >=2s 静音段 {len(silences)} 处")

        raw_path = os.path.join(args.output_dir, "qwen_raw.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    finally:
        if tunnel:
            tunnel.kill()
        if server:
            server.shutdown()

    segments, full_text = to_segments(result, silences)

    srt_path = os.path.join(args.output_dir, "source.srt")
    json_path = os.path.join(args.output_dir, "source.json")
    meta_path = os.path.join(args.output_dir, "run_meta.json")
    write_srt(segments, srt_path)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"text": full_text, "segments": segments, "language": "auto"},
                  f, ensure_ascii=False, indent=1)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"engine": f"dashscope/{MODEL}", "source": args.video,
                   "max_entry_seconds": MAX_ENTRY_SECONDS}, f, ensure_ascii=False, indent=1)

    if args.keep_audio:
        keep = os.path.join(args.output_dir, "audio.mp3")
        os.replace(audio_path, keep)
        print(f"  {keep}")
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    n_words = sum(len(s["words"]) for s in segments)
    print(f"OK: {len(segments)} segments, {n_words} words, 耗时 {time.time() - t0:.1f}s")
    print(f"  {srt_path}")
    print(f"  {json_path}")
    print(f"  {meta_path}")
    print(f"  {os.path.join(args.output_dir, 'qwen_raw.json')}")


if __name__ == "__main__":
    main()
