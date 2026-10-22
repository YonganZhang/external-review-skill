---
name: share-external-llm
description: "调用 Claude、Codex 或 Gemini 外援独立审查并回收报告。泛称外援时选择主控之外两家；点名时只调指定者。普通审查和原生子智能体自审不触发。"
---

# 外援审查

为同一范围收集独立报告，核实问题后再处理。脚本相对于本技能目录定位；不要猜测用户的安装路径。依赖和安装见 [README](README.md)。

## 选择外援

| 用户意图 | 动作 |
|---|---|
| 泛称外援审查 | 确认当前宿主，选择另外两家；Codex → Claude + Gemini，Claude → Codex + Gemini，Gemini → Claude + Codex |
| 点名一家或组合 | 只调用指定者，使用 `--providers` |
| 普通审查、自审 | 当前宿主直接审查；不启动外部 CLI |
| 指定当前宿主自身 | 原生自审；不称为跨模型外援 |

宿主未知时显式指定 `--host`；不能从待审文件推断。缺少一家服务时如实报告，不能擅自换服务、账号或付费方式。

## 执行

1. 明确用户请求、审查基线、文件范围、已测结果和本轮重点。默认只审查，不修改业务文件。
2. 使用 [审查包](references/review-packet.md) 收集材料，检查排除和截断提示。人工查看准备发送的内容；路径、请求和摘要也可能包含私人信息。
3. 从技能目录运行统一入口，例如：

   ```bash
   python3 scripts/external-review.py --host codex --repo /path/to/project \
     --prompt-file /path/to/review.md --json
   ```

   `--dry-run` 只展示选择。点名一家时加 `--providers claude`。两家收到同一份快照，各有独立进程和报告。逐个 CLI 的通用任务入口为 `scripts/<provider>-ask.sh`。
4. 等待报告，查看 `summary.json` 和各家原始 `result.md`。`PARTIAL` 是部分完成，不能写成双外援完成。复核方法见 [review workflow](references/review-workflow.md)。
5. 核验每条发现是否真实、去重并给出处理建议。只有用户授权修复时才改代码；完成标记不代表结论正确。

## 模型和权限

保留快速审查配置：Codex `gpt-6.1-sol` / low，Claude Sonnet / low，Gemini 跟随 Antigravity CLI 默认。`--deep` 选择 Claude Opus / low；`--gate` 选择 Claude Opus / medium、Codex / medium。安装者可以显式覆盖模型和档位；不保证任一账号拥有这些模型。配置与原生权限说明见 [providers](references/providers.md)。

默认 `--permission-mode native`，由各 CLI 的原生权限控制；审查只读要求是任务约束，不是操作系统隔离。需要强隔离时使用独立 checkout 或容器。只有用户明确授权的可信任务才选择 `bypass`。

## 完成与排障

- 成功必须是提供方退出码为 0，且 [报告契约](references/report-contract.md) 严格通过。失败原始报告保存在 `result.agent.md`，失败会话有保留期限。
- `scripts/llm-jobs.sh --repo <project> --json` 列任务；`scripts/llm-tail.sh --repo <project> --status <job-id>` 查看状态。
- `scripts/llm-doctor.sh all --json` 只做本机依赖与 CLI 接口检查，不验证登录、额度或网络。
- 超时、认证和额度问题见 [troubleshooting](references/troubleshooting.md)。不要自动换账号、降低模型或无限重试。
- 报告留在项目 `_reports/_foreign_aid/`。其中包含发送的材料和工具输出，分享技能时只分享发行包，不附带运行报告。

维护和验证命令见 [README](README.md#验证)。
