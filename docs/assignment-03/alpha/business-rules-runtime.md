# Alpha 业务规则运行时说明

把 `docs/assignment-03/alpha/business-rules.md`（PR #29 已合并）中的判定规则落成可执行代码，供 `AgentWorkflow` 直接调用。本文只说明实现与接口对齐，规则本身以上述业务文档为准，不在代码里新增政策条件。

## 1. 交付内容

| 成果 | 路径 |
| --- | --- |
| 规则实现 | `backend/services/alpha_business_rules.py` |
| 单元测试 | `tests/test_alpha_business_rules.py` |
| 本文档 | `docs/assignment-03/alpha/business-rules-runtime.md` |

两个注入函数与既定约定一致：

```python
alpha_clarification_rule(request: AgentRequest) -> str | None
alpha_evidence_check(request: AgentRequest, chunk: RetrievedChunk) -> bool
```

均为同步函数，可直接传入 `AgentWorkflow(clarification_rule=..., evidence_check=...)`（传函数本身，不加括号）。

分支 `feat/alpha-business-rules-runtime`，基于 main `f5fcabc`，PR #36（https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/36）。

## 2. 三个场景的必要字段与追问顺序

追问固定按「事项 → 场景字段」推进，每轮只返回一个问句；信息齐备返回 `None`。

| 场景 | 必要字段 | 追问优先级 |
| --- | --- | --- |
| S1 竞赛认定 | 用途（创新学分 / 综测 / 推免）、赛事名称、获奖级别、获奖等级或排名、个人或集体、前八名（创新学分）、完成人排序（综测）、成果学期与第一署名单位（综测） | 用途 → 赛事名称 → 级别 → 等级 → 个人/集体 → 前八名或排序 → 学期 → 署名单位 |
| S2 奖学金 | 奖学金类别；院级需具体奖项 | 类别 → 院级具体奖项 → 咨询维度 |
| S3 推免 | 咨询对象（校内资格 / 学院复试）、专业与学位类型（问招生计划时） | 年级（个人可能性）→ 咨询对象 → 专业 |

不追问的两类情况：

- 年度不追问。现行通用政策与库内唯一的年度通知都直接作答，按业务文档 2.5 处理；学生问库外年度（2027 年院级、2028 年推免）直接交给证据判断返回证据不足。
- 资料缺口不追问。查认定目录、查级别归属、问校内推免资格门槛时，追问解决不了缺资料，直接返回 `None`，由证据判断拒绝全部片段。

## 3. 证据适用性判断

`alpha_evidence_check` 先过基础门禁（`retrieval_status=enabled`、`source_verification_status=verified`、时效为 current/historical/expired、标题非空、发布日期与生效日期不在未来），再按场景与文档类型收紧：

| 场景 | 判定要点 |
| --- | --- |
| S1 | 创新学分只接受《创新创业学分认定办法》与竞赛级别认定目录；综测加分只接受综评办法与目录。国际级、国家级、省部级赛事缺目录无法定 A+/A/A-/B/C 档，一律不接受综评办法；校级与院级两档可直接定档。推免计分口径未入库，不接受任何竞赛类资料 |
| S2 | 校级办法接受校级奖学金与“不具备资格”类通用问题；院级只接受院级与星火通知，且不得用 2026 年通知回答 2027 年及以后；国家奖学金、文化科技创新创业奖学金、社会捐赠类一律拒绝 |
| S3 | 复试流程、材料、招生计划、录取规则接受 2027 年复试方案；资格排名、加分、遴选细则不接受，复试方案不能充当资格门槛；其他学院与外校问题一律拒绝 |

叠加的通用判定，任一命中即拒绝：

- 年度不匹配：年度类资料（院级通知、推免年度方案）只服务其标注的适用年度，问其他年度（无论更早还是更晚）都拒绝；问库外未来年度直接拒绝。适用年度只取 `applicability_raw` 的适用年度/适用届别字段、标题中的「年/届/版」、记录编号中的年份，**不拿发布日期当适用年度**。
- 年度无法确认：年度类资料取不到适用年度时按未知处理，拒绝。
- 必要元数据缺失：拿不到 `DocumentMetadata`、或 `applicability_raw` 为空时，无法确认文档类型、适用范围与年度，拒绝；不因“片段内容看起来相关”而放行。
- 截止日期已过且问“现在还能不能办”拒绝；专业或年级与资料适用范围不符拒绝。
- 局部章节不适配：同一文件里教师绩效/师资条款不能回答学生问题，学生条款也不能回答教师问题，依据 `ParsedChunk.locator_note` 判断。

返回值只有 `True` / `False`，不返回 `"unknown"`、`"false"` 等字符串。规则内部异常一律按无法确认处理（返回 `False`），不放行。

## 4. 与检索模块的字段约定

`RetrievedChunk` 的 17 个字段里没有 `applicability_raw`、`deadline_on`、`record_code`，按王智洋的说明，这三项位于 `DocumentMetadata`，本轮不扩公共 DTO，也不改 `extra="forbid"` 契约。

取用方式为两个可选的只读查询函数，均与 retriever 的方法签名一致：

