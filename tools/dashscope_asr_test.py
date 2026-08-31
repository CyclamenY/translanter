"""阿里云百炼 Qwen3-ASR（qwen-audio-3.0-asr-flash-filetrans）异步识别测试脚本。

用法:
  DASHSCOPE_API_KEY=... python tools/dashscope_asr_test.py --name ja --url https://xxx/ja.mp3 --out out-asr-test/ja-qwen

产出:
  <out>/qwen_raw.json   识别结果原始 JSON（transcription_url 拉取的内容）
  <out>/qwen.srt        由 sentences 直接转换的 SRT
"""
import argparse
import json
import os
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://ws-nefv2l1h6gqljivb.cn-beijing.maas.aliyuncs.com"
SUBMIT_URL = f"{BASE}/api/v1/services/audio/asr/transcription"
MODEL = "qwen-audio-3.0-asr-flash-filetrans"


def auth() -> dict:
    return {"Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}"}


def ms_to_srt(ms: int) -> str:
    h, rem = divmod(int(ms), 3600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()

    resp = requests.post(
        SUBMIT_URL,
        headers={**auth(), "Content-Type": "application/json", "X-DashScope-Async": "enable"},
        json={"model": MODEL, "input": {"file_urls": [args.url]}, "parameters": {"channel_id": [0]}},
        timeout=60,
    )
    print(f"[{args.name}] submit HTTP {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()
    task_id = resp.json()["output"]["task_id"]

    task = None
    for attempt in range(1, 121):
        time.sleep(5)
        q = requests.get(f"{BASE}/api/v1/tasks/{task_id}", headers=auth(), timeout=60)
        body = q.json()
        status = body.get("output", {}).get("task_status", "?")
        if status == "SUCCEEDED":
            task = body
            break
        if status not in ("PENDING", "RUNNING"):
            print(f"[{args.name}] 任务失败: {json.dumps(body, ensure_ascii=False)[:500]}")
            sys.exit(1)
        if attempt % 6 == 0:
            print(f"[{args.name}] {status}… {attempt * 5}s")
    if task is None:
        print(f"[{args.name}] 轮询超时")
        sys.exit(1)

    transcription_url = task["output"]["transcription_url"]
    result = None
    for dl in range(6):  # 本机 DNS 偶发抽风，重试拉取
        try:
            result = requests.get(transcription_url, timeout=120).json()
            break
        except requests.exceptions.ConnectionError as e:
            print(f"[{args.name}] 结果下载失败({dl + 1}/6): {type(e).__name__}")
            time.sleep(5)
    if result is None:
        print(f"[{args.name}] 结果下载多次失败，签名 URL: {transcription_url}")
        sys.exit(1)
    elapsed = time.time() - t0

    with open(os.path.join(args.out, "qwen_raw.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # transcripts[].sentences[] -> srt
    sentences = []
    for tr in result.get("transcripts", []):
        sentences.extend(tr.get("sentences", []))
    sentences.sort(key=lambda s: s["begin_time"])
    blocks = [
        f"{i}\n{ms_to_srt(s['begin_time'])} --> {ms_to_srt(s['end_time'])}\n{s['text']}\n"
        for i, s in enumerate(sentences, 1)
    ]
    srt_path = os.path.join(args.out, "qwen.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))

    duration_ms = result.get("properties", {}).get("original_duration_in_milliseconds", "?")
    print(f"[{args.name}] 完成: {len(sentences)} 条 sentence, 音频时长 {duration_ms}ms, "
          f"耗时 {elapsed:.1f}s -> {srt_path}")


if __name__ == "__main__":
    main()
