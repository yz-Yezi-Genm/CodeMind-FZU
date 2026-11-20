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

import json
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
QUESTION_WORK_NAME = "请说明作品名称，例如“基于多源数据的城市交通流量预测”。"
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
QUESTION_PROFESSION = "你关注的是哪个专业？"
QUESTION_DEGREE = "你关注的是学术型、专业型，还是直博？"
QUESTION_GRADE = "你现在是大几？不同年级参考的年度通知不同。"

_COMPETITION_TOPIC = re.compile(
    r"竞赛|比赛|大赛|挑战杯|数学建模|蓝桥杯|获奖|奖项|(?<!学)奖(?!学金)"
    r"|创新学分|学分认定|综测加分|综测里|综测能加|加几分|能加多少分"
)
_RECOMMENDATION_TOPIC = re.compile(r"推免|保研|免试攻读|直博")
_SCHOLARSHIP_TOPIC = re.compile(r"奖学金|助学金|奖助|单项奖|励志奖")

_PURPOSE_CREDIT = re.compile(r"创新学分|学分认定|认定多少学分|原始分")
_PURPOSE_EVALUATION = re.compile(r"综测|综合素质测评|综合素质评价|加几分|加分")

# 正文同时含教师与学生条款、必须按章节定位的资料；新增此类文件时在此登记。
_SECTION_SENSITIVE = re.compile(
    r"创新创业学分认定|学分认定实施|星火|奖教金|奖教奖学金"
)

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
_RANK = re.compile(
    r"第([一二三四五六七八九十]{1,2}|\d{1,2})\s*(?:完成人|作者|名)|排名第\s*([一二三四五六七八九十]{1,2}|\d{1,2})"
)
_ORDER = re.compile(r"第[一二三四五六七八九十]{1,2}\s*(?:完成人|作者)|完成人排序|排序第")
_SEMESTER = re.compile(r"上一学期|上学期|上个学期|前一学期|本学期|这学期|这一学期|下学期|去年|前年|学年")
_FIRST_UNIT = re.compile(r"第一署名|署名单位|第一单位")
_FIRST_UNIT_NEGATIVE = re.compile(r"不是|并非|没有|未以|不属于|非第一")
_SEMESTER_LAST = re.compile(r"上一学期|上学期|上个学期|前一学期")
_SEMESTER_OTHER = re.compile(r"本学期|这学期|这一学期|下学期|去年|前年|两年前")

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
_REVIEW_DETAIL = re.compile(
    r"招多少|招生计划|招几人|多少人|名额|分组|材料投递|投递|调剂|录取|复试名单"
)
_PROFESSION = re.compile(
    r"计算机科学与技术|计算机技术|软件工程|人工智能|数据科学与大数据技术|数据科学"
    r"|大数据|信息安全|网络空间安全|数学|金融|经济|电子信息"
)
_GRADE = re.compile(r"大[一二三四]|[一二三四]年级|20\d{2}\s*级")
_PERSONAL = re.compile(r"我(?!们)|本人|我自己")
_EXTERNAL_SCHOOL = re.compile(r"其他学院|别的学院|外校|其他学校|别的学校")
_EXTERNAL_COLLEGE = re.compile(
    r"其他学院|别的学院|外院"
    r"|数学与统计学院|外国语学院|经济与管理学院|法学院|人文社会科学学院"
    r"|土木工程学院|机械工程及自动化学院|化学学院|物理与信息工程学院"
    r"|生物科学与工程学院|材料科学与工程学院|电气工程与自动化学院|建筑与城乡规划学院"
)

