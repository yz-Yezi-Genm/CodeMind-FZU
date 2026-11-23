# Beta 第二阶段：真实 Qwen 与 Agent 联调

日期：2026-11-23  
分支：`feat/beta-runtime-qwen-integration`  
依赖：第一阶段 `feat/beta-runtime-stability`

## 1. 阶段边界

第一阶段负责 FastAPI、Runtime、QwenClient 和离线契约测试。

第二阶段只记录真实 Qwen 调用、受约束 JSON 输出以及吴诗莹 Beta AgentWorkflow 的最终联调。本阶段不修改公共 DTO、Protocol、Retriever 或业务规则。

## 2. 当前已完成

真实 `qwen-flash` 已完成一次受约束 JSON 请求：

```json
{"answer":"奖学金申请需要提交申请表和成绩单。","used_evidence_ids":["E1"]}
```

适配器完整返回 JSON 内容、模型名称和 usage；模型内容和 Agent 内部 JSON 校验边界保持不变。记录见
[qwen-constrained-live.txt](evidence/qwen-constrained-live.txt)。

当前 `main` 的 FastAPI + Runtime + 真实 Qwen 也完成了一次合成资料 HTTP 冒烟，返回
`200 / answered / 非空引用`。记录见
[runtime-http-smoke.txt](evidence/runtime-http-smoke.txt)。

该 HTTP 冒烟使用当前 Alpha 证据摘录协议，不等同于 V2.1 受约束自然语言生成验收。

## 3. 合并条件

第二阶段不得在以下条件完成前合并：

1. 吴诗莹 Beta Agent 分支完成 V2.1 `answer + used_evidence_ids` 解析与 Citation 构造；
2. Agent 集成分支合入 `main` 或与第二阶段建立明确依赖；
3. 真实 Qwen 经最终 `/api/v1/ask` 返回受约束自然语言答案；
4. Agent 拒绝未知、重复、跨请求 evidence ID；
5. Citation 来自本次真实检索片段；
6. MockTransport、直接 Qwen、FastAPI HTTP、正式资料验收分别记录；
7. 使用正式人工审核资料完成一次四领域或对应场景的正向验收，或明确记录正式资料缺失导致的安全拒答。

## 4. 当前阻塞

- Beta AgentWorkflow 尚未合入 `main`。
- 正式 `knowledge_base/processed/alpha/approved/` 暂无项目负责人人工签核资料包。
- 因此第二阶段目前保持 Draft，不能把当前 HTTP 冒烟写成 V2.1 完整链路通过。
