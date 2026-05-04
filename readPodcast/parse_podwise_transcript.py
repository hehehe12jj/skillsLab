#!/usr/bin/env python3
"""
从 Dokobot 抓取的 Podwise Transcript tab 输出中提取纯逐字稿。

背景
----
Podwise 的 Transcript 页面是一个多面板布局：主内容区为带时间戳/说话人的
逐字稿；同页还有 Outline(左侧章节目录)、Takeaways(AI 总结句)、Q & A、
Related Episodes(相关节目侧栏)，以及免费层 Paywall 浮层。Dokobot 是像素级
视觉提取，会把它们视觉顺序地铺平到输出里，逐字稿和侧栏内容高度交织。

本脚本的策略
------------
1. 扫描所有"纯时间戳"行 (MM:SS 或 H:MM:SS)
2. 只保留在主时间线上**严格递增**的时间戳(Outline 侧栏里的 10:11/22:09 等
   反复穿插的会被过滤)
3. 每个时间戳后到下一个时间戳之间,收集:
   - Speaker N (可选)
   - 说话人姓名(可选,"张小珺"/"广密" 等可扩展)
   - 20 字符以上、不匹配已知侧栏特征的段落,视为逐字稿文本
4. 侧栏特征:Outline 标题、Q:/A:、Takeaway 句式、订阅/Subscribe、参考链接等

使用
----
    python3 parse_podwise_transcript.py <src.txt> <dst.md>

或直接编辑下方 SRC / OUT 常量。
"""

import re
import sys
from pathlib import Path

# 可通过参数覆盖
DEFAULT_SRC = Path("/tmp/podwise-transcript-1.txt")
DEFAULT_OUT = Path("/tmp/podwise-transcript-clean.md")

# 已知的侧栏/Outline 固定标题 —— 根据当前集的 Outline 章节补充
# (可在调用处扩展,或在运行后人工检查输出后回填)
SIDEBAR_EXACT = {
    "Outlines", "Q & A", "Takeaways", "Related Episodes",
    "Access AI Contents", "Accessing...", "Loading...",
    "Get unlimited access:",
}

SIDEBAR_PREFIX = (
    "Q:", "A:",                      # Q & A 区
    "**",                             # Markdown 粗体包裹的侧栏小标题
    "Subscribe",
    "4 episodes", "2 episodes",      # Paywall 浮层
    "Prev ", "Next ",
    "Episode cover", "Podcast cover",
    "[Column",                        # Dokobot 多列标识
)

# 时间戳: MM:SS 或 H:MM:SS 或 HH:MM:SS
TS_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
# 参考链接行: [1] https://...
REF_RE = re.compile(r"^\[\d+\]\s+https?://")
# 章节目录条目(含时间戳前缀): "33:34 OpenAI与Google在Coding赛道的战略"
OUTLINE_TS_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?\s+\S+")

# 可选:已知说话人姓名 —— 建议调用方根据 metadata 传入
KNOWN_SPEAKERS = {"张小珺", "广密"}


def is_sidebar_noise(s: str) -> bool:
    t = s.strip()
    if not t or t in ("---",):
        return True
    if t in SIDEBAR_EXACT:
        return True
    for p in SIDEBAR_PREFIX:
        if t.startswith(p):
            return True
    if REF_RE.match(t) or OUTLINE_TS_RE.match(t):
        return True
    return False


def ts_to_seconds(h: int, m: int, s: int) -> int:
    return h * 3600 + m * 60 + s


def fmt_hms(total: int) -> str:
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse(src: Path, out: Path) -> int:
    lines = src.read_text(encoding="utf-8").splitlines()

    # 1. 收集所有时间戳行
    ts_positions = []
    for i, raw in enumerate(lines):
        t = raw.strip()
        m = TS_RE.fullmatch(t)
        if not m:
            continue
        h, mm, ss = m.groups()
        sec = (ts_to_seconds(int(h), int(mm), int(ss)) if ss is not None
               else ts_to_seconds(0, int(h), int(mm)))
        ts_positions.append((i, sec))

    # 2. 贪心过滤出主时间线(严格递增)
    main_seq = []
    last = -1
    for i, sec in ts_positions:
        if sec > last:
            main_seq.append((i, sec))
            last = sec

    # 3. 提取每段
    entries = []
    for idx, (line_i, sec) in enumerate(main_seq):
        end = main_seq[idx + 1][0] if idx + 1 < len(main_seq) else len(lines)
        segment = lines[line_i + 1:end]

        speaker_label = None
        speaker_name = None
        paragraph_parts = []
        for raw in segment:
            t = raw.strip()
            if not t or t == "---":
                continue
            if re.fullmatch(r"Speaker \d+", t):
                speaker_label = t
                continue
            if t in KNOWN_SPEAKERS:
                speaker_name = t
                continue
            if is_sidebar_noise(t):
                continue
            if TS_RE.fullmatch(t):
                continue
            # >=20 字算有效段落(过滤短的 Outline 标题残片)
            if len(t) >= 20:
                paragraph_parts.append(t)

        if not paragraph_parts:
            continue
        entries.append({
            "ts": fmt_hms(sec),
            "speaker": speaker_name or speaker_label or "",
            "text": "\n\n".join(paragraph_parts),
        })

    # 4. 写 Markdown
    lines_out = []
    for e in entries:
        head = f"**[{e['ts']}]"
        if e["speaker"]:
            head += f" {e['speaker']}"
        head += "**"
        lines_out.append(f"{head}\n\n{e['text']}\n")

    out.write_text("\n".join(lines_out), encoding="utf-8")
    return len(entries)


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    n = parse(src, out)
    print(f"[parse_podwise_transcript] Wrote {n} entries to {out}")


if __name__ == "__main__":
    main()
