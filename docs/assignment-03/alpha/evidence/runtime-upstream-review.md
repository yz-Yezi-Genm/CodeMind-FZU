# Alpha Runtime 第二轮集成复核

日期：2026-11-20（Asia/Shanghai）

## 集成版本

| 上游 | 参考提交 | 使用方式 |
|---|---|---|
| #35 已审核资料加载器 | `main` `a87182c5dd6f805f316df0b75896b8f84fa4415f` | 已正常合入 #34，运行时调用 `load_approved_alpha_retriever()` |
| #32 最新 AgentWorkflow | `8ce01317f0b95441525c54c144af2eb1fb69c4a9` | 尚未合入 `main`；在临时集成副本中合并验证 |
| #36 最新业务规则 | `917c9149628c9cfe03e1d1b64f51d3d22969a827` | 尚未合入 `main`；在临时集成副本中合并验证 |

临时集成副本先合并 #32，再合并 #36，核心模块无冲突。`tests/test_agent_workflow_api.py` 仅因双方同时修改测试文件产生冲突，验证时采用 #32 版本；#34 的运行层测试在 `tests/test_backend_runtime.py` 中单独执行。

## 运行修复

- 资料只通过 #35 `load_approved_alpha_retriever()` 加载，不再自行扫描 JSON。
- 运行时要求资料目录存在、已加载包和索引结果非空、片段数大于零、每条索引严格 `indexed` 且 warnings 为空。
- 人工审核由 #35 同时检查 manifest 的 `human_approved is True` 和 `temporal_notes["human_approved"] is True`。
- 业务规则使用 #36 `build_from_retriever(retriever)`，闭包绑定当前 Retriever 的 `get_document_metadata` 与 `get_parsed_chunk`，不再调用未初始化的全局证据入口。
- #32 合入后自动调用 `create_alpha_workflow(...)`；未合入期间保持同签名 `AgentWorkflow` fallback。
- `CONVERSATION_MAX_MESSAGES` 为奇数时向下归一化为完整问答对。
- 会话增加全局数量上限、空闲回收、显式清理和后台清理任务；活动请求不会被清理。

## 测试结果

### 当前 #34（含 #35，未含 #32/#36）

```text
定向运行/API/Qwen/会话：
Ran 43 tests, OK

全量 unittest：
Ran 199 tests
195 passed, 2 failed, 2 skipped
```

两个失败均为既有 `scholarship-2026` 文件 SHA-256 与登记值不一致；跳过一个为 Windows 符号链接权限，另一个为 #36 未合入时的条件测试跳过。

### #34 + #32 + #36 临时集成副本

```text
运行层与最新业务规则定向测试：
Ran 13 tests, OK

全量 unittest：
Ran 248 tests
229 passed, 1 failed, 18 skipped

#32 官方上游集成脚本：
Ran 16 tests, OK

#36 pytest：
102 passed, 1 failed
```

唯一 #32 unittest 失败是 `test_legacy_package_snapshot_is_read_only_and_metadata_is_detached`：该测试仍断言 `LocalBM25Retriever` 不应有 `index_document`，但 #35 已增加元数据查询能力，所以组合后该断言过期；运行层本身未失败。

#36 唯一 pytest 失败是 `test_workflow_answers_with_applicable_evidence`：其测试资料未设置 #32 最新工作流要求的 `temporal_notes["human_approved"] is True`，因此被安全拒绝。该失败属于 #32/#36 测试替身口径未对齐，不是放宽审核的代码问题。

## 失败关闭场景

以下场景均通过：

- 正式 approved 目录缺失；
- 资料 `enabled` 但 `human_approved=false`；
- manifest 通过而包内审核标记缺失；
- 来源未就绪导致 `partial`；
- 索引结果含 warnings；
- 业务规则拒绝证据，Qwen 调用次数为 0；
- 最新工作流拒绝未人工审核证据；
- 历史证据不进入当前政策回答；
- 损坏元数据、错误政策类型、年度不匹配和教师章节被拒绝。

## 当前未完成

- `knowledge_base/processed/alpha/approved/` 仍没有正式 `enabled` 资料包。
- 当前机器没有配置真实 `QWEN_API_KEY`，未执行付费 Qwen 请求。
- #32、#36 尚未合入 `main`，最终 PR 需在二者合并后再次同步并重跑。
