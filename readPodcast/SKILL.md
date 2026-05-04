---
name: read-podcast
description: 从 Podwise 链接提取播客完整内容（summary、transcript、keywords、highlights 等），进行 ASR 语音识别审阅修正，生成结构化笔记并写入 Obsidian vault。当用户分享 podwise.ai 链接、说"帮我整理播客"、"播客笔记"、"读播客"、"/read-podcast"时触发。即使用户只是粘贴了一个 podwise.ai/dashboard/episodes/ 开头的 URL，也应该触发此 skill。
---

# Read Podcast

将 Podwise 播客页面转化为 Obsidian 结构化笔记，包含 ASR 审阅修正。通过 **Dokobot** 的像素级视觉提取读取页面内容（复用已登录的 Chrome，不受虚拟滚动/懒加载影响）。

## 关键背景(必读)

Podwise 的 Episode 页面是**单 URL 多 Tab**：顶部有 `Summary / Transcript / Mindmap / Keywords / Highlights / Showcase` 等 tab，切 tab **URL 不变**，`?tab=xxx` 参数不生效，`/transcript` 等路径返回 404。Dokobot CLI 只能 `read`，不能程序化 `click`。所以：

- **Tab 切换必须由用户手工完成**，然后用 `--reuse-tab` 读取当前可见 tab 的内容
- **Transcript 页面是多栏布局**(主文字区 + 左侧 Outline 章节栏 + 浮层 Takeaways/Q&A/Paywall)，Dokobot 把它们全部视觉铺平，输出里逐字稿与侧栏交织。必须用解析脚本分离
- **免费层有 paywall**: 输出中出现 `Access AI Contents / 4 episodes per month for free / Subscribe` 说明当前账号是免费用户，此时 transcript 可能只能显示前面几分钟(上方几个 entry)。如遇此情况应提示用户升级或换账号

## 前置条件

- Dokobot CLI 已安装：`npm install -g @dokobot/cli`；`dokobot install-bridge` 启用本地模式
- 可用 `dokobot doko list` 确认至少有一个本地设备在线
- Chrome 已装 Dokobot 扩展，且**已登录 Podwise**(复用登录态，付费账号才能拿完整 transcript)
- Obsidian 打开，官方 CLI 路径：`/Applications/Obsidian.app/Contents/MacOS/obsidian-cli`
- 本 skill 目录下的 `parse_podwise_transcript.py` 脚本可用

## 输出规格

- 目标 vault：`obsidian-vault`
- 目标目录：`podcasts/`
- 文件名格式：`YYYY-MM-DD 播客标题.md`
- 内容板块(按顺序)：frontmatter → 摘要 → 核心要点 → 思维导图(若有) → 关键词(若有) → 金句摘录(若有) → 章节概要 → Q&A → ASR 审阅记录 → 逐字稿

## 工作流

### Step 1: 读取默认 Tab (Summary) —— 一次性收齐结构化 AI 产物

Podwise 的默认 tab 是 "AI Note"，**一次 `dokobot read` 就能拿到**：Summary、Takeaways、Outline(章节+时间戳)、Q&A 等所有 AI 总结内容。

```bash
dokobot read '<podwise-url>' \
  --local \
  --screens 20 \
  --timeout 180 \
  -o /tmp/podwise-summary.txt
```

大部分集 20 屏足够(页面包括 Summary / Takeaways / Outline / 9–10 个 Q&A / Related Episodes)。读完从中提取节目元信息(标题/节目名/日期/时长)与 Summary/Takeaways/Outline/Q&A。

### Step 2: 让用户在 Chrome 里切到 Transcript Tab

直接告诉用户：

> 请在 Chrome 里的 Podwise 页面上点一下顶部的 **Transcript** tab，确认逐字稿已经显示出来(带时间戳 + Speaker 标记)，然后告诉我"好了"。

**不要尝试** `<url>/transcript`、`<url>?tab=transcript`、`<url>#transcript` —— 亲测无效。

### Step 3: 用 `--reuse-tab` 读当前 Tab 的 Transcript

用户切好后，用 `--reuse-tab` 读取**浏览器当前 tab**(不会再开新 tab、URL 可与之前相同)：

```bash
dokobot read '<podwise-url>' \
  --local \
  --reuse-tab \
  --screens 30 \
  --timeout 300 \
  -o /tmp/podwise-transcript-raw.txt
```

`--timeout 300` 是必要的：长播客 + 逐字稿自动滚动很耗时。

若一屏不够(输出尾部不是 Related Episodes / 没看到与节目时长匹配的最后时间戳)，按原 `--session-id` 续读。

### Step 4: 用解析器清洗出纯逐字稿

原始输出里逐字稿与 Outline 章节、Takeaways 句子、Q&A、Paywall 浮层等侧栏内容**视觉交织**，不能直接用。调用本 skill 目录下的解析器：

```bash
python3 /Users/hejj/.claude/skills/read-podcast/parse_podwise_transcript.py \
  /tmp/podwise-transcript-raw.txt \
  /tmp/podwise-transcript-clean.md
```

脚本做的事：
1. 扫描全部"纯时间戳"行(`MM:SS` / `H:MM:SS`)
2. 贪心保留**主时间线上严格递增**的时间戳(把 Outline 侧栏里反复穿插的小时间戳过滤掉)
3. 每个时间戳后收集 Speaker N / 说话人姓名 / 长度 ≥ 20 的正文段落
4. 跳过已知侧栏特征:Q:/A:、`**粗体**`、`[Column N]`、`[1] https://...`、Subscribe、Paywall、Outlines/Takeaways/Related Episodes 标题等

