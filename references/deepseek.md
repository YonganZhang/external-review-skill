# DeepSeek 外援：官方 Harness

其他宿主调用官方 `dsh` 执行独立审查，保留 `provider=deepseek`。默认双外援选择不变；只有 `--providers deepseek` 或显式组合才产生 DeepSeek 调用。它是第四个可选提供方，不是把 Claude/Codex 的身份替换成 DeepSeek。

## 安装与认证

验证版本：`@deepseek-ai/dsh@0.2.1-rc.2`（开发者预览）。本次使用 Node.js 22.22.1 验证；上游 [CLI 文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.zh.md) 和 [模型配置](https://deepseek-harness.github.io/deepseek-harness/guide/providers) 说明其完整能力。

```bash
npm install -g @deepseek-ai/dsh@0.2.1-rc.2
dsh --version
bash scripts/llm-doctor.sh deepseek --json
```

通过自己的凭证管理工具向调用进程提供 `DEEPSEEK_API_KEY`。不要把密钥放在参数、提示词、仓库或待分享的报告中。这个适配器固定使用官方 API 路由 `deepseek-official`，清除继承的 `DEEPSEEK_BASE_URL`；不支持第三方中转。官方 headless 关闭交互登录凭证读取，使用环境变量，其次是工作目录和 DSH_HOME 的 `.env`；所以仍需审查所选工作目录的配置。每个作业创建独立 DSH_HOME，不自动切换账号。

Harness 开源，API 使用充值或赠送余额按量扣费。上游还有交互式官方账号登录能力，但本适配器不启用它，也不承诺任何订阅权益。安装脚本不会购买套餐、充值或替用户生成凭证。

## 调用

在技能目录中运行：

```bash
python3 scripts/external-review.py --host codex --providers deepseek \
  --repo /path/to/project --prompt-file /path/to/review.md --json
```

也可通过 `bash scripts/deepseek-ask.sh --repo /path/to/project --prompt-file /path/to/review.md --json` 发起单次任务。默认 `deepseek-flash` / `low`；`--deep` 与 `--gate` 保持模型、将默认 effort 设为 `high`。显式 `LLM_DEEPSEEK_EFFORT=off|low|high|max` 优先。需要 Pro 时显式使用统一入口 `--model deepseek=deepseek-v4-pro` 或单家入口 `--model deepseek-v4-pro`。不自动升档或换模型。

默认权限 `native` 映射为 dsh `workspace-write`；`bypass` 映射为 `danger-full-access`，仅用于获得授权的可信任务。headless 无界面审批会失败关闭。外层 timeout 约束本次进程组，不安装全局队列、内存预留或常驻服务；主动脱离进程组的工具不在该终止保证内。

## 报告与费用

作业目录包含 `result.md`、`deepseek-events.jsonl`、`deepseek-stderr.log`、`deepseek-final.txt`、`deepseek-usage.json`；正常退出时另存 dsh 原始退出码。成功必须同时满足原始进程退出 0、完整且成功的终端事件、严格报告。失败不会用拼接字段伪装完成。原始运行数据可能含审查材料，分享技能时不包含它们。

费用估算依据 [官方价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)（2026-10-22），单位为人民币/百万 token：

| 模型 | 未缓存输入，空闲/高峰 | 缓存输入，空闲/高峰 | 输出，空闲/高峰 |
|---|---|---|---|
| Flash | 1 / 2 | 0.02 / 0.04 | 4 / 8 |
| V4 Pro | 4.5 / 9 | 0.15 / 0.30 | 13.5 / 27 |

`deepseek-usage.py` 对官方逐步 usage 求和。上游 `inputTokens` 已经排除缓存输入；推理 token 包含在输出中，不重复收费。只估算根智能体的 token，不包括可能的子任务、标题生成、搜索抓取等额外请求。缺失用量、未知模型或未知缓存写入费用时保留未知，不能拿零代替。价格有变化，脚本带日期与来源，官方账单为准。Search/Fetch 从 2026-11-01 起按官方说明另计，不能用这里的 token 估算代表全部费用。

## 适用范围

此接入验证工具调用、报告回收、异常退出和费用可见性；并不证明官方 Harness 的审查质量一定优于其他 Harness。它目前处于预览阶段，升级前应重跑契约测试和一次小规模真实审查。
