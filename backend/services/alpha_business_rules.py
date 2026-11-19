"""Alpha 业务规则：主动追问与证据适用性判断。

规则来源为 `docs/assignment-03/alpha/business-rules.md`（已在 PR #29 合并），
本模块只做规则的代码化落地，不新增状态值、不修改公共契约字段。

两个注入点由 `AgentWorkflow` 调用：

- `alpha_clarification_rule(request) -> str | None`：信息不足时返回单个问句。
- `alpha_evidence_check(request, chunk) -> bool`：判断片段是否适用于当前问题。

`RetrievedChunk` 不含 `applicability_raw` / `deadline_on` / `record_code`，
这些字段位于 `DocumentMetadata`，局部章节说明位于 `ParsedChunk.locator_note`。
证据判断通过两个可选查询函数取得，由组装层把同一个 retriever 实例传进来：

```python
evidence_check = build_alpha_evidence_check(
    retriever.get_document_metadata,
    chunk_lookup=retriever.get_parsed_chunk,
)
```

也可以先 `bind_metadata_lookup(...)` / `bind_chunk_lookup(...)`，再直接使用两参数
的 `alpha_evidence_check(request, chunk)`。元数据缺失、年度无法确认或适用范围
无法确认时一律返回 `False`，不放行。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from backend.contracts.models import (
    AgentRequest,
    DocumentMetadata,
    LLMRole,
    ParsedChunk,
    RetrievalStatus,
    RetrievedChunk,
    SourceVerificationStatus,
    TimelinessVerificationStatus,
)

MetadataLookup = Callable[[UUID], DocumentMetadata | None]
ChunkLookup = Callable[[UUID], ParsedChunk | None]
EvidenceCheck = Callable[[AgentRequest, RetrievedChunk], bool]

# 场景与用途标签（仅本模块内部使用，不写入公共契约）
COMPETITION = "competition"
SCHOLARSHIP = "scholarship"
RECOMMENDATION = "recommendation"

PURPOSE_CREDIT = "innovation_credit"
PURPOSE_EVALUATION = "comprehensive_evaluation"
PURPOSE_RECOMMENDATION = "recommendation"

QUALIFICATION = "qualification"
REVIEW = "review"

# 追问文案与业务文档 4.3 / 5.3 / 6.3 保持一致
QUESTION_TOPIC = "请问你具体咨询哪项学校政策或办理事项？"
QUESTION_PURPOSE = "你想了解的是创新学分认定、综测加分，还是推免相关？"
QUESTION_COMPETITION_NAME = "请说一下竞赛全称，例如全国大学生数学建模竞赛。"
QUESTION_LEVEL = "这个奖是国家级、省部级还是校级？"
QUESTION_AWARD_GRADE = "获得的是特等奖、一等奖、二等奖还是三等奖？"
QUESTION_FORMAT = "这是个人参赛还是团队作品？"
QUESTION_TOP_EIGHT = "团队作品里你排第几？创新学分只认定排名前八名成员。"
QUESTION_ORDER = "你在完成人里排第几？综测团体项目按排序系数计算。"
QUESTION_SEMESTER = "这份成果是哪个学期取得的？综测只计上一学期内的成果。"
QUESTION_FIRST_UNIT = "这份成果是否以福州大学为第一署名单位？"
QUESTION_SCHOLARSHIP_CATEGORY = (
    "你想问的是校级优秀学生综合奖学金、国家奖学金，还是学院层面的院级奖学金？"
)
QUESTION_SCHOLARSHIP_DIMENSION = "你想了解申请条件、所需材料，还是评定时间？"
QUESTION_DEPT_AWARD = "院级奖学金里你关注哪一类？学科竞赛类、学术类、学业类还是学生工作类？"
QUESTION_RECOMMENDATION_OBJECT = "你想问的是校内推免资格怎么获得，还是学院接收推免的复试安排？"
QUESTION_PROFESSION = "你关注的是哪个专业？学术型、专业型还是直博？"
QUESTION_GRADE = "你现在是大几？不同年级参考的年度通知不同。"

_COMPETITION_TOPIC = re.compile(
    r"竞赛|比赛|大赛|挑战杯|数学建模|蓝桥杯|获奖|奖项|(?<!学)奖(?!学金)"
    r"|创新学分|学分认定|综测加分|综测里|综测能加|加几分|能加多少分"
)
_RECOMMENDATION_TOPIC = re.compile(r"推免|保研|免试攻读|直博")
_SCHOLARSHIP_TOPIC = re.compile(r"奖学金|助学金|奖助|单项奖|励志奖")

_PURPOSE_CREDIT = re.compile(r"创新学分|学分认定|认定多少学分|原始分")
_PURPOSE_EVALUATION = re.compile(r"综测|综合素质测评|综合素质评价|加几分|加分")

_LEVELS = (
    ("international", re.compile(r"国际级|国际性|国际竞赛")),
    ("national", re.compile(r"国家级|全国")),
    ("provincial", re.compile(r"省部级|省级|省赛|赛区")),
    ("school", re.compile(r"校级|学校级")),
    ("college", re.compile(r"院级|学院级")),
)
_LEVEL_LOOKUP_QUESTION = re.compile(r"认定目录|是否属于.*认定|属于哪一?级别|什么级别|在哪一级")
_AWARD_GRADE = re.compile(
    r"特等|一等|二等|三等|金奖|银奖|铜奖|单项奖|最高等级奖|次高等级奖|第三等级奖"
)
_TEAM = re.compile(r"团队|集体|我们|合作|组队")
_INDIVIDUAL = re.compile(r"个人参赛|个人项目|独立完成|一个人")
_RANK = re.compile(r"第([一二三四五六七八1-8])完成人|第([一二三四五六七八1-8])名|排名第([一二三四五六七八1-8])")
_ORDER = re.compile(r"第[一二三四五六七八1-8]完成人|完成人排序|排序第")
_SEMESTER = re.compile(r"上一学期|上学期|本学期|这学期|学年")
_FIRST_UNIT = re.compile(r"第一署名|署名单位|福州大学为第一")

_SCHOLARSHIP_NATIONAL = re.compile(r"国家奖学金|国家励志|励志奖学金")
_SCHOLARSHIP_CULTECH = re.compile(r"文化科技创新创业奖学金")
_SCHOLARSHIP_SOCIAL = re.compile(r"宝钢|社会捐赠|捐赠奖学金")
_SCHOLARSHIP_DEPT = re.compile(
    r"院级|学院层面的奖学金|学院奖学金|爱国者之星|爱国者奖学金|星火|UPTOP|荣耀计算机"
)
_SCHOLARSHIP_SCHOOL = re.compile(
    r"优秀学生综合奖学金|综合奖学金|单项奖学金|学习进步奖|精神文明建设奖"
)
_DEPT_AWARD = re.compile(
    r"爱国者之星|爱国者奖学金|星火|UPTOP|荣耀计算机|学科竞赛类|学术类|学业类|学生工作类"
)
_ELIGIBILITY_QUESTION = re.compile(r"没有资格|不具备资格|不能申请|取消资格|还能.*吗|能不能评|能否评")
_NO_ELIGIBILITY = re.compile(r"没有资格|不具备资格|不能申请|取消资格")
_DISQUALIFYING_SITUATION = re.compile(r"挂科|挂了|不及格|处分|休学|保留学籍|重修|补考")
_SCHOLARSHIP_DIMENSION = re.compile(
    r"条件|要求|资格|金额|多少钱|名额|材料|时间|什么时候|截止|流程|怎么申请|比例"
)

_RECOMMENDATION_REVIEW = re.compile(r"复试|面试|机试|材料|招生|名额|招多少|录取|直博|专业")
_RECOMMENDATION_QUALIFICATION = re.compile(r"资格|排名|遴选|推荐办法|加分|名额分配")
_PLAN_QUESTION = re.compile(r"招多少|招生计划|招几人|多少人|名额")
_PROFESSION = re.compile(
    r"计算机科学与技术|计算机技术|软件工程|人工智能|数据科学|信息安全|网络空间|数学|金融|经济"
)
# 同一学科门类下的相近专业名称（如“计算机技术”与“计算机科学与技术”）
_CS_FAMILY = re.compile(r"计算机|软件|人工智能|数据科学|信息安全|网络空间")
_GRADE = re.compile(r"大[一二三四]|[一二三四]年级|20\d{2}\s*级")
_PERSONAL = re.compile(r"我(?!们)|本人|我自己")
_EXTERNAL_SCHOOL = re.compile(r"其他学院|别的学院|外校|其他学校|别的学校")

_KIND_CREDIT = "credit_bylaw"
_KIND_EVALUATION = "evaluation_bylaw"
_KIND_SCHOLARSHIP = "scholarship_bylaw"
_KIND_DEPT_SCHOLARSHIP = "dept_scholarship"
_KIND_RECOMMENDATION = "recommendation_review"
_KIND_CATALOG = "competition_catalog"
_KIND_EVENT = "event_notice"
_KIND_COURSE = "course_rules"
_KIND_OTHER = "other"

_YEAR = re.compile(r"(20\d{2})\s*(?:年|届)")
_ACADEMIC_YEAR_RANGE = re.compile(r"20\d{2}\s*[-—–至]\s*20\d{2}\s*学年?")

_lookup: MetadataLookup | None = None
_chunk_lookup: ChunkLookup | None = None


@dataclass(frozen=True)
class _DocumentFacts:
    record_code: str | None
    title: str
    applicability: dict[str, str] | None
    deadline: date | None
    has_metadata: bool
    has_metadata: bool = False


def bind_metadata_lookup(lookup: MetadataLookup | None) -> None:
    """注册元数据查询函数（通常为 retriever.get_document_metadata）。"""
    global _lookup
    _lookup = lookup


def bind_chunk_lookup(lookup: ChunkLookup | None) -> None:
    """注册片段查询函数（通常为 retriever.get_parsed_chunk），用于读取 locator_note。"""
    global _chunk_lookup
    _chunk_lookup = lookup


def build_alpha_evidence_check(
    metadata_lookup: MetadataLookup | None = None,
    *,
    chunk_lookup: ChunkLookup | None = None,
    today: Callable[[], date] = date.today,
) -> EvidenceCheck:
    """用闭包绑定 retriever 的只读查询方法，保持 `(request, chunk) -> bool` 签名。

    ```python
    evidence_check = build_alpha_evidence_check(
        retriever.get_document_metadata,
        chunk_lookup=retriever.get_parsed_chunk,
    )
    ```
    """

    def check(request: AgentRequest, chunk: RetrievedChunk) -> bool:
        return _assess(request, chunk, metadata_lookup, chunk_lookup, today())

    return check


def build_from_retriever(
    retriever: object,
    *,
    today: Callable[[], date] = date.today,
) -> EvidenceCheck:
    """直接从 retriever 对象取两个查询方法；缺失的方法按 None 处理。"""
    metadata = getattr(retriever, "get_document_metadata", None)
    parsed = getattr(retriever, "get_parsed_chunk", None)
    return build_alpha_evidence_check(
        metadata if callable(metadata) else None,
        chunk_lookup=parsed if callable(parsed) else None,
        today=today,
    )


def alpha_clarification_rule(request: AgentRequest) -> str | None:
    """必要信息不足时返回单个追问问句，信息齐备时返回 None。"""
    text = _user_text(request)
    scenario, _ = _analyse(text)
    if scenario is None:
        return QUESTION_TOPIC
    if scenario == COMPETITION:
        return _clarify_competition(text)
    if scenario == SCHOLARSHIP:
        return _clarify_scholarship(text)
    return _clarify_recommendation(text)


def alpha_evidence_check(request: AgentRequest, chunk: RetrievedChunk) -> bool:
    """默认入口；查询函数来自 `bind_metadata_lookup` / `bind_chunk_lookup`。"""
    return _assess(request, chunk, _lookup, _chunk_lookup, date.today())


# --------------------------------------------------------------------------- 文本解析


def _user_text(request: AgentRequest) -> str:
    previous = [turn.content for turn in request.history if turn.role == LLMRole.USER]
    return "\n".join([*previous, request.query]).strip()


def _analyse(text: str) -> tuple[str | None, str | None]:
    competition = _COMPETITION_TOPIC.search(text)
    recommendation = _RECOMMENDATION_TOPIC.search(text)
    scholarship = _SCHOLARSHIP_TOPIC.search(text)
    purpose = _purpose(text)
    # 奖学金名称里也常带“学科竞赛类”等字样，只有明确问创新学分或综测加分
    # 才按竞赛认定处理，否则仍归奖学金场景。
    if competition and scholarship:
        return (
            (COMPETITION if purpose in {PURPOSE_CREDIT, PURPOSE_EVALUATION} else SCHOLARSHIP),
            purpose,
        )
    if competition:
        return COMPETITION, purpose
    if scholarship:
        return SCHOLARSHIP, None
    if recommendation:
        return RECOMMENDATION, None
    return None, None


def _purpose(text: str) -> str | None:
    if _PURPOSE_CREDIT.search(text):
        return PURPOSE_CREDIT
    if _PURPOSE_EVALUATION.search(text):
        return PURPOSE_EVALUATION
    if _RECOMMENDATION_TOPIC.search(text):
        return PURPOSE_RECOMMENDATION
    return None


def _level(text: str) -> str | None:
    for name, pattern in _LEVELS:
        if pattern.search(text):
            return name
    return None


def _award_grade(text: str) -> str | None:
    match = _AWARD_GRADE.search(text)
    return match.group() if match else None


def _team(text: str) -> bool | None:
    if _TEAM.search(text):
        return True
    if _INDIVIDUAL.search(text):
        return False
    return None


def _rank(text: str) -> int | None:
    match = _RANK.search(text)
    if not match:
        return None
    token = next(group for group in match.groups() if group)
    return int(token) if token.isdigit() else "一二三四五六七八".index(token) + 1


def _years(text: str) -> set[int]:
    cleaned = _ACADEMIC_YEAR_RANGE.sub(" ", text)
    return {int(year) for year in _YEAR.findall(cleaned)}


def _future_year(text: str, *, today: date) -> bool:
    if re.search(r"下一届|下届|明年|下一轮", text):
        return True
    years = _years(text)
    return bool(years) and max(years) > today.year


def _scholarship_category(text: str) -> str | None:
    if _SCHOLARSHIP_NATIONAL.search(text):
        return "national"
    if _SCHOLARSHIP_CULTECH.search(text):
        return "cultech"
    if _SCHOLARSHIP_SOCIAL.search(text):
        return "social"
    if _SCHOLARSHIP_DEPT.search(text):
        return "dept"
    if _SCHOLARSHIP_SCHOOL.search(text):
        return "school"
    return None


def _recommendation_object(text: str) -> str | None:
    if _RECOMMENDATION_QUALIFICATION.search(text):
        return QUALIFICATION
    if _RECOMMENDATION_REVIEW.search(text):
        return REVIEW
    return None


# --------------------------------------------------------------------------- 追问规则


def _clarify_competition(text: str) -> str | None:
    # 查目录、查级别归属属于资料缺口，追问解决不了，交给证据判断。
    if _LEVEL_LOOKUP_QUESTION.search(text):
        return None
    purpose = _purpose(text)
    if purpose is None:
        return QUESTION_PURPOSE
    if purpose == PURPOSE_RECOMMENDATION:
        return None
    # 综测加分依赖《学科竞赛等级目录》定档；国家级与省部级无法定类，
    # 补齐个人/集体也仍然无法给出分值，直接走证据不足。
    if purpose == PURPOSE_EVALUATION and _level(text) in {
        "international", "national", "provincial",
    }:
        return None
    if not re.search(r"竞赛|比赛|大赛|杯|赛区", text):
        return QUESTION_COMPETITION_NAME
    if _level(text) is None:
        return QUESTION_LEVEL
    if _award_grade(text) is None and _rank(text) is None:
        return QUESTION_AWARD_GRADE
    team = _team(text)
    if team is None:
        return QUESTION_FORMAT
    if team and purpose == PURPOSE_CREDIT:
        rank = _rank(text)
        if rank is None or rank > 8:
            return QUESTION_TOP_EIGHT
    if team and purpose == PURPOSE_EVALUATION:
        if not _ORDER.search(text):
            return QUESTION_ORDER
        if not _SEMESTER.search(text):
            return QUESTION_SEMESTER
        if not _FIRST_UNIT.search(text):
            return QUESTION_FIRST_UNIT
    return None


def _clarify_scholarship(text: str) -> str | None:
    # 库外年度直接证据不足，不追问年度（2.5）。
    if _future_year(text, today=date.today()):
        return None
    category = _scholarship_category(text)
    if category is None:
        # 通用资格问题（处分、挂科、休学等）由校级办法直接覆盖，不问类别。
        if _NO_ELIGIBILITY.search(text):
            return None
        if _ELIGIBILITY_QUESTION.search(text) and _DISQUALIFYING_SITUATION.search(text):
            return None
        return QUESTION_SCHOLARSHIP_CATEGORY
    if category == "dept" and not _DEPT_AWARD.search(text):
        return QUESTION_DEPT_AWARD
    if (
        not _SCHOLARSHIP_DIMENSION.search(text)
        and not _PERSONAL.search(text)
        and len(re.sub(r"[\s，。？！,.?!]", "", text)) <= 20
    ):
        return QUESTION_SCHOLARSHIP_DIMENSION
    return None


def _clarify_recommendation(text: str) -> str | None:
    if _future_year(text, today=date.today()) or _EXTERNAL_SCHOOL.search(text):
        return None
    if _PERSONAL.search(text) and not _GRADE.search(text):
        return QUESTION_GRADE
    obj = _recommendation_object(text)
    if obj is None:
        return QUESTION_RECOMMENDATION_OBJECT
    if obj == REVIEW and _PLAN_QUESTION.search(text) and not _PROFESSION.search(text):
        return QUESTION_PROFESSION
    return None


# --------------------------------------------------------------------------- 证据判断


def _assess(
    request: AgentRequest,
    chunk: RetrievedChunk,
    lookup: MetadataLookup | None,
    chunk_lookup: ChunkLookup | None,
    today: date,
) -> bool:
    try:
        text = _user_text(request)
        facts = _document_facts(chunk, lookup)
        if not _basic_gates(chunk, today):
            return False
        if _EXTERNAL_SCHOOL.search(text):
            return False
        scenario, purpose = _analyse(text)
        if scenario is None:
            return True
        # 三个场景都要确认文档类型与适用范围；缺元数据即视为无法确认。
        if not facts.has_metadata:
            return False
        if not facts.applicability:
            return False
        kind = _classify(facts)
        if _applicability(text, facts) is False:
            return False
        if not _section_applies(text, chunk, chunk_lookup):
            return False
        if _year_conflict(text, kind, facts, today):
            return False
        if _deadline_conflict(text, facts, today):
            return False
        if scenario == COMPETITION:
            return _check_competition(text, purpose, kind)
        if scenario == SCHOLARSHIP:
            return _check_scholarship(text, kind, today)
        return _check_recommendation(text, kind)
    except Exception:
        # 规则无法判断时按“无法确认适用性”处理，不能放行。
        return False


def _basic_gates(chunk: RetrievedChunk, today: date) -> bool:
    if chunk.retrieval_status != RetrievalStatus.ENABLED:
        return False
    if chunk.source_verification_status != SourceVerificationStatus.VERIFIED:
        return False
    if chunk.timeliness_verification_status not in {
        TimelinessVerificationStatus.CURRENT,
        TimelinessVerificationStatus.HISTORICAL,
        TimelinessVerificationStatus.EXPIRED,
    }:
        return False
    if not chunk.content.strip() or not chunk.title.strip():
        return False
    for value in (chunk.published_on, chunk.effective_on):
        if value is not None and value > today:
            return False
    return True


def _check_competition(text: str, purpose: str | None, kind: str) -> bool:
    if _LEVEL_LOOKUP_QUESTION.search(text):
        return kind == _KIND_CATALOG
    if purpose == PURPOSE_RECOMMENDATION:
        return False
    if purpose == PURPOSE_CREDIT:
        return kind in {_KIND_CREDIT, _KIND_CATALOG}
    if purpose == PURPOSE_EVALUATION:
        level = _level(text)
        if level is None:
            return False
        if level in {"international", "national", "provincial"}:
            # 没有等级目录就无法确定 A+/A/A-/B/C 档，不能拿分档表充当结论。
            return kind == _KIND_CATALOG
        return kind in {_KIND_EVALUATION, _KIND_CATALOG}
    return False


def _check_scholarship(text: str, kind: str, today: date) -> bool:
    category = _scholarship_category(text)
    if category is None:
        return kind == _KIND_SCHOLARSHIP
    if category in {"national", "cultech", "social"}:
        # 国家层面办法、实施细则与捐赠设立规定均未入库。
        return False
    if category == "dept":
        if _future_year(text, today=today):
            return False
        return kind == _KIND_DEPT_SCHOLARSHIP
    return kind == _KIND_SCHOLARSHIP


def _check_recommendation(text: str, kind: str) -> bool:
    obj = _recommendation_object(text)
    if obj == QUALIFICATION or (obj is None and _PERSONAL.search(text)):
        # 校内推免资格推荐办法未入库，复试方案不能代替资格门槛。
        return False
    return kind == _KIND_RECOMMENDATION


# --------------------------------------------------------------------------- 元数据与适用范围


def _section_applies(
    text: str,
    chunk: RetrievedChunk,
    chunk_lookup: ChunkLookup | None,
) -> bool:
    """按 locator_note 区分同一文件里的局部章节（如教师条款与学生条款）。"""
    if chunk_lookup is None:
        return True
    try:
        parsed = chunk_lookup(chunk.chunk_id)
    except Exception:
        return True
    note = getattr(parsed, "locator_note", None) if parsed is not None else None
    if not note:
        return True
    teacher = bool(re.search(r"教师|教职工|师资|绩效", note))
    student = bool(re.search(r"学生|本科生|研究生|同学", note))
    if teacher and not student and "教师" not in text:
        return False
    if student and not teacher and re.search(r"教师|教职工", text):
        return False
    return True


def _document_facts(chunk: RetrievedChunk, lookup: MetadataLookup | None) -> _DocumentFacts:
    metadata = None
    if lookup is not None:
        try:
            metadata = lookup(chunk.version_id)
        except Exception:
            metadata = None
    if metadata is not None and not isinstance(metadata, DocumentMetadata):
        metadata = None
    if metadata is not None:
        applicability = metadata.applicability_raw
        if applicability is not None:
            applicability = {str(key): str(value) for key, value in applicability.items()}
        return _DocumentFacts(
            record_code=metadata.record_code,
            title=metadata.title,
            applicability=applicability,
            deadline=metadata.deadline_on,
            has_metadata=True,
        )
    return _DocumentFacts(
        record_code=None,
        title=chunk.title,
        applicability=None,
        deadline=None,
        has_metadata=False,
    )


def _classify(facts: _DocumentFacts) -> str:
    code = facts.record_code or ""
    title = facts.title or ""
    if "竞赛项目级别认定" in code or "竞赛级别认定" in title or "级别认定结果" in title:
        return _KIND_CATALOG
    if "创新创业学分认定" in code or ("创新创业" in title and "学分认定" in title):
        return _KIND_CREDIT
    if "综评" in code or "综合素质评价" in title:
        return _KIND_EVALUATION
    if "院级奖学金" in code or "星火奖学金" in code or "院级奖学金" in title or "星火奖" in title:
        return _KIND_DEPT_SCHOLARSHIP
    if "本科奖学金" in code or "奖学金评定管理办法" in title:
        return _KIND_SCHOLARSHIP
    if "推免复试" in code or "推免复试" in title or "免试攻读研究生" in title:
        return _KIND_RECOMMENDATION
    if "蓝桥杯" in title:
        return _KIND_EVENT
    if "课程考核" in title or "成绩记载" in title:
        return _KIND_COURSE
    return _KIND_OTHER


def _year_conflict(text: str, kind: str, facts: _DocumentFacts, today: date) -> bool:
    if kind not in {_KIND_DEPT_SCHOLARSHIP, _KIND_RECOMMENDATION}:
        return False
    doc_year = _document_year(facts)
    if doc_year is None:
        # 年度类通知必须能确认适用年度，否则不用于作答。
        return True
    years = _years(text)
    if not years:
        return _future_year(text, today=today)
    # 年度类通知只服务其标注年度，问其他年度一律不适用。
    return doc_year != max(years)


def _document_year(facts: _DocumentFacts) -> int | None:
    """适用年度只取明确标注的年度口径，不拿发布日期当适用年度。"""
    app = facts.applicability or {}
    for key in ("适用年度", "适用届别", "适用学年", "适用年份"):
        match = re.search(r"20\d{2}", str(app.get(key) or ""))
        if match:
            return int(match.group())
    for value, pattern in (
        (facts.title, r"(20\d{2})\s*(?:年|届|版)"),
        # 记录编号按“计算机学院-2026-院级奖学金”编码适用年度
        (facts.record_code, r"(20\d{2})"),
    ):
        if not value:
            continue
        match = re.search(pattern, str(value))
        if match:
            return int(match.group(1))
    return None


def _deadline_conflict(text: str, facts: _DocumentFacts, today: date) -> bool:
    if facts.deadline is None or today <= facts.deadline:
        return False
    return bool(re.search(r"截止|报名|申请时间|还能|现在.*(申请|报名)|办理窗口", text))


def _applicability(text: str, facts: _DocumentFacts) -> bool | None:
    app = facts.applicability or {}
    grade_text = str(app.get("适用年级") or "")
    major_text = str(app.get("适用专业") or "")
    target_text = str(app.get("适用对象") or "")

    query_grade = _grade_level(text)
    query_major = _PROFESSION.search(text)
    unknown = False

    if query_grade and grade_text:
        allowed = _grade_allowed(grade_text, query_grade)
        if allowed is False:
            return False
        unknown = unknown or allowed is None
    elif query_grade and not grade_text:
        unknown = True

    if query_major and major_text:
        if not _major_allowed(major_text, query_major.group()):
            return False
    elif query_major and not major_text:
        unknown = True

    if re.search(r"研究生|硕士(?!生源)|博士", text) and target_text:
        if "本科" in target_text and "研究生" not in target_text:
            return False

    if unknown and _PERSONAL.search(text):
        # 适用范围未知时，不替学生认定个人适用性。
        return False
    return True


def _grade_level(text: str) -> int | None:
    match = re.search(r"大([一二三四])", text)
    if match:
        return "一二三四".index(match.group(1)) + 1
    return None


def _grade_allowed(grade_text: str, grade: int) -> bool | None:
    if re.search(r"全体|全部|全校|各年级|所有年级", grade_text):
        return True
    if "大一至大三" in grade_text:
        if grade <= 3:
            return True
        return bool(re.search(r"应届|毕业生", grade_text))
    match = re.search(r"大([一二三四])", grade_text)
    if match:
        return grade == "一二三四".index(match.group(1)) + 1
    return None


def _major_allowed(major_text: str, query_major: str) -> bool:
    if re.search(r"全校|不限|各专业|所有专业|相关本科专业", major_text):
        return True
    if not major_text.strip():
        return True
    if query_major in major_text or major_text in query_major:
        return True
    return bool(_CS_FAMILY.search(major_text) and _CS_FAMILY.search(query_major))
