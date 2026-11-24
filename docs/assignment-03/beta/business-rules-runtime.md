# Beta 业务规则运行时说明

把 `docs/assignment-03/beta/business-rules.md` 中的判定规则落成可执行代码，供 `AgentWorkflow` 直接调用。本文只说明实现与接口对齐，规则本身以上述业务文档为准，不在代码里新增政策条件。

## 1. 交付内容

| 成果 | 路径 |
| --- | --- |
| 规则实现 | `backend/services/alpha_business_rules.py` |
| 单元测试 | `tests/test_alpha_business_rules.py` |
| 本文档 | `docs/assignment-03/beta/business-rules-runtime.md` |

两个注入函数与既定约定一致：

```python
alpha_clarification_rule(request: AgentRequest) -> str | None
alpha_evidence_check(request: AgentRequest, chunk: RetrievedChunk) -> bool
```

均为同步函数，可直接传入 `AgentWorkflow(clarification_rule=..., evidence_check=...)`（传函数本身，不加括号）。

分支 `feat/beta-business-rules`，基于本轮 main `306c15d`（PR #51 Retriever metadata/chunk lookup contract）；Alpha 规则由已合并的 PR #36 带入，Beta 在本分支按《Beta 冲刺任务书 V2.1》与《Beta 接口规范 V2.1-Final》扩充 S4 与历史政策判断。

## 2. 四个场景的必要字段与追问顺序

追问固定按「事项 → 场景字段」推进，每轮只返回一个问句；信息齐备返回 `None`。

| 场景 | 必要字段 | 追问优先级 |
| --- | --- | --- |
| S1 竞赛认定 | 用途（创新学分 / 综测 / 推免）、赛事名称、获奖级别、获奖等级或排名、个人或集体、前八名（创新学分）、完成人排序（综测）、成果学期与第一署名单位（综测） | 用途 → 赛事名称 → 级别 → 等级 → 个人/集体 → 前八名或排序 → 学期 → 署名单位 |
| S2 奖学金 | 奖学金类别；院级需具体奖项 | 类别 → 院级具体奖项 → 咨询维度 |
| S3 推免 | 咨询对象（校内资格 / 学院复试）、专业与学位类型（问招生计划时） | 年级（个人可能性）→ 咨询对象 → 专业 |
| S4 学院资源 | 资源类别；实验室问题区分研究方向与报名招募；培养方案需专业或年级 | 资源类别 → 实验室目的 / 培养方案专业与年级 |

不追问的两类情况：

- 年度不追问。现行通用政策与库内唯一的年度通知都直接作答，按业务文档 2.5 处理；学生问库外年度（2027 年院级、2028 年推免）直接交给证据判断返回证据不足。
- 资料缺口不追问。查认定目录、查级别归属、问校内推免资格门槛时，追问解决不了缺资料，直接返回 `None`，由证据判断拒绝全部片段。
- S4 不追问年度、学期、姓名、学号与学院。问“学院有哪些实验室”“我能不能进某实验室”“学院办公室电话”时不追问，只按已审核资料回答或返回证据不足。

## 3. 证据适用性判断

`alpha_evidence_check` 先过基础门禁（`retrieval_status=enabled`、`source_verification_status=verified`、时效为 current/historical/superseded/expired、标题非空、发布日期与生效日期不在未来），再检查元数据是否存在、`temporal_notes.human_approved` 是否严格为 `true`、元数据标题/来源/发布方/日期是否与片段一致；任一失败即拒绝。公共门禁通过后按场景与文档类型收紧：