**验收检查**:
- 第一条时间戳接近 `00:00:xx`(而非 `10:11` 这种章节跳转)
- 最后一条时间戳接近节目时长
- 条目数与 Outline 章节数量级一致(一集 1h 通常 40–80 条)
- 如果条目很少(<10)或最后时间戳只到几分钟,说明 Paywall 触发,需要提示用户

### Step 5: ASR 审阅修正

对清洗后的 transcript 文本进行语音识别错误检查。常见错误模式：

- 同音字错误(如"逐字稿"→"竹子稿"、"余额宝"→"鱼蛾堡"、"语言及世界"↔"语言即世界")
- 专有名词识别错误(App 名、人名、模型名,如"Cloud Code"→"Claude Code"、"Opus"误为"Ops")
- 语境不符用字("矛"→"毛"、"背会"→"备会")

审阅流程:
1. 根据播客主题(科技/财经/生活等)建立可能的专有名词列表
2. 扫描全文,标记疑似 ASR 错误
3. 自动修正明确错误,记录修正表
4. **说话人映射**: 根据上下文把 "Speaker 1"/"Speaker 2" 映射为实际人名(通常 Speaker 1 是主持人,Speaker 2 是嘉宾)。在解析器的 `KNOWN_SPEAKERS` 集合里追加后可让脚本直接识别

输出审阅记录表：

```markdown
| 时间 | 原文 | 修正 | 说明 |
|------|------|------|------|
| 00:01:19 | 竹子稿 | 逐字稿 | ASR 同音错误 |
| 00:05:22 | Cloud Code | Claude Code | 专有名词 |
```

### Step 6: 生成 Markdown 并写入 Obsidian

```bash
OBS=/Applications/Obsidian.app/Contents/MacOS/obsidian-cli

# 1. 创建文件(含 frontmatter + 标题)
$OBS vault="obsidian-vault" create \
  name="podcasts/YYYY-MM-DD 播客标题" \
  content="---\ntitle: ...\n---\n\n# 标题" \
  silent

# 2. 逐段 append 各板块: Summary / Takeaways / Outline / Q&A / ASR表 / Transcript
$OBS vault="obsidian-vault" append \
  path="podcasts/YYYY-MM-DD 播客标题.md" \
  content="..."

# 3. 逐字稿分批 append,每批 ~3000 字符(CLI content 参数有长度限制)
```

### Step 7: 清理

```bash
dokobot doko close <SESSION_ID>    # 若有 sessionId
rm -f /tmp/podwise-summary.txt /tmp/podwise-transcript-raw.txt /tmp/podwise-transcript-clean.md
```

## Frontmatter 模板

```yaml
---
title: "播客标题"
podcast: 播客节目名
episode: 集数
date: YYYY-MM-DD
duration: "Xh Ym"
host: 主持人
guest: 嘉宾
source: https://podwise.ai/dashboard/episodes/xxx
tags:
  - podcast
  - 根据内容添加相关标签
---
```

## 逐字稿格式

```markdown
**[HH:MM:SS] 说话人**

段落文本（已修正 ASR 错误）
```

合并同一说话人的连续片段为一个段落，避免碎片化。

## 教训 & 注意事项

### Dokobot 使用

- **永远加 `--local`**: 免费无限,不走网络,Podwise 登录态在本地 Chrome 里
- **永远加 `-o <file>`**: 逐字稿内容庞大,禁止直接让 stdout 污染对话上下文
- **永远加 `--timeout 180` 以上**: 默认 60 秒对长页面自动滚动不够用,Transcript 页建议 300
- **Transcript tab 必须 `--reuse-tab`**: Podwise tab 状态在客户端,只有用 `--reuse-tab` 读取用户手动切换后的 tab 才能拿到

### Podwise 结构陷阱

- 一页多 tab,切 tab URL 不变 —— 不要试 `/transcript`、`?tab=transcript` 这类推测路径(实测都无效)
- Transcript 页面是多栏布局,Dokobot 视觉提取会把**章节目录、Takeaways、Q&A 面板、Paywall 浮层**与主文字区一起铺平输出,**必须**用 `parse_podwise_transcript.py` 清洗
- 免费层每月只能看 4 集完整内容,输出中出现 `Access AI Contents / Subscribe` 且逐字稿被截断时,应提示用户

### 其它

- 不要再用 bb-browser / curl localhost:19824 / `performance.getEntriesByType` 这套旧路径,本 skill 已完全迁移到 Dokobot
- 不要用 npm 的 `obsidian` 命令(需要 API key),用 `/Applications/Obsidian.app/Contents/MacOS/obsidian-cli`
- 写入前确保 `podcasts/` 目录存在(`obsidian-cli create` 会自动创建)
- 解析器里 `KNOWN_SPEAKERS` 默认含"张小珺"、"广密",换别的播客要扩展

## 故障排查

| 症状 | 处理 |
|------|------|
| `503 No extension connected` | 检查 Chrome 是否打开,扩展是否在线;`dokobot doko list` 查看本地设备 |
| `504 Timed out` | 加大 `--timeout`,或降低 `--screens`、用 `--session-id` 续读 |
| 逐字稿只到几分钟 / 出现 Subscribe | Paywall 触发,当前账号免费额度用尽,换账号或升级 |
| 清洗后条目数过少 | 检查原始输出是否真的切到了 Transcript tab(默认 AI Note tab 里没有逐字稿) |
| 清洗后有重复段落 | 解析器的"主时间线严格递增"策略对少数集可能偏保守,可放宽为 `>=` 或调大段落长度阈值 |
| Dokobot 版本老旧 | `dokobot --version`,必要时 `dokobot update` |

## 相关文件

- `parse_podwise_transcript.py` —— Transcript 清洗脚本(用法见 Step 4)
