# External Review Skill · 外援审查

让 Claude、Codex、Gemini 对同一份材料独立审查，再由主控核实、合并发现。面向 Codex / Claude Code 的可安装 Skill，也能独立从终端使用。

## 这份包做什么

- 自动选择主控之外两家，或只运行你指定的服务；并行调用，同一份材料，独立报告。
- 收集 Git 暂存、未暂存、未跟踪及指定基线后的改动，支持带空格的路径。
- 进程成功并且报告完整才算完成；一家失败时明确保留“部分完成”。
- 本地任务状态、错误分类和报告路径支持 JSON；没有全局排队、内存名额或后台常驻服务。

## 环境

验证环境为 Linux：Python 3.10+、Bash 4+、Git、tmux、GNU coreutils（含 `timeout`、`sha256sum`），以及所选提供方的 CLI。Python 无第三方依赖。WSL 可按 Linux 配置，未单独验证；macOS / 原生 Windows 尚未验证。

你需要使用自己的账号安装并登录 `claude`、`codex`、`agy`（Google Antigravity CLI）。只安装打算调用的提供方即可；默认双外援需要对应两家都可用。本技能不提供账号、模型额度或任何服务的再分发副本。安装、登录和模型配置见 [providers](references/providers.md)。

## 给老师：三步开始

1. 解压后进入 `share-external-llm` 目录，检查本机依赖：

   ```bash
   bash scripts/llm-doctor.sh all --json
   ```

   `authentication: NOT_CHECKED` 表示还需自行确认服务已登录。
2. 安装到一个项目（先预览，再应用）：

   ```bash
   python3 install.py --project /path/to/your-project
   python3 install.py --project /path/to/your-project --apply
   ```

   默认安装到该项目的 `.agents/skills/share-external-llm` 和 `.claude/skills/share-external-llm`，不改全局配置。可用 `--target codex` 或 `--target claude`。相同内容重复安装会跳过；不同版本会停止并显示路径，避免覆盖接收者已有内容。
3. 在该项目新开宿主会话，说：“用外援审查这次修改。”宿主应读取本技能并按实际身份选择提供方。也可直接运行下面的命令。

## 终端用法

以下命令在解压的技能目录执行，将项目路径替换为自己的 Git 仓库：

```bash
bash scripts/llm-review-packet.sh --repo /path/to/project \
  --path src --request '检查这次改动是否引入回归' --out /tmp/review-packet.md
python3 scripts/external-review.py --host codex --repo /path/to/project \
  --prompt-file /tmp/review-packet.md --dry-run
python3 scripts/external-review.py --host codex --repo /path/to/project \
  --prompt-file /tmp/review-packet.md --json
```

先打开 `/tmp/review-packet.md` 检查实际内容。已有输出默认不覆盖；确认重建时给 packet 命令加 `--force`。用 `--base <commit>` 纳入该提交到当前工作树的差异；默认基线为 HEAD。

指定一家：`--providers claude`。指定模型：`--model claude=sonnet`（可重复）。默认快速配置和 `--deep`、`--gate` 见 [providers](references/providers.md)。每家超时默认 1200 秒，可用 `--timeout` 改动。

统一入口退出码：全部完成为 `0`，部分完成或全部失败为 `1`，参数错误为 `2`。轮次记录在 `_reports/_foreign_aid/reviews/<round>/summary.json`，原始报告在各自 job 目录。严格成功契约见 [report-contract](references/report-contract.md)。

## 验证

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash tests/test-llm-tmux-run.sh
```

测试用合成仓库、替身 CLI 和隔离 tmux，不使用真实模型额度。发行版的验证记录见 [VALIDATION.md](VALIDATION.md)。故障排查见 [troubleshooting](references/troubleshooting.md)，脚本索引见 [scripts/README.md](scripts/README.md)。

## 分享与许可

MIT 许可，见 [LICENSE](LICENSE)。来源和改动范围见 [NOTICE.md](NOTICE.md)。`MANIFEST.json` 记录发行文件的 SHA-256，安装器验证它后才复制。源码克隆的维护者修改文件后需重新生成发行清单；发行配方见仓库随附的 `release.py`。

English: a portable external-review skill with independent provider reports, strict completion checks and explicit partial failure. Bring your own CLI installation and account. Linux is the tested platform.