| 场景 | 判定要点 |
| --- | --- |
| S1 | 创新学分只接受《创新创业学分认定办法》与教务处《大学生学科竞赛级别认定结果》；综测加分只接受综评办法与《学生文化科技创新创业奖学金学科竞赛等级目录》。两份目录不是同一份资料：教务处的级别认定不能用来给综测量化分值，国际级、国家级、省部级赛事缺等级目录一律拒绝；校级、院级两档在综评办法里直接写明，不需要等级目录。竞赛级别只看明确写出的奖项级别，“全国大学生数学建模竞赛”这类名称里的“全国”不判为国家级。推免计分口径未入库，不接受任何竞赛类资料 |
| S2 | 校级办法接受校级奖学金与“不具备资格”类通用问题；院级只接受院级与星火通知，且不得用 2026 年通知回答 2027 年及以后；国家奖学金、文化科技创新创业奖学金、社会捐赠类一律拒绝 |
| S3 | 复试（含复试资格审查、材料、招生计划、录取规则）接受学院接收推免的复试方案；推荐资格、排名、遴选接受学院年度推荐资格方案。两类资料不互换：复试方案不能当资格门槛，资格方案也不回答复试环节。其他学院与外校问题一律拒绝 |
| S4 | 元数据 `business_direction_codes` 必须含 `COLLEGE_RESOURCES`，`category_name` 只取六个正式名称（通知与办事渠道、培养方案与课程、实验室与科研团队、研究方向与公开介绍、科研实践与竞赛、学院公开信息与联系方式），不从正文关键词兜底。R1/R2/R3/R5 必须有 `applicability_raw`；R4 公开介绍可不强制；R6 豁免适用对象。问招募只接受 R3，问研究方向只接受 R4；R4 历史介绍不能回答 R3 招募。过期通知可回答“本年度已截止”，但不能回答“现在还剩几个名额” |

S4 来源判定：

- `source_url` 用 `urllib.parse.urlsplit()` 解析，取 `hostname` 与外层白名单做精确相等匹配，禁止 `"fzu.edu.cn" in url`；`scheme` 必须为 `https`，拒绝 userinfo、非 443 端口、非法端口、空 hostname 与包含 `%00` 等异常字符的主机。
- 直连官方主机：`fzu.edu.cn`、`ccds.fzu.edu.cn`、`news.fzu.edu.cn`、`zsks.fzu.edu.cn`、`xwgk.fzu.edu.cn`、`xcb.fzu.edu.cn`；R1 已核验栏目另加 `jwch.fzu.edu.cn`、`stuic.fzu.edu.cn`。其他 `fzu.edu.cn` 子域名需学校官网链接或官方文件佐证后再加入。
- R6 只接受 `ccds.fzu.edu.cn` 的直接公开页面；`news`、`zsks` 不能回答学院办公电话与地址。
- `mp.weixin.qq.com` 不入通用白名单。公众号文章必须从 `temporal_notes` 读取身份核验记录：`wechat_verification`（或 `official_account`）嵌套字典，字段 `verified=true`、`account_name`、`account_id`、`basis` 全部非空；兼容 `wechat_verified` 等扁平键。
- 可认账号仅限学院“福州大学计算机学院”“福大计算机青年”、学校 `ifzu1958`、招生 `fzuzsks`；账号 ID 还必须是资料侧已核实值，名称与 ID 必须同属学院、学校或招生主体，未登记的 `gh_` ID 不通过。学院两个号的真实 ID 未补齐前，生产 `COLLEGE_WECHAT_IDS` 为空，学院公众号文章不通过；单元测试通过 `monkeypatch` 注入 `gh_college` 验证核验逻辑。R6 只认学院两个号；`ifzu1958` 只用于学校新闻语境，`fzuzsks` 只用于招生报考语境。
- 适用字段统一中文五键 `适用年级/适用专业/适用对象/学院/适用届别`，兼容 `grade/major/target` 旧键；同义键值冲突时返回拒绝，不任选其一。

叠加的通用判定，任一命中即拒绝：