- `(version_id: UUID) -> DocumentMetadata | None`（`retriever.get_document_metadata`）
- `(chunk_id: UUID) -> ParsedChunk | None`（`retriever.get_parsed_chunk`，用于读 `locator_note`）

用工厂闭包绑定后，对外仍是两参数的 `alpha_evidence_check(request, chunk)`：

```python
from backend.services.alpha_business_rules import (
    alpha_clarification_rule,
    build_alpha_evidence_check,
)

workflow = AgentWorkflow(
    retriever=retriever,
    llm_client=llm_client,
    clarification_rule=alpha_clarification_rule,
    evidence_check=build_alpha_evidence_check(
        retriever.get_document_metadata,
        chunk_lookup=retriever.get_parsed_chunk,
    ),
)
```

也可以直接交给 retriever 对象，方法缺失时自动降级：

```python
evidence_check = build_from_retriever(retriever)
```

若组装顺序上不方便传闭包，可先注册再直接用模块级函数：

```python
bind_metadata_lookup(retriever.get_document_metadata)
bind_chunk_lookup(retriever.get_parsed_chunk)

workflow = AgentWorkflow(..., evidence_check=alpha_evidence_check)
```

PR #35 尚未合入 main，本分支不依赖它的代码：`build_from_retriever` 用 `getattr` 取方法，合入后无需改动即可生效。两个方法都是同步、未知对象返回 `None`、成功返回深拷贝，规则侧只读、不修改返回值。

必要时元数据缺失时一律拒绝（`False`）：无法确认文档类型、适用年度、适用范围时宁可证据不足，也不给学生错误结论。

## 5. 与工作流的行为对齐

| 规则返回 | 工作流行为 |
| --- | --- |
| 追问问句 | `needs_clarification`，问句进 `clarifying_question`，`answer=null`，不检索、不调用模型 |
| `None` | 继续检索与证据门禁 |
| 证据 `True` | 保留片段，进入模型选择 |
| 证据 `False` | 剔除片段；全部剔除则 `insufficient_evidence` / `insufficient_data`，引用为空，不调用模型 |

联调测试覆盖上述四条路径（`test_workflow_returns_clarification_before_retrieval`、`test_workflow_rejects_inapplicable_evidence`、`test_workflow_answers_with_applicable_evidence`）。

异常行为以工作流现有实现为准：追问规则抛异常时工作流未做兜底捕获，异常会向上抛给调用方（HTTP 层统一安全拒答）；证据规则在模块内部已捕获异常并返回 `False`，不会让单个片段的判断失败拖垮整轮。

## 6. 测试命令与结果

```
python -m pytest tests/test_alpha_business_rules.py -q
# 63 passed

python -m pytest tests -q
# 234 passed, 77 subtests passed
```

测试覆盖：

- 三个场景的正常追问与信息齐备返回 `None`；
- 每轮只一问（返回值为单个问句）；
- 历史 user 消息补齐字段后不重复追问（含“只说了奖学金、本轮补类别”）；
- 三个场景各有多条证据接受用例；
- 不适用政策被拒绝：跨口径、目录缺失、年度不匹配（含问更早年度）、未来年度、外校资料、已废止版本、未核验时效、专业不符、资格门槛误用复试方案、教师条款回答学生问题、适用范围为空、年度类资料缺元数据；
- 规则异常时返回 `False` 而非放行。

与吴诗莹约定案例的对应测试：

| 案例 | 测试 | 预期 |
| --- | --- | --- |
| 奖学金缺类别 | `test_scholarship_clarification` | 返回类别追问，`needs_clarification`，不检索 |
| 补齐类别 | `test_history_completes_scholarship_category`、`test_history_fills_slots_without_reasking` | 返回 `None`，继续检索 |
| 年度不匹配 | `test_inapplicable_evidence_is_rejected`（2027 院级 / 2026 推免） | `False`，全部剔除后 `insufficient_evidence` |
| 适用范围未知 | `test_unknown_applicability_is_rejected`、`test_lookup_failure_is_treated_as_unknown` | `False` |
| 年度无法确认（缺元数据） | `test_annual_notice_without_metadata_is_rejected`、`test_default_entry_fails_closed_without_metadata` | `False` |
| 局部片段不适用 | `test_teacher_only_section_is_rejected_for_student_question` | 教师条款 `False`，学生条款 `True` |

## 7. 已知限制

1. 工作流当前仍要求 `timeliness_verification_status=current` 才进入生成，业务文档中的“年度已结束按 historical 正常回答”暂时无法端到端落地。本模块对 historical/expired 片段判为适用，等这一门槛放宽后即可生效，不需要再改规则。
2. 只实现 `clarification_rule` 与 `evidence_check` 两个注入点。`answer_mode` 的多分支（historical、procedure_reference）与多事项部分回答仍由工作流的答案组织环节负责，本模块不产出 `AgentResult`。
3. 规则基于关键词与文档类型匹配，不是完整意图识别。遇到无法归类的主题返回 `None` 或 `True`，交由工作流既有门禁与检索相关性处理，不额外拦截其他业务方向的问题。
4. 资料缺口清单沿用业务文档第 7 节，代码不内置政策条件，也不因目录新增而改变分档逻辑。
