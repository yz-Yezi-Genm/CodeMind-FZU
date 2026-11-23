# PR: Beta 第二阶段真实 Qwen 与 Agent 联调

## 修改目的

在运行稳定性第一阶段合入后，单独记录和验证真实 Qwen、V2.1 受约束 JSON 以及 AgentWorkflow 证据 ID/Citation 链路。

## 修改文件

- `scripts/check_beta_qwen_generation.py`
- `docs/assignment-03/beta/qwen-integration-stage2.md`
- `docs/assignment-03/beta/evidence/qwen-constrained-live.txt`
- `docs/assignment-03/beta/evidence/runtime-http-smoke.txt`

## 当前完成

- 真实 `qwen-flash` 返回受约束 JSON；
- Qwen 适配器完整传递模型内容、model 和 usage；
- 当前 Runtime 通过真实 HTTP 完成合成资料测试；
- MockTransport 与真实调用记录分开。

## 依赖

- 第一阶段：`feat/beta-runtime-stability`
- Agent：吴诗莹 `feat/beta-agent-history` / PR #46
- 正式资料：项目负责人最终人工审核

## 合并条件

- 第一阶段已合并；
- Agent 受约束生成和引用校验已合入；
- 真实 Qwen 经最终 `/api/v1/ask` 复跑；
- 正式资料或明确安全拒答记录完成；
- 不将当前 Alpha 证据摘录 HTTP 冒烟写成 V2.1 最终通过。

## 已知问题

当前正式 approved 目录无签核资料；Beta AgentWorkflow 尚未合入 main。因此本 PR 保持 Draft。