- 年度不匹配：年度类资料（院级通知、推免年度方案）只服务其标注的适用年度，问其他年度（无论更早还是更晚）都拒绝；问库外未来年度直接拒绝。适用年度只取 `applicability_raw` 的适用年度/适用届别字段、标题中的「年/届/版」、记录编号中的年份，**不拿发布日期当适用年度**。
- 年度无法确认：年度类资料取不到适用年度时按未知处理，拒绝。
- 年度歧义：元数据标注“年度歧义”（如院级 2026 通知发布年度与正文考核年度不一致）时，不凭记录编号年份认定适用年度，直接拒绝。
- 必要元数据缺失：拿不到 `DocumentMetadata`，或按场景要求 `applicability_raw` 却为空时，无法确认文档类型、适用范围与年度，拒绝；不因“片段内容看起来相关”而放行。
- 历史政策分层：`historical`/`expired` 只在历史问题中放行，问“现在/今年/最新”一律拒绝；`superseded` 只在明确问旧办法时放行，并须说明已被替代；`policy_status` 写明无法确认是否为现行版本时拒绝。
- 截止日期已过且问“现在还能不能办”拒绝（“还能”“现在还”“办理窗口”这类表述）；问历史通知里的条件或时间点本身不拒绝。专业、年级、学院与资料适用范围不符拒绝。
- 局部章节不适配：同一文件里教师绩效/师资条款不能回答学生问题，学生条款也不能回答教师问题，依据 `ParsedChunk.locator_note` 判断。
- 章节无法确认：正文同时含教师条款与学生条款的资料（常量 `_SECTION_SENSITIVE`，当前登记《创新创业学分认定管理实施办法》与 2026 年“星火奖教奖学金”评选通知），必须能从 `locator_note` 或 `locator` 看出属于教师节还是学生节，否则拒绝；“第 7 条”这类泛化定位不算确认。
- 章节按层级切分判断：`heading_path` 与 `locator` 用 `|` 切段后逐段匹配，先把总标题里的复合词「奖教奖学金」剔除，再判定「奖教金」为教师节、「奖学金」为学生节，不用裸「奖学金」子串扫整段。教师节（奖教金）一律不用于学生问答；总通知段（款项使用、评选安排、材料报送）不区分师生，只在办理流程类问题（材料、报送、截止时间、流程）放行，问条件、金额、名额一律拒绝。

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

#35 已合入 main，`build_from_retriever` 直接用 `getattr` 取 `get_document_metadata` 与 `get_parsed_chunk`，无需额外适配。两个方法都是同步、未知对象返回 `None`、成功返回深拷贝，规则侧只读、不修改返回值。

必要时元数据缺失时一律拒绝（`False`）：无法确认文档类型、适用年度、适用范围时宁可证据不足，也不给学生错误结论。

适用范围字段按 PR #31 的实际元数据统一映射（不只看“适用年级/适用专业/适用对象”）：

| 语义 | 取值键（按顺序取第一个非空） |
| --- | --- |
| 年级 | 适用年级、年级、学生对象、对象、适用对象、招生对象 |
| 专业 | 适用专业、专业、招生专业 |
| 对象 | 适用对象、对象、学生对象、招生对象 |
| 学院 | 学院、适用学院、所属学院 |
| 年度 | 适用年度、适用届别、适用学年、适用年份、目标届别、年度 |

年度歧义键（`年度歧义`）非空时不参与年度推断，直接拒绝。学院字段只服务本院，问其他学院（数学与统计、外国语、经济与管理等）一律拒绝。

章节说明的两种形态都支持：`locator_note` 为纯文本时直接匹配；为 JSON 字符串时解析 `heading_path`（也兼容 `heading` / `section` / `path` / `title` 键），并叠加 `chunk.locator` 一起判断。王智洋确认 `get_parsed_chunk` 对不存在、未开放（blocked/review_only）或重索引剔除的 chunk 统一返回 `None`，不会抛异常，与本模块“取不到章节即拒绝”的处理一致。

## 4.1 多轮对话的时间隔离

时间判断不拼全部历史。`_temporal_text()` 以本轮 `query` 的明确时间意图优先：本轮写了年份、今年/去年/前年、现在/目前/当前或“当时/去年/以前”，就只用本轮文本；只有本轮完全没写时间时，才回退到最近一条带时间意图的历史 user 消息，用作未明确槽位的补充。

