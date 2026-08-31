"""对比火山在线 ASR 输出与本地链 baseline，产出四维度指标与准确率裁决清单。

用法: python tools/asr_compare.py --lang zh --volc out-asr-test/zh/volc.srt --baseline "out/华为麒麟9050怎么样/resegmented.srt" --out out-asr-test/zh
"""
import argparse
import difflib
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRT_BLOCK = re.compile(r"(\d+)\n(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})\n(.*?)(?=\n\n|\Z)", re.S)
SENT_END = re.compile(r"[。！？!?…]+[」』）)\"']*$|[.!?]+[)\"']*$")


def parse_srt(path: str):
    text = open(path, encoding="utf-8").read()
    entries = []
    for m in SRT_BLOCK.finditer(text):
        g = m.groups()
        start = int(g[1]) * 3600 + int(g[2]) * 60 + int(g[3]) + int(g[4]) / 1000
        end = int(g[5]) * 3600 + int(g[6]) * 60 + int(g[7]) + int(g[8]) / 1000
        entries.append({"start": start, "end": end, "text": g[9].strip()})
    return entries


def normalize(text: str, lang: str) -> str:
    t = re.sub(r"[\s，。、！？,.!?…・「」『』\"''()（）—\-]+", "", text)
    return t.lower() if lang == "en" else t


def seg_metrics(entries):
    durs = [e["end"] - e["start"] for e in entries]
    sent_ok = sum(1 for e in entries if SENT_END.search(e["text"]))
    return {
        "条目数": len(entries),
        "平均条长s": round(sum(durs) / len(durs), 2) if durs else 0,
        "最长条s": round(max(durs), 2) if durs else 0,
        "超12s条数": sum(1 for d in durs if d > 12),
        "整句率%": round(100 * sent_ok / len(entries), 1) if entries else 0,
    }


def boundary_alignment(volc, base):
    base_ends = sorted(e["end"] for e in base)
    import bisect
    offsets = []
    for e in volc:
        i = bisect.bisect_left(base_ends, e["end"])
        cand = [abs(e["end"] - base_ends[j]) for j in (i - 1, i) if 0 <= j < len(base_ends)]
        if cand:
            offsets.append(min(cand))
    offsets.sort()
    med = offsets[len(offsets) // 2] if offsets else 0
    return {
        "边界中位偏差s": round(med, 2),
        "边界1s内命中%": round(100 * sum(1 for o in offsets if o <= 1.0) / len(offsets), 1) if offsets else 0,
    }


def char_to_time(entries, norm_lens, pos):
    """把归一化文本的字符位置映射回条目时间区间。"""
    acc = 0
    for e, n in zip(entries, norm_lens):
        if pos < acc + n:
            return e
        acc += n
    return entries[-1] if entries else None


def text_diff(volc, base, lang):
    v_texts = [normalize(e["text"], lang) for e in volc]
    b_texts = [normalize(e["text"], lang) for e in base]
    v_full, b_full = "".join(v_texts), "".join(b_texts)
    sm = difflib.SequenceMatcher(None, v_full, b_full, autojunk=False)
    ratio = sm.ratio()
    hunks = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        size = max(i2 - i1, j2 - j1)
        hunks.append({
            "type": tag, "size": size,
            "volc_text": v_full[i1:i2], "base_text": b_full[j1:j2],
            "volc_pos": (i1 + i2) // 2, "base_pos": (j1 + j2) // 2,
        })
    # 大差异优先，附时间定位
    hunks.sort(key=lambda h: -h["size"])
    for h in hunks:
        ve = char_to_time(volc, [len(t) for t in v_texts], h["volc_pos"])
        be = char_to_time(base, [len(t) for t in b_texts], h["base_pos"])
        h["volc_time"] = f"{ve['start']:.1f}-{ve['end']:.1f}s" if ve else "?"
        h["base_time"] = f"{be['start']:.1f}-{be['end']:.1f}s" if be else "?"
        del h["volc_pos"], h["base_pos"]
    return ratio, hunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True)
    ap.add_argument("--volc", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    volc = parse_srt(args.volc)
    base = parse_srt(args.baseline)

    report = {
        "lang": args.lang,
        "断句指标": {"volc": seg_metrics(volc), "baseline": seg_metrics(base)},
        "边界对齐": boundary_alignment(volc, base),
    }
    ratio, hunks = text_diff(volc, base, args.lang)
    report["文本相似度"] = round(ratio, 4)
    report["差异点总数"] = len(hunks)

    with open(os.path.join(args.out, "compare.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    # 裁决清单：取差异最大的 40 个
    with open(os.path.join(args.out, "diff-adjudication.md"), "w", encoding="utf-8") as f:
        f.write(f"# {args.lang} 准确率差异裁决清单\n\n")
        f.write(f"文本相似度: {ratio:.2%}，差异点 {len(hunks)} 个（按大小排序，取前 40）\n\n")
        f.write("| # | 类型 | volc 时间 | volc 文本 | baseline 时间 | baseline 文本 | 裁决 |\n|---|---|---|---|---|---|---|\n")
        for i, h in enumerate(hunks[:40], 1):
            f.write(f"| {i} | {h['type']} | {h['volc_time']} | {h['volc_text']} | {h['base_time']} | {h['base_text']} | |\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
