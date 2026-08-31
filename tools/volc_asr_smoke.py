"""冒烟测试：火山引擎豆包语音识别大模型 录音文件识别（异步 submit/query）。

用法: VOLCENGINE_ASR_API_KEY=... python tools/volc_asr_smoke.py [音频URL]
默认用一段公开的 16kHz 英文样例。
"""
import json
import os
import sys
import time
import uuid

import requests

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
RESOURCE_ID = "volc.seedasr.auc"

DEFAULT_AUDIO_URL = "https://lf3-static.bytednsdoc.com/obj/eden-cn/lm_hz_ihsph/ljhwZthlaukjlkulzlp/console/bigtts/zh_female_cancan_mars_bigtts.mp3"


def headers(request_id: str, sequence: str = "-1") -> dict:
    return {
        "X-Api-Key": os.environ["VOLCENGINE_ASR_API_KEY"],
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": request_id,
        "X-Api-Sequence": sequence,
        "Content-Type": "application/json",
    }


def main() -> None:
    audio_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_AUDIO_URL
    request_id = str(uuid.uuid4())

    payload = {
        "user": {"uid": "translanter-smoke"},
        "audio": {
            "url": audio_url,
            "format": "mp3",
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,       # 数字规整
            "enable_punc": True,      # 自动标点
            "enable_ddc": False,
            "enable_speaker_info": False,
            "enable_channel_split": False,
            "show_utterances": True,  # 输出句级分段（本项目的核心诉求）
            "vad_segment": False,
            "sensitive_words_filter": "",
        },
    }

    resp = requests.post(SUBMIT_URL, headers=headers(request_id), json=payload, timeout=30)
    print("submit HTTP", resp.status_code)
    print("submit headers:", {k: v for k, v in resp.headers.items() if k.lower().startswith("x-") or k.lower().startswith("x-api")})
    try:
        print("submit body:", json.dumps(resp.json(), ensure_ascii=False)[:500])
    except ValueError:
        print("submit body (raw):", resp.text[:500])
    resp.raise_for_status()

    # 轮询 query
    for attempt in range(1, 13):
        time.sleep(5)
        q = requests.post(QUERY_URL, headers=headers(request_id), json={}, timeout=30)
        try:
            body = q.json()
        except ValueError:
            print(f"query[{attempt}] raw:", q.text[:300])
            continue
        # X-Api-Status-Code 在响应头里标识任务状态
        status = q.headers.get("X-Api-Status-Code", "?")
        message = q.headers.get("X-Api-Message", "")
        print(f"query[{attempt}] status={status} message={message}")
        if status == "20000000":  # 成功
            print(json.dumps(body, ensure_ascii=False, indent=2)[:2000])
            return
        if status not in ("20000001", "20000002"):  # 排队中/处理中
            print("任务失败:", json.dumps(body, ensure_ascii=False)[:500])
            sys.exit(1)
    print("轮询超时")


if __name__ == "__main__":
    main()