这样处理两类污染：第一轮问 2025、第二轮问 2024 时，不会因为历史文本同时含 2025 而让 2025 资料通过；第一轮问“2026 年当时招几个”、第二轮问“现在还剩几个名额”时，历史里的“当时”不会让当前名额检查失效。反过来，本轮问历史人数也不会被上一轮的“现在”拦住。

## 4.2 S4 R3 的年度适用性

`_check_resources()` 对 `doc_kind=RES_LAB` 的 R3 招募通知增加年度匹配：问题写了明确年度（含今年、去年、前年）时，必须命中 `_document_year(facts)`，同年度放行，跨年度拒绝；问题没写年度时不额外卡年份。R4 研究方向与公开介绍、R6 学院公开信息与联系方式不套用年度通知规则。

同一函数末尾的旧资料判断也统一使用 `_temporal_text()`：`SUPERSEDED` 只在本轮明确问历史时放行；`HISTORICAL`/`EXPIRED` 的联系方式、培养方案在本轮写“现在/目前/当前”时拒绝。历史消息仍可补本轮没写的时间槽位，但不能把本轮当前问题伪装成历史问句。

## 5. 与工作流的行为对齐

| 规则返回 | 工作流行为 |
| --- | --- |
| 追问问句 | `needs_clarification`，问句进 `clarifying_question`，`answer=null`，不检索、不调用模型 |
| `None` | 继续检索与证据门禁 |
| 证据 `True` | 保留片段，进入模型选择 |
| 证据 `False` | 剔除片段；全部剔除则 `insufficient_evidence` / `insufficient_data`，引用为空，不调用模型 |

联调测试覆盖上述四条路径（`test_workflow_returns_clarification_before_retrieval`、`test_workflow_rejects_inapplicable_evidence`、`test_workflow_answers_with_applicable_evidence`）。

按吴诗莹对齐后的工作流行为：追问规则抛异常时返回 `insufficient_evidence`（`answer_mode=insufficient_data`，警告码 `CLARIFICATION_RULE_FAILED`），不检索、不调用模型；证据规则在模块内部已捕获异常并返回 `False`，单个片段判断失败不影响其他片段。

本分支基于 main `306c15d`，当前 main 工作流尚未包含上述兜底捕获，因此测试 `test_clarification_error_is_safely_rejected` 同时兼容两种实现：异常上抛（调用方拒答）或工作流返回 `insufficient_evidence` + `CLARIFICATION_RULE_FAILED`；两种路径都断言未触发检索与模型调用。

## 6. 测试命令与结果

```
python -m pytest tests/test_alpha_business_rules.py -q
# 176 passed

TMPDIR=/private/tmp/codemind-test python -m pytest tests -q
# 424 passed, 27 skipped, 136 subtests passed（main 306c15d + 本分支改动）
# 说明：macOS 默认 TMPDIR 下 test_alpha_corpus 的符号链接用例会误报 1 项；
# 指定普通目录（TMPDIR=/private/tmp/codemind-test）后全量全过。
```

测试覆盖：

