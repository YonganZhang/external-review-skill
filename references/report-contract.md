# 外援严格报告契约

runner 自动向 worker 注入实际 job、报告路径和此格式；调用者不必重复粘贴模板。生命周期由 `scripts/llm-tmux-run.sh` 管理，格式验证由 `scripts/llm-report.py` 统一执行。

每个有意义阶段更新 `progress.md`：时间、阶段、剩余工作。最终 `result.md` 保留以下字段与六个标题，审查 findings 放 Evidence 中，不另加 `==END==` 等完成协议。

```markdown
# Foreign Aid Result

JOB_ID: <actual job id>
PROVIDER: <codex|gemini|claude>
COMPLETION_STATUS: <COMPLETE|FAILED|BLOCKED>
ERROR_CLASS: <NONE|QUOTA|AUTH|NETWORK|TIMEOUT|TOOLING|MODEL_REJECT|MISSING_COMPLETION_MARKER|TMUX_DIED|OUTER_TIMEOUT|UNKNOWN>

## Summary
简明结果。

## Work Performed
实际做过的动作。

## Evidence
证据、findings、验证和未覆盖项。

## Files Changed Or Reviewed
实际文件路径，或 None。

## Errors Or Blockers
无则 None。

## Next Steps
调用者后续动作。
```

真正完成才能填写 COMPLETE；未完成写 FAILED / BLOCKED 与错误分类。worker 不修改 runner 的状态文件；主控不能补造完成标记。格式通过不代表内容正确，最终仍由主控核验。

成功同时要求提供方退出码为 0；JOB_ID 和 PROVIDER 必须匹配该任务，四个元数据字段各出现一次，六个必需标题各出现一次且内容非空。错误退出即使写了 COMPLETE 也会判失败，并保留原始报告。
