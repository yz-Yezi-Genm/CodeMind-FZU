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

当前仅完成源码读取、静态审查、远程提交及回读；尚未独立执行 Python 测试。不得把新增用例数当作通过数，也不得把旧 PR 测试日志当作本分支结果。

## 合并前验收

使用 Python 3.10.11、项目已有依赖，在本分支执行：

```powershell
python --version
python -m pytest tests/test_beta_response_contract_validation.py tests/test_interface_contracts.py tests/test_mock_agent_api.py tests/test_backend_runtime.py -q -ra
python -m pytest tests -q -ra
git diff --check
```

记录实际 HEAD、环境、退出码、通过/失败/跳过及警告。发现其他旧测试调用缺少必要字段时，最小修复测试替身，禁止降低断言标准。#44、#46、#53 同步合并后的 main 后分别回归；#50 真实模型验收仍独立开展。未获组长复核不得合并。