- 四个场景的正常追问与信息齐备返回 `None`；
- 每轮只一问（返回值为单个问句）；
- 历史 user 消息补齐字段后不重复追问（含“只说了奖学金、本轮补类别”）；
- 三个场景各有多条证据接受用例；
- 不适用政策被拒绝：跨口径、目录缺失、年度不匹配（含问更早年度）、未来年度、外校资料、已废止版本、未核验时效、专业不符、资格门槛误用复试方案、教师条款回答学生问题、适用范围为空、年度类资料缺元数据；
- 规则异常时返回 `False` 而非放行；
- 追问规则异常时不产出政策答案，且不触发检索与模型调用（兼容 `CLARIFICATION_RULE_FAILED` 与异常上抛两种实现）；
- 章节敏感资料缺章节定位时拒绝，非章节敏感资料不受影响；
- 两份竞赛目录拆分：教务处级别认定只答创新学分，综测定档需学科竞赛等级目录；
- 推免复试资格审查归复试环节，推荐资格方案与复试方案互不顶替；
- 第一署名与学期区分肯定/否定/未说明，否定与已说明不再追问；
- 排名支持第九名及以后，已说明排名不再重复追问前八名；
- 院级年度歧义、其他学院问题按无法确认拒绝；
- 星火文件按 `heading_path` 三段区分：总通知段只在流程类问题放行，奖教金段一律拒绝，奖学金段放行；JSON 形态的 `locator_note` 可解析，总标题里的「奖教奖学金」不会被误判为学生节；同时标注教师与学生的共同条款可回答学生问题（ROLE_SHARED）；
- 综测的学期与第一署名要求对个人项目同样生效，个人参赛不再跳过这两项检查；
- 创新学分缺作品名称时先追问作品（`QUESTION_WORK_NAME`），且排在级别、等级追问之前；
- 推免的专业与学位类型分开追问，分组、材料投递、名额、调剂、录取等复试细节都先确认专业再确认学位类型；
- `2024级` 等入学年级按“入学年 + 4”折算届别后与目标届别比对，追问阶段与证据判断使用同一套届别口径；
- 专业按明确名称或别名映射匹配，不再用“计算机相关专业”的大范围放行（如电子信息工程问 2027 届推荐资格直接拒绝）；
- 竞赛名称含「全国」不等于国家级：「全国大学生数学建模竞赛省赛二等奖」判为省部级；
- 历史对话切换主题不影响本轮场景识别：场景优先按本轮提问判断，历史只在必要时补充字段；
- 历史/已过期通知的截止时间与办理状态仍可作为历史信息回答，不因截止日期已过而丢弃；但现行资料问“现在还能不能办”依旧拒绝；
- 候选资料在 `review_only`、`blocked` 状态下不进入回答（覆盖 #31 真实资料状态）；
- 同一会话换竞赛：本轮写明的级别、个人/集体、作品优先，历史只补本轮没说的槽位（换竞赛后旧作品不再沿用）；
- 同一会话在复试与推荐资格之间切换：推免子场景按本轮问题判断，复试问题不追问年级；
- 校级、院级综测只认综合素质评价办法，学科竞赛等级目录只负责国际级/国家级/省部级；
- 级别否定与转折表达（“不是国家级，是省级二等奖”）按转折后的级别识别；
- 团队识别要求明确表述（团队、集体、我们组、队友等），“我们”单独出现不算团队；
- 历史/过期通知：问历史截止时间放行，问“现在还能不能申请”拒绝；
- 年级口径区分正式资格与参考说明：#31 的“大一至大三仅升学准备参考”不再让低年级通过正式推荐资格，只有准备、流程类问题按参考口径放行；
- 排名不跨竞赛、不跨作品继承：历史排名只在本轮未说、且同一竞赛同一作品时复用；
- 追问与证据判断共用时间源，`alpha_clarification_rule` 支持注入 `today`；
- 明确指定年级或专业、但资料缺少对应适用范围字段时 fail-closed，不因为句子里没有第一人称而放行；
- 作品标识除书名号外，也识别“作品名称叫 XXX”“项目名称是 XXX”等无书名号写法，跨作品排名同样不继承；
- 正式资格、排名、遴选、能否申请等意图优先于“提前/准备”等参考性关键词，低年级不能借准备说法通过正式资格；
- 资料没有学院字段时，明确询问其他学院同样拒绝；
- 历史排名只在“本轮同一竞赛 + 本轮明确同一作品”时继承，本轮未说作品也重新追问；
- S4 六类资源识别：只说“学院有什么资源”追问类别，实验室只说名称追问研究方向还是报名，培养方案未说专业与年级追问范围；
- S4 证据门禁：缺 `COLLEGE_RESOURCES`、`category_name` 未登记、缺 `applicability_raw`、R4 历史介绍回答招募、过期通知回答当前名额、非官方来源或 R6 非 `ccds.fzu.edu.cn`、公众号未核验，全部拒绝；
- S4 跨轮上下文：上一轮问实验室、本轮“EDA 那个招几个”不丢类别；本轮切到办公室电话时不继承实验室资料；
- 历史政策分层：历史通知只答历史问题，问“现在”拒绝；已被替代的旧办法只在明确问旧办法时放行；无法确认现行版本时拒绝；
- 元数据异常：读取异常、人工审核非严格 `true`、标题与片段不一致，全部 `False`。

