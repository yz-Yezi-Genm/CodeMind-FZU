# Beta 公共响应契约修复

基线：b855b48f7d77f834cd58b182c3d394ce3f7f5e91（含 #41、#45、#49、#51）。
依据：V2.1-Final §5.3、§6.2。

## 修改范围

- AgentResult、AskResponse 共用私有响应形状校验函数。answered 必须具有非空 answer 及明确 answer_mode；needs_clarification 必须具有非空追问，answer/answer_mode 为 null、citations 为空；insufficient_evidence 必须使用 insufficient_data、空 citations，并通过 answer 或 warnings 提供非空说明。
- 不改变字段、枚举、序列化结构或 Protocol。§5.3 未明确禁止 answered 使用某个现有枚举值，本轮仅强制模式非空；如需禁止 answered + insufficient_data，应另行确认规范。原因文本是否真正解释证据缺口、引用事实正确性属于工作流验收，而非 DTO 结构校验。
- MockAgentService 正常模拟响应显式使用 current_policy 作为合成演示模式，保留原有模拟标识和无真实政策结论说明。四处运行时测试替身补齐模式，原有断言不删除。Mock HTTP 测试增加模式和空引用断言。
- 新增 tests/test_beta_response_contract_validation.py：两个 DTO 的正反向参数化测试及 HTTP 200 证据不足测试。

## 兼容性及验证边界

已静态核对 main 中的 AgentWorkflow 三个主要输出分支、HTTP AskResponse 构造、Mock Agent、运行时测试替身和若干现有测试、演示脚本。GitHub 代码搜索没有返回匹配结果，因此不能声称完成全仓库调用方穷举。未修改其他成员的核心工作流、资料审核状态、前端或数据库。

已完成源码读取、静态审查、远程提交及回读。以下测试为组长在本地 Windows .venv 实际执行并提供的终端输出，非 GitHub Actions 或助手独立运行结果。测试时远程 HEAD 为 `4ab5b01`；本地 HEAD、Python 小版本与 git diff --check 尚待终端命令确认。

## 合并前验收

使用 Python 3.10.11、项目已有依赖，在本分支执行：

```powershell
python --version
python -m pytest tests/test_beta_response_contract_validation.py tests/test_interface_contracts.py tests/test_mock_agent_api.py tests/test_backend_runtime.py -q -ra
python -m pytest tests -q -ra
git diff --check
```

记录实际 HEAD、环境、退出码、通过/失败/跳过及警告。发现其他旧测试调用缺少必要字段时，最小修复测试替身，禁止降低断言标准。#44、#46、#53 同步合并后的 main 后分别回归；#50 真实模型验收仍独立开展。未获组长复核不得合并。


## 2026-11-24 本地测试验收记录

| 测试 | 实际结果 |
| --- | --- |
| 四文件专项 pytest | 134 passed, 1 warning in 4.47s |
| 首次全量 pytest | 2 failed, 505 passed, 28 skipped, 1 warning, 152 subtests passed in 14.21s |
| 恢复本地原始 HTML 的 LF 后全量 pytest | 505 passed, 28 skipped, 1 warning, 154 subtests passed in 10.97s |

专项与最终全量运行均无失败。首次全量的两项失败是同一奖学金原始 HTML 文件的 SHA-256 不匹配，分别出现在 document_processing 与 local_retrieval 的子测试中；不是两个独立的主测试，因此复测通过后主测试计数仍为 505，子测试从 152 增至 154。

独立读取远程 main 原始字节并计算 SHA-256：LF（56992 字节，含 UTF-8 BOM）为 `a979ba14520f885b66344a91726e9f9ba90656b83a6a5d9ef2556b3a07baa675`，与已登记哈希一致。模拟 CRLF（57777 字节）为 `cdbb5410575e98f7bcd2a868dedaee1bf535ebb26c5de83c42e731771b90dc8c`，与首次失败日志一致。根目录 .gitattributes 已指定该文件 LF；仅在本地恢复换行符，未修改远程政策原件、登记哈希或校验逻辑。

跳过：25 项需单独运行 scripts.verify_beta_upstream_integration 的上游联调测试，2 项真实 Qwen opt-in 测试，1 项 Windows 符号链接权限测试。警告：既有 StarletteDeprecationWarning（httpx TestClient）。以上跳过不计为通过。

合并前仍需确认本地测试对应代码提交（本次文档提交不改变代码）、Python 3.10.11、工作区状态和 diff 格式；建议单独执行上游联调脚本。真实 Qwen 与正式政策验收不在本 PR 范围。保持 Draft，未合并。