_KIND_CREDIT = "credit_bylaw"
_KIND_EVALUATION = "evaluation_bylaw"
_KIND_SCHOLARSHIP = "scholarship_bylaw"
_KIND_DEPT_SCHOLARSHIP = "dept_scholarship"
_KIND_RECOMMENDATION_REVIEW = "recommendation_review"
_KIND_RECOMMENDATION_QUALIFICATION = "recommendation_qualification"
# 教务处《大学生学科竞赛级别认定结果》：只服务创新学分认定与级别归属。
_KIND_CREDIT_CATALOG = "competition_credit_catalog"
# 《学生文化科技创新创业奖学金学科竞赛等级目录》：综测 A+/A/A-/B/C 定档依据。
_KIND_EVAL_CATALOG = "competition_evaluation_catalog"
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
    scenario, _ = _analyse(text, request.query)
    if scenario is None:
        return QUESTION_TOPIC
    if scenario == COMPETITION:
        return _clarify_competition(text)
    if scenario == SCHOLARSHIP:
        return _clarify_scholarship(text)
    return _clarify_recommendation(text, request.query)


def alpha_evidence_check(request: AgentRequest, chunk: RetrievedChunk) -> bool:
    """默认入口；查询函数来自 `bind_metadata_lookup` / `bind_chunk_lookup`。"""
    return _assess(request, chunk, _lookup, _chunk_lookup, date.today())


# --------------------------------------------------------------------------- 文本解析


def _user_text(request: AgentRequest) -> str:
    previous = [turn.content for turn in request.history if turn.role == LLMRole.USER]
    return "\n".join([*previous, request.query]).strip()


def _detect(text: str) -> tuple[str | None, str | None]:
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


def _analyse(
    text: str, query: str | None = None
) -> tuple[str | None, str | None]:
    """优先按本轮问题定场景，避免历史对话的旧主题污染新问题。"""
    if query:
        scenario, purpose = _detect(query)
        if scenario is not None and not (scenario == COMPETITION and purpose is None):
            return scenario, purpose
        full_scenario, full_purpose = _detect(text)
        if scenario is None:
            return full_scenario, full_purpose
        # 本轮只提到“奖”而未说用途，且上下文明确是奖学金场景时，按奖学金继续。
        if full_scenario is not None and full_scenario != COMPETITION:
            return full_scenario, full_purpose
        return scenario, purpose
    return _detect(text)


def _purpose(text: str) -> str | None:
    if _PURPOSE_CREDIT.search(text):
        return PURPOSE_CREDIT
    if _PURPOSE_EVALUATION.search(text):
        return PURPOSE_EVALUATION
    if _RECOMMENDATION_TOPIC.search(text):
        return PURPOSE_RECOMMENDATION
    return None


def _level(text: str) -> str | None:
    """级别只看明确写出的奖项级别；竞赛名称里的“全国”不等于国家级。"""
    if re.search(r"国际级|国际性|国际竞赛", text):
        return "international"
    if re.search(r"国家级|国家[特一二三]?等(?:奖)?|国家奖|全国奖|全国总决赛|国赛", text):
        return "national"
    if re.search(r"省部级|省级|省赛|赛区|省[一二三]等", text):
        return "provincial"
    if re.search(r"校级|学校级", text):
        return "school"
    if re.search(r"院级|学院级", text):
        return "college"
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
    return _rank_number(token)


