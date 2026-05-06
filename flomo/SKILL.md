---
name: flomo
description: 把内容作为一条笔记发送到 flomo(通过 webhook)。当用户输入 /flomo、说"记到 flomo"、"发 flomo"、"flomo 记一下"、"存到 flomo"、"Memo 一下"、或用 #标签 格式想快速记一条想法到 flomo 时触发。短内容(一两句话)直接发送,长内容或多段 markdown 先展示预览再请用户确认。
allowed-tools: Bash, AskUserQuestion, Read
---

# flomo

把内容发送到 flomo,一条笔记 = 一次 webhook POST。

## 安装

从 repo 首次拉取后,把本 skill 目录复制到 `~/.claude/skills/`,然后创建真实配置:

```bash
cp -r flomo ~/.claude/skills/
cd ~/.claude/skills/flomo
cp .config.example .config
chmod 600 .config
# 编辑 .config,把 FLOMO_WEBHOOK=xxx 替换为 flomo 账号「设置 → API」里的 incoming webhook URL
chmod +x send.sh
```

`.config` 里有 webhook token,已在仓库 `.gitignore` 中,**不会被提交**。

## 依赖

- `~/.claude/skills/flomo/send.sh` — 发送脚本(已可执行)
- `~/.claude/skills/flomo/.config` — 存 `FLOMO_WEBHOOK` 的值(权限 600)
- 系统需要 `curl` 和 `jq`

## 触发形式

1. `/flomo <内容>` — 斜杠命令 + 同一行直接跟内容
2. `/flomo`(空) — 询问用户要记什么,或基于最近对话提取候选内容
3. 自然语言:"记到 flomo: xxx"、"这个存 flomo"、"flomo 一条:xxx"

## 两种发送模式

### A. 短内容直接发(快路径)

满足所有条件 → **直接调 `send.sh`,不用 AskUserQuestion**:
- 内容是用户在 `/flomo` 后直接写的一两句话(粗略估 ≤ 140 字、单段)
- 没有多行/代码块/列表/链接大段摘录
- 用户没有 "先给我看看"、"确认一下" 这类字样

### B. 长内容/Markdown 先预览(稳路径)

任一条件命中 → **先把最终 markdown 贴给用户,再 AskUserQuestion 确认**:
- 内容超过 ~140 字、或包含多段/列表/代码块/引用
- 内容是你基于对话整理、提炼、翻译出来的(不是用户原话直发)
- 包含链接 + 摘要、或多个主题合并成一条
- 用户明确要求 "让我看看"、"确认后再发"

确认问题固定两个选项:**「发送」/「让我改改」**。用户改完再回到本环节走一遍。

## 标签处理(两种模式都跑)

发送前,扫一遍内容看是否需要 **自动抽取 / 追加 #标签**:

1. **用户已写了 `#xxx`** → 原样保留,不改。
2. **用户口头提了标签**(如"标签用读书"、"打上 #工作 标签") → 把 `#读书` / `#工作` 加到正文末尾(如果正文里没有)。
3. **内容主题很明确且用户没给标签**(比如明显是在总结一本书、记一次会议、一段代码心得) → 可以**建议** 1-2 个标签,但**必须在预览环节让用户确认**,不要自作主张加。走快路径时**不要**自动猜标签。
4. 标签放在正文**末尾**,用空格分隔:`...内容... #标签1 #标签2`

flomo 的标签支持多级:`#读书/笔记`、`#工作/技术`。如果用户的已有标签体系能判断出来,用多级;判断不出来就用单级。

## 发送

一条命令:

```bash
~/.claude/skills/flomo/send.sh "最终内容"
```

或通过 stdin(内容里有特殊字符/换行时更稳):

```bash
~/.claude/skills/flomo/send.sh <<'FLOMO_EOF'
多行内容
第二行
#标签
FLOMO_EOF
```

**内容中如果可能出现 `FLOMO_EOF` 字样,换一个不会冲突的 heredoc 标记。**

## 结果反馈

- 成功:`OK: flomo accepted the note (HTTP 200)`,告诉用户"已发送到 flomo",一句话就够,不要重复粘贴内容。
- 失败:把 `send.sh` 的 stderr 原文展示给用户。常见错因:
  - HTTP 非 200 → webhook URL 可能被轮换,让用户去 flomo 账号设置重新拿 URL,更新 `.config`。
  - `code` 非 0 → flomo 服务端拒绝(内容过长、频控等),把 body 里的 `message` 念给用户。

## 禁止

- 不要为了 "安全" 给内容加 "以下是笔记内容:" 这种前缀,用户要什么就发什么。
- 不要发送空内容。
- 不要在未得到用户确认时,把整段对话/长文章塞进一条笔记(flomo 是卡片笔记,不是文档)。如果内容超 1000 字,应该先问用户:"这么长要不要分成几条发?"