与吴诗莹约定案例的对应测试：

| 案例 | 测试 | 预期 |
| --- | --- | --- |
| 奖学金缺类别 | `test_scholarship_clarification` | 返回类别追问，`needs_clarification`，不检索 |
| 补齐类别 | `test_history_completes_scholarship_category`、`test_history_fills_slots_without_reasking` | 返回 `None`，继续检索 |
| 年度不匹配 | `test_inapplicable_evidence_is_rejected`（2027 院级 / 2026 推免） | `False`，全部剔除后 `insufficient_evidence` |
| 适用范围未知 | `test_unknown_applicability_is_rejected`、`test_lookup_failure_is_treated_as_unknown` | `False` |
| 年度无法确认（缺元数据） | `test_annual_notice_without_metadata_is_rejected`、`test_default_entry_fails_closed_without_metadata` | `False` |
| 局部片段不适用 | `test_teacher_only_section_is_rejected_for_student_question` | 教师条款 `False`，学生条款 `True` |

## 6.1 与 #31 / #32 / #35 的接口联调（历史记录）

#31、#35、#36 与 Agent 集成相关 PR 曾以 main `9016441` 为基线完成联调，以下是该基线的历史记录；本分支当前基于 `306c15d`，接口签名未变。以 `9016441` 的 `backend/retrieval/local.py` 的 `LocalBM25Retriever` 签名为准：`retrieve(request)`、`get_document_metadata(version_id)`、`get_parsed_chunk(chunk_id)`，后两者对 `review_only`/`blocked` 返回 `None`。`build_from_retriever` 用 `getattr` 取方法，签名与 `MetadataLookup`/`ChunkLookup` 一致，可直接注入。

以 `9016441` 的 `backend/services/agent_workflow.py` 与 #32 `feat/alpha-agent-integration`（`e46e745`）的 `AgentWorkflow` 分别做注入联调，结果一致：

| 场景 | 结果 |
| --- | --- |
| 推免复试问名额，未说学位类型 | `needs_clarification`，检索调用 0 |
| #31 推免资料 `review_only`（元数据查询返回 `None`） | `insufficient_evidence` / `NO_ELIGIBLE_EVIDENCE`，引用 0 |
| 校级综测 + 综评办法（enabled） | `answered`，引用 1 |
| 过期通知问历史截止 | 规则层 `True`；#32 端到端仍 `NO_ELIGIBLE_EVIDENCE` |
| 过期通知问“现在还能申请” | 规则层 `False` |

最后一项是 #32 `_eligible` 仍要求 `timeliness=current` 的已知门槛，需由 #32 统一放宽后才能端到端回答历史通知。

## 7. 已知限制

1. 工作流当前仍要求 `timeliness_verification_status=current` 才进入生成，业务文档中的“年度已结束按 historical 正常回答”暂时无法端到端落地。本模块对 historical/expired 片段判为适用，等这一门槛放宽后即可生效，不需要再改规则。
2. 只实现 `clarification_rule` 与 `evidence_check` 两个注入点。`answer_mode` 的多分支（historical、procedure_reference）与多事项部分回答仍由工作流的答案组织环节负责，本模块不产出 `AgentResult`。
3. 规则基于关键词与文档类型匹配，不是完整意图识别。Beta 起未识别场景直接返回 `False`，不再走 `scenario is None -> True` 的旁路；这会扩大对库外主题的拒答范围，属有意收紧。
4. 资料缺口清单沿用业务文档第 8 节，代码不内置政策条件，也不因目录新增而改变分档逻辑。
