---
name: read-podcast
description: 从 Podwise 链接提取播客完整内容（summary、transcript、keywords、highlights 等），进行 ASR 语音识别审阅修正，生成结构化笔记并写入 Obsidian vault。当用户分享 podwise.ai 链接、说"帮我整理播客"、"播客笔记"、"读播客"、"/read-podcast"时触发。即使用户只是粘贴了一个 podwise.ai/dashboard/episodes/ 开头的 URL，也应该触发此 skill。
---

# Read Podcast

将 Podwise 播客页面转化为 Obsidian 结构化笔记，包含 ASR 审阅修正。

## 前置条件

- bb-browser daemon 已启动，Chrome 已安装 bb-browser 扩展
- 用户已在浏览器中登录 Podwise（复用登录态）
- Obsidian 已打开，官方 CLI 已启用（Settings → General → Advanced → CLI）
- 官方 CLI 路径：`/Applications/Obsidian.app/Contents/MacOS/obsidian-cli`

## 输出规格

- 目标 vault：`obsidian-vault`
- 目标目录：`podcasts/`
- 文件名格式：`YYYY-MM-DD 播客标题.md`
- 内容板块（按顺序）：frontmatter → 摘要 → 核心要点 → 思维导图 → 关键词 → 金句摘录 → 章节概要 → ASR 审阅记录 → 逐字稿

## 工作流

### Step 1: 打开页面并定位 transcript API

通过 bb-browser HTTP API 打开 Podwise 页面，等待加载后从 `performance.getEntriesByType("resource")` 中提取 transcript API 地址。

```bash
# 打开页面
curl -s -X POST http://localhost:19824/command \
  -H "Content-Type: application/json" \
  -d '{"action":"open","url":"<podwise-url>"}'

# 等待加载
curl -s -X POST http://localhost:19824/command \
  -H "Content-Type: application/json" \
  -d '{"action":"eval","script":"document.title"}'
```

关键：从 performance entries 中找到形如以下格式的 API 地址：
```
https://podwise.ai/api/no-auth/episodes/<hash>/transcripts?token=<token>&unzip=false
```

提取方式：
```javascript
performance.getEntriesByType("resource")
  .filter(r => r.name.includes("transcripts"))
  .map(r => r.name)
```

### Step 2: 获取完整数据

在浏览器上下文中调用 transcript API（带 `unzip=true`），获取 JSON 数据。数据结构：

```json
{
  "summary": {
    "version": "1.0",
    "summary": "...",
    "takeaways": [...],
    "chapters": [...],
    "chapter_parts": [...],
    "qas": [...],
    "keywords": [...],
    "highlights": [...],
    "mindmap": "..."
  },
  "text": "[{\"time\":\"00:01:19\",\"content\":\"...\",\"speaker\":\"Speaker 1\",...}]"
}
```

注意 `text` 字段是 JSON 字符串，需要两次 `JSON.parse`。

由于数据量大（transcript 通常 50 万+ 字符），需要分块传输：
1. 在浏览器中将 JSON 字符串切成 50000 字符的 chunks
2. 逐块通过 eval 取回
3. 本地拼接后解析

```javascript
// 浏览器端分块
const t = JSON.stringify(window.__trData.text);
const chunkSize = 50000;
window.__trChunks = [];
for(let i=0; i<t.length; i+=chunkSize) {
  window.__trChunks.push(t.substring(i, i+chunkSize));
}
```

### Step 3: ASR 审阅修正

对 transcript 文本进行语音识别错误检查。常见错误模式：

- 同音字错误（如"逐字稿"→"竹子稿"、"余额宝"→"鱼蛾堡"）
- 专有名词识别错误（如 App 名、人名、术语）
- 语境不符的用字（如"矛"→"毛"、"背会"→"备会"）

审阅流程：
1. 根据播客主题和上下文，建立可能的专有名词列表
2. 扫描全文，标记疑似 ASR 错误
3. 自动修正明确的错误，记录修正表
4. 在说话人标识上，根据上下文将 "Speaker 1"/"Speaker 2" 映射为实际人名

输出审阅记录表：

```markdown
| 时间 | 原文 | 修正 | 说明 |
|------|------|------|------|
| 00:01:19 | 竹子稿 | 逐字稿 | ASR 同音错误 |
```

### Step 4: 生成 Markdown 并写入 Obsidian

使用官方 obsidian-cli 分段写入。由于 CLI content 参数有长度限制，长文档必须分段：

```bash
OBS=/Applications/Obsidian.app/Contents/MacOS/obsidian-cli

# 1. 创建文件（含 frontmatter）
$OBS vault="obsidian-vault" create \
  name="podcasts/YYYY-MM-DD 标题" \
  content="---\ntitle: ...\npodcast: ...\ndate: ...\n---" \
  silent

# 2. 逐段 append 各板块
$OBS vault="obsidian-vault" append \
  path="podcasts/YYYY-MM-DD 标题.md" \
  content="..."

# 3. 逐字稿分批写入（每批 ~3000 字符）
```

### Step 5: 清理

关闭 bb-browser 打开的 tab：
```bash
curl -s -X POST http://localhost:19824/command \
  -H "Content-Type: application/json" \
  -d '{"action":"close","tabId":<tabId>}'
```

## Frontmatter 模板

```yaml
---
title: "播客标题"
podcast: 播客节目名
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

## 注意事项

- bb-browser HTTP API 地址固定为 `http://localhost:19824/command`
- eval 的参数名是 `script`，不是 `expression`
- 如果 CLI 命令报 "No page target found"，改用 HTTP API
- Podwise 页面使用虚拟滚动，不能通过 DOM 直接提取完整 transcript，必须走 API
- 不要用 npm 的 `obsidian` 命令（需要 API key），用 `/Applications/Obsidian.app/Contents/MacOS/obsidian-cli`
- 写入前确保 `podcasts/` 目录存在（obsidian-cli create 会自动创建）