_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _rank_number(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    if token == "十":
        return 10
    if token.startswith("十"):
        return 10 + _DIGITS.get(token[1:], 0)
    if "十" in token:
        head, _, tail = token.partition("十")
        base = _DIGITS.get(head, 0) * 10
        return base + (_DIGITS.get(tail, 0) if tail else 0)
    return _DIGITS.get(token)


def _first_unit_state(text: str) -> bool | None:
    """第一署名单位是肯定、否定还是未说明。"""
    if not _FIRST_UNIT.search(text):
        return None
    if _FIRST_UNIT_NEGATIVE.search(text):
        return False
    if re.search(r"(以|是).{0,8}(福州大学|福大).{0,6}(为|作为)?第一|第一署名.{0,4}(福州大学|福大)", text):
        return True
    return None


def _work_mentioned(text: str) -> bool:
    """作品名称：书名号标题，或明确写出作品/项目/论文名称。"""
    if re.search(r"《[^》]{2,60}》", text):
        return True
    return bool(re.search(r"(?:作品|项目|论文|成果)(?:名称|题目|叫)|(?:作品|项目|论文)是[《“]", text))


def _degree_type(text: str) -> str | None:
    if re.search(r"直博", text):
        return "direct_phd"
    if re.search(r"学术型|学硕|学术硕士", text):
        return "academic"
    if re.search(r"专业型|专硕|专业硕士", text):
        return "professional"
    return None


def _semester_state(text: str) -> bool | None:
    """成果是否落在上一学期。"""
    if _SEMESTER_LAST.search(text):
        return True
    if _SEMESTER_OTHER.search(text):
        return False
    return None


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


_REVIEW_PRIORITY = re.compile(r"复试|面试|机试|招生计划|招生名额|接收推免")


def _recommendation_object(text: str) -> str | None:
    # 复试资格审查、复试材料属于复试环节，不能因为出现“资格”就归到推荐资格。
    if _REVIEW_PRIORITY.search(text):
        return REVIEW
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
    if purpose == PURPOSE_CREDIT and not _work_mentioned(text):
        # 创新学分按作品认定，赛事与作品必须能对上。
        return QUESTION_WORK_NAME
    if _level(text) is None:
        return QUESTION_LEVEL
    if _award_grade(text) is None and _rank(text) is None:
        return QUESTION_AWARD_GRADE
    team = _team(text)
    if team is None:
        return QUESTION_FORMAT
    if team and purpose == PURPOSE_CREDIT:
        # 只在前八名之外未说明时追问；已经说清第九名及以后不再重复追问。
        if _rank(text) is None:
            return QUESTION_TOP_EIGHT
    if purpose == PURPOSE_EVALUATION:
        # 个人项目同样要计上一学期成果、同样要求福大第一署名，不因为个人申报跳过。
        if team and _rank(text) is None and not _ORDER.search(text):
            return QUESTION_ORDER
        if _semester_state(text) is None:
            return QUESTION_SEMESTER
        if _first_unit_state(text) is None:
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


def _clarify_recommendation(text: str, subject: str | None = None) -> str | None:
    if _future_year(text, today=date.today()) or _EXTERNAL_SCHOOL.search(text):
        return None
    obj = _recommendation_object(text)
    if obj == REVIEW and _REVIEW_DETAIL.search(text):
        # 专业与学位类型是两件事：认出专业不等于知道学术型/专业型/直博。
        if not _PROFESSION.search(text):
            return QUESTION_PROFESSION
        if _degree_type(text) is None:
            return QUESTION_DEGREE
        return None
    # 年级只对校内推荐资格、排名和遴选有意义，复试材料类问题不追问年级。
    # 只看本轮提问，避免上一轮聊别的主题时把“我”带进来。
    current = subject or text
    if _PERSONAL.search(current) and not _GRADE.search(text):
        return QUESTION_GRADE
    if obj is None:
        return QUESTION_RECOMMENDATION_OBJECT
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
        scenario, purpose = _analyse(text, request.query)
        if scenario is None:
            return True
        # 三个场景都要确认文档类型与适用范围；缺元数据即视为无法确认。
        if not facts.has_metadata:
            return False
        if not facts.applicability:
            return False
        kind = _classify(facts)
        if _applicability(text, facts, today) is False:
            return False
        if not _section_applies(text, facts, chunk, chunk_lookup):
            return False
        if _year_conflict(text, kind, facts, today):
            return False
        if _deadline_conflict(
            text, facts, today, chunk.timeliness_verification_status
        ):
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
        return kind == _KIND_CREDIT_CATALOG
    if purpose == PURPOSE_RECOMMENDATION:
        return False
    if purpose == PURPOSE_CREDIT:
        # 创新学分只认教务处级别认定目录与学分认定办法。
        return kind in {_KIND_CREDIT, _KIND_CREDIT_CATALOG}
    if purpose == PURPOSE_EVALUATION:
        level = _level(text)
        if level is None:
            return False
        if level in {"international", "national", "provincial"}:
            # 综测 A+/A/A-/B/C 只能由学科竞赛等级目录定档；教务处级别认定目录不顶替。
            return kind == _KIND_EVAL_CATALOG
        # 校级、院级两档在综评办法里直接写明，不需要等级目录。
        return kind in {_KIND_EVALUATION, _KIND_EVAL_CATALOG}
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
    if obj == REVIEW:
        # 复试、材料、招生计划只认学院接收推免的复试方案。
        return kind == _KIND_RECOMMENDATION_REVIEW
    if obj == QUALIFICATION or (obj is None and _PERSONAL.search(text)):
        # 推荐资格只认学院推荐资格方案；校级办法未入库，复试方案不能代替。
        return kind == _KIND_RECOMMENDATION_QUALIFICATION
    return kind == _KIND_RECOMMENDATION_QUALIFICATION


# --------------------------------------------------------------------------- 元数据与适用范围


def _needs_section(facts: _DocumentFacts) -> bool:
    """正文同时含教师条款与学生条款、必须按章节区分的资料。"""
    scope = f"{facts.record_code or ''}{facts.title or ''}"
    return bool(_SECTION_SENSITIVE.search(scope))


_TEACHER_SECTION = re.compile(r"奖教金|教师|教职工|师资|绩效")
_STUDENT_SECTION = re.compile(r"奖学金|学生|本科生|研究生|同学")
# heading_path / locator 的层级分隔符。总标题里“星火奖教奖学金”是复合词，不代表某一节。
_SECTION_SEP = re.compile(r"\||｜|›|»|>")
_PROCEDURE_QUESTION = re.compile(r"材料|流程|报送|提交|截止|交到|程序|步骤|什么时候交|怎么报")
_AWARD_QUESTION = re.compile(r"条件|要求|金额|奖励标准|名额|等级|资格|比例|能不能评")

ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"
ROLE_SHARED = "shared"


def _section_text(note: object) -> str:
    """章节说明可能是纯文本、dict，或含 heading_path 的 JSON 字符串。"""
    if note is None:
        return ""
    if isinstance(note, dict):
        parts: list[str] = []
        heading = note.get("heading_path")
        if isinstance(heading, list):
            for item in heading:
                if isinstance(item, dict):
                    title = item.get("title") or item.get("heading")
                    if title:
                        parts.append(str(title))
                else:
                    parts.append(str(item))
        elif heading:
            parts.append(str(heading))
        return " | ".join(part for part in parts if part)
    if not isinstance(note, str):
        return str(note)
    text = note.strip()
    if not text.startswith(("{", "[")):
        return text
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return text
    parts: list[str] = []
    if isinstance(data, dict):
        heading = data.get("heading_path")
        if isinstance(heading, list):
            parts.extend(str(item) for item in heading)
        elif heading:
            parts.append(str(heading))
        for key in ("heading", "section", "path", "title"):
            value = data.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            elif value:
                parts.append(str(value))
    elif isinstance(data, list):
        parts.extend(str(item) for item in data)
    return " ".join(item for item in parts if item) or text


def _section_role(note: str) -> str | None:
    """按层级切分章节名，判断片段属于教师节、学生节，还是不区分师生的总通知。"""
    teacher = student = False
    for raw in _SECTION_SEP.split(note):
        segment = raw.strip().replace("奖教奖学金", "")
        if not segment:
            continue
        if _TEACHER_SECTION.search(segment):
            teacher = True
        if _STUDENT_SECTION.search(segment):
            student = True
    if teacher and student:
        return ROLE_SHARED
    if teacher:
        return ROLE_TEACHER
    if student:
        return ROLE_STUDENT
    return None


def _section_applies(
    text: str,
    facts: _DocumentFacts,
    chunk: RetrievedChunk,
    chunk_lookup: ChunkLookup | None,
) -> bool:
    """按 locator_note / locator 区分同一文件里的局部章节（如奖教金与学生奖学金条款）。"""
    needs_section = _needs_section(facts)
    note = ""
    if chunk_lookup is not None:
        try:
            parsed = chunk_lookup(chunk.chunk_id)
        except Exception:
            parsed = None
        if parsed is not None:
            note = _section_text(getattr(parsed, "locator_note", None))
    note = f"{note} {_section_text(chunk.locator)}".strip()
    if not note and not needs_section:
        return True
    role = _section_role(note)
    if needs_section and role is None:
        # 总通知部分（款项使用、评选安排、材料报送）不区分师生，只在办理流程问题上放行。
        return bool(_PROCEDURE_QUESTION.search(text) and not _AWARD_QUESTION.search(text))
    if role in {None, ROLE_SHARED}:
        return True
    if role == ROLE_TEACHER:
        # 教师评奖条款一律不用于学生问答，即使提问者自称教师。
        return False
    return not re.search(r"教师|教职工|奖教金", text)


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
    scope = f"{code}{title}"
    # 综测定档目录与教务处级别认定目录不是同一份资料，先区分再落到别的类型。
    if "学科竞赛等级目录" in scope or (
        "文化科技创新创业" in scope and "目录" in scope
    ):
        return _KIND_EVAL_CATALOG
    if "竞赛项目级别认定" in code or "竞赛级别认定" in title or "级别认定结果" in title:
        return _KIND_CREDIT_CATALOG
    if "创新创业学分认定" in code or ("创新创业" in title and "学分认定" in title):
        return _KIND_CREDIT
    if "综评" in code or "综合素质评价" in title:
        return _KIND_EVALUATION
    if "院级奖学金" in code or "星火奖学金" in code or "院级奖学金" in title or "星火奖" in title:
        return _KIND_DEPT_SCHOLARSHIP
    if "本科奖学金" in code or "奖学金评定管理办法" in title:
        return _KIND_SCHOLARSHIP
    # 学院接收推免的复试方案与学院推荐资格方案是两份资料。
    if "推免复试" in code or "推免复试" in title or "复试方案" in title or "复试实施细则" in title:
        return _KIND_RECOMMENDATION_REVIEW
    if "推免资格推荐" in code or "推荐资格" in scope or "推免资格" in scope:
        return _KIND_RECOMMENDATION_QUALIFICATION
    if "免试攻读研究生" in title:
        return _KIND_RECOMMENDATION_QUALIFICATION
    if "蓝桥杯" in title:
        return _KIND_EVENT
    if "课程考核" in title or "成绩记载" in title:
        return _KIND_COURSE
    return _KIND_OTHER


_YEAR_AMBIGUITY_KEY = re.compile(r"年度歧义|年度|评奖年度|考核年度")


def _year_ambiguous(facts: _DocumentFacts) -> bool:
    """元数据明确标注年度歧义时，不能凭 record_code 的年份认作适用年度。"""
    app = facts.applicability or {}
    for key, value in app.items():
        if "歧义" not in str(key):
            continue
        text = str(value)
        if text.strip() and not re.fullmatch(r"无|否|none|-", text.strip(), re.I):
            return True
    return False


def _year_conflict(text: str, kind: str, facts: _DocumentFacts, today: date) -> bool:
    if kind not in {
        _KIND_DEPT_SCHOLARSHIP,
        _KIND_RECOMMENDATION_REVIEW,
        _KIND_RECOMMENDATION_QUALIFICATION,
    }:
        return False
    if _year_ambiguous(facts):
        # 发布年度与正文考核年度存疑时，一律不用于作答。
        return True
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
    for key in ("适用年度", "适用届别", "适用学年", "适用年份", "目标届别", "年度"):
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


_AVAILABILITY_QUESTION = re.compile(r"还能|现在还|目前还|是否还|办理窗口|现在.*(申请|报名|提交)|今年.*(申请|报名)")


def _deadline_conflict(
    text: str,
    facts: _DocumentFacts,
    today: date,
    timeliness: TimelinessVerificationStatus,
) -> bool:
    """截止日期已过只在“现行资料 + 问现在还能不能办”时拒绝。

    历史通知（historical / expired）的截止时间与办理状态应作为历史信息回答，
    由工作流标注 answer_mode=historical，不在这里丢证据。
    """
    if facts.deadline is None or today <= facts.deadline:
        return False
    if timeliness in {
        TimelinessVerificationStatus.HISTORICAL,
        TimelinessVerificationStatus.EXPIRED,
    }:
        return False
    return bool(_AVAILABILITY_QUESTION.search(text))


_GRADE_KEYS = ("适用年级", "年级", "学生对象", "对象", "适用对象", "招生对象")
_MAJOR_KEYS = ("适用专业", "专业", "招生专业")
_TARGET_KEYS = ("适用对象", "对象", "学生对象", "招生对象")
_COLLEGE_KEYS = ("学院", "适用学院", "所属学院")


def _first_value(app: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = app.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _applicability(
    text: str, facts: _DocumentFacts, today: date
) -> bool | None:
    app = facts.applicability or {}
    # #31 实际元数据里年级/专业/对象分别落在 适用年级 / 学生对象 / 对象 / 学院 等键上。
    grade_text = _first_value(app, _GRADE_KEYS)
    major_text = _first_value(app, _MAJOR_KEYS)
    target_text = _first_value(app, _TARGET_KEYS)
    college_text = _first_value(app, _COLLEGE_KEYS)

    query_grade = _grade_level(text, today)
    query_major = _PROFESSION.search(text)
    unknown = False

    query_cohort = _enrolment_year(text)
    target_cohort = _cohort_year(app)
    if query_cohort and target_cohort and query_cohort + 4 != target_cohort:
        # 入学年份与目标届别对不上，说明这份年度方案不是该学生的届别。
        return False

    if college_text and _EXTERNAL_COLLEGE.search(text):
        # 资料只服务本学院，问题指向其他学院时不适用。
        named = _EXTERNAL_COLLEGE.search(text)
        if "计算机" not in named.group() and "软件" not in named.group():
            return False

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


def _grade_level(text: str, today: date | None = None) -> int | None:
    match = re.search(r"大([一二三四])", text)
    if match:
        return "一二三四".index(match.group(1)) + 1
    year = _enrolment_year(text)
    if year is not None and today is not None:
        # 2024 级在 2026 年 11 月是大三；9 月前仍按上一学年计算。
        grade = today.year - year + (1 if today.month >= 9 else 0)
        return grade if 1 <= grade <= 4 else None
    return None


def _enrolment_year(text: str) -> int | None:
    match = re.search(r"(20\d{2})\s*级", text)
    return int(match.group(1)) if match else None


def _cohort_year(app: dict[str, str]) -> int | None:
    for key in ("目标届别", "适用届别", "适用年级"):
        match = re.search(r"(20\d{2})\s*届", str(app.get(key) or ""))
        if match:
            return int(match.group(1))
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


_MAJOR_ALIASES: dict[str, tuple[str, ...]] = {
    "计算机科学与技术": ("计算机科学与技术", "计算机技术", "计算机科学", "计算机"),
    "软件工程": ("软件工程", "软件"),
    "人工智能": ("人工智能",),
    "数据科学与大数据技术": ("数据科学与大数据技术", "数据科学", "大数据"),
    "信息安全": ("信息安全", "网络空间安全"),
}


def _major_allowed(major_text: str, query_major: str) -> bool:
    """只做明确专业匹配或有依据的别名映射，不做计算机大类模糊放行。"""
    if re.search(r"全校|不限|各专业|所有专业|相关本科专业", major_text):
        return True
    if not major_text.strip():
        return True
    if query_major in major_text:
        return True
    for canonical, aliases in _MAJOR_ALIASES.items():
        if query_major in aliases and canonical in major_text:
            return True
    return False
