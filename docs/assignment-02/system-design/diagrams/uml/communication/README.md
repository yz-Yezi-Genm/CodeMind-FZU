# UML 通信图

负责人：赵紫龙（v1.0 已完成，待成员本人提交与交叉评审）。

本目录通过 UML 通信图描述两个核心协作场景：官方资料问答、知识资料维护与索引更新。每张图均提供 Draw.io 可编辑源文件、SVG 矢量图和 PNG 预览图，配套消息表说明发送方、接收方、数据、异常与降级策略。

## 交付文件

| 场景 | 可编辑源文件 | 导出图 |
|---|---|---|
| 官方资料问答 | `UML通信图_智能问答_赵紫龙_v1.drawio` | `UML通信图_智能问答_赵紫龙_v1.svg`、`.png` |
| 知识维护与索引 | `UML通信图_知识入库_赵紫龙_v1.drawio` | `UML通信图_知识入库_赵紫龙_v1.svg`、`.png` |

详细对象职责、消息编号、错误处理、状态机与审计字段见 [`通信设计说明_赵紫龙_v1.md`](通信设计说明_赵紫龙_v1.md)。

> 说明：问答链路采用开题稿确定的 Chroma + BM25 + RRF + Qwen 方案。当前真实模型调用与混合检索联调仍待验证；数据库与完整 Web 管理端属于后续设计。

Draw.io、SVG 和 PNG 均由 [`../../../source/tools/generate_zhaozilong_diagrams.py`](../../../source/tools/generate_zhaozilong_diagrams.py) 的同一场景模型生成，避免三种格式的消息连接漂移。

知识维护流程在测试通过后由 `IndexPublisher` 提交统一版本，`VersionRegistry` 原子切换活动版本指针，`AgentQueryGateway` 仅向 Agent 暴露完整发布版本。项目整体覆盖五大业务方向；竞赛认定、奖学金申请、推免基本条件是代表性验证任务，不代表业务方向数量。交换出国当前资料不足，不纳入首版。

问答链路将生成前证据筛选和生成后回答复核分开：`EvidenceVerifier` 向 Agent 返回已核验证据，`AnswerVerifier` 复核 Qwen 返回的草稿。
