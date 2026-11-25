"""Alpha 业务规则单元测试：追问、证据适用性与工作流联调。"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from backend.contracts.models import (
    AgentRequest,
    AnswerMode,
    AnswerStatus,
    ConversationTurn,
    DocumentMetadata,
    ExtractionStatus,
    InclusionStatus,
    LLMResult,
    ParsedChunk,
    LLMRole,
    RetrievalRequest,
    RetrievalStatus,
    RetrievedChunk,
    SourceVerificationStatus,
    TimelinessVerificationStatus,
)
from backend.services.agent_workflow import AgentWorkflow
import backend.services.alpha_business_rules as business_rules
from backend.services.alpha_business_rules import (
    QUESTION_AWARD_GRADE,
    QUESTION_DEPT_AWARD,
    QUESTION_FIRST_UNIT,
    QUESTION_FORMAT,
    QUESTION_GRADE,
    QUESTION_LEVEL,
    QUESTION_ORDER,
    QUESTION_PROFESSION,
    QUESTION_PURPOSE,
    QUESTION_RECOMMENDATION_OBJECT,
    QUESTION_SCHOLARSHIP_CATEGORY,
    QUESTION_SEMESTER,
    QUESTION_TOP_EIGHT,
    QUESTION_TOPIC,
    _first_unit_state,
    _grade_level,
    _level_for,
    _team,
    _works,
    _level,
    _rank,
    QUESTION_WORK_NAME,
    QUESTION_DEGREE,
    QUESTION_RESOURCE_TYPE,
    QUESTION_LAB_PURPOSE,
    QUESTION_PLAN_SCOPE,
    COMPETITION,
    PURPOSE_EVALUATION,
    RECOMMENDATION,
    RESOURCES,
    _analyse,
    _detect,
    _purpose,
    alpha_clarification_rule,
    build_alpha_evidence_check,
)

TODAY = date(2026, 11, 19)
WORK = "作品《基于多源数据的城市交通流量预测》"


def _request(query: str, *, history: list[str] | None = None) -> AgentRequest:
    turns = [
        ConversationTurn(role=LLMRole.USER, content=item) for item in (history or [])
    ]
    return AgentRequest(
        request_id=uuid.UUID(int=1),
        conversation_id=uuid.UUID(int=2),
        query=query,
        history=turns,
    )


@pytest.mark.parametrize(("hours", "expected"), [
    (0, 2), (1, 2), (29, 2), (30, 4), (31, 4), (59, 4), (60, 6), (61, 6),
    (100, 6), (200, 6), ("29.999", 2), ("59.999", 4),
])
def test_volunteer_service_raw_score_boundaries(hours, expected):
    assert business_rules.volunteer_service_raw_score(Decimal(hours)) == expected


@pytest.mark.parametrize("hours", ["-1", "NaN", "Infinity"])
def test_volunteer_service_rejects_invalid_hours(hours):
    with pytest.raises(ValueError):
        business_rules.volunteer_service_raw_score(Decimal(hours))


def test_volunteer_service_clarifies_cohort_and_invalid_duration():
    assert alpha_clarification_rule(_request("推免志愿服务计分怎么计算？")) == business_rules.QUESTION_VOLUNTEER_COHORT
    for hours in ("-1小时", "30-60小时", "1小时30分钟"):
        assert (alpha_clarification_rule(_request(f"2027届推免志愿服务{hours}算多少分？"))
                == business_rules.QUESTION_VOLUNTEER_HOURS)
    assert alpha_clarification_rule(_request("那30小时呢", history=["2027届推免志愿服务怎么计分？"])) is None


def _chunk(
    *,
    title: str,
    content: str,
    index: int = 1,
    timeliness: TimelinessVerificationStatus = TimelinessVerificationStatus.CURRENT,
    source: SourceVerificationStatus = SourceVerificationStatus.VERIFIED,
    published_on: date | None = date(2026, 5, 18),
    source_url: str = "https://example.invalid/policy",
    publisher: str | None = "福州大学",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.UUID(int=100 + index),
        document_id=uuid.UUID(int=200 + index),
        version_id=uuid.UUID(int=300 + index),
        file_id=uuid.UUID(int=400 + index),
        content=content,
        title=title,
        publisher=publisher,
        source_url=source_url,
        published_on=published_on,
        effective_on=None,
        locator="第 7 条",
        original_locator=None,
        score=1.0,
        retrieval_method="bm25",
        source_verification_status=source,
        timeliness_verification_status=timeliness,
        retrieval_status=RetrievalStatus.ENABLED,
    )


def _meta(
    chunk: RetrievedChunk,
    *,
    record_code: str,
    title: str | None = None,
    applicability: dict[str, str] | None = None,
    deadline: date | None = None,
    category: str = "综评与奖学金",
    directions: tuple[str, ...] = (),
    document_type: str = "规范性文件",
    policy_status: str = "当前有效",
    approved: bool = True,
) -> DocumentMetadata:
    return DocumentMetadata(
        title=title or chunk.title,
        document_type=document_type,
        category_name=category,
        business_direction_codes=list(directions),
        record_code=record_code,
        version_no="import-1",
        source_url=chunk.source_url,
        publisher=chunk.publisher,
        published_on=chunk.published_on,
        deadline_on=deadline,
        applicability_raw=applicability,
        policy_status=policy_status,
        source_verification_status=SourceVerificationStatus.VERIFIED,
        timeliness_verification_status=chunk.timeliness_verification_status,
        extraction_status=ExtractionStatus.EXTRACTED,
        v1_inclusion_status=InclusionStatus.INCLUDED,
        retrieval_status=RetrievalStatus.ENABLED,
        temporal_notes={"human_approved": approved},
    )


CREDIT_BYLAW = _chunk(
    index=1,
    title="福州大学本科生创新创业实践与素质拓展学分认定管理实施办法",
    content="国家级竞赛集体项目二等奖原始分 2 分；同一竞赛同一作品同年度只取最高一项。",
)
EVALUATION_BYLAW = _chunk(
    index=2,
    title="福州大学本科生综合素质评价实施办法",
    content="竞赛成果按 A+、A、A-、B、C 五档计分；校级最高等级奖 2 分、院级 1.5 分。",
)
SCHOOL_SCHOLARSHIP = _chunk(
    index=3,
    title="福州大学本科生奖学金评定管理办法",
    content="除任意选修课外有课程不及格者不具备参评资格；优秀学生综合奖学金一等奖 1500 元。",
)
DEPT_SCHOLARSHIP = _chunk(
    index=4,
    title="关于做好福州大学计算机与大数据学院各类院级奖学金评选工作的通知",
    content="学科竞赛类爱国者之星奖学金 5000 元、5 名，评选年度获省级三等奖以上。",
    timeliness=TimelinessVerificationStatus.HISTORICAL,
)
XINGHUO = _chunk(
    index=10,
    title="关于做好2026年福州大学“星火奖教奖学金”评选工作的通知",
    content="“星火奖学金”面向学生评选，每学年 3000 元/人；“星火奖教金”面向教师评选。",
    timeliness=TimelinessVerificationStatus.HISTORICAL,
)
RECOMMENDATION_REVIEW = _chunk(
    index=5,
    title="计算机与大数据学院 2027 年推免复试方案及实施细则",
    content="复试为现场机试 40 分加现场面试 60 分；计算机技术专业型硕士招生 57 人。",
    timeliness=TimelinessVerificationStatus.HISTORICAL,
)
CATALOG = _chunk(
    index=6,
    title="关于公布大学生学科竞赛级别认定结果的通知（2026年版）",
    content="全国大学生数学建模竞赛认定为国家级 A 类赛事。",
)
SUPERSEDED_SCHOLARSHIP = _chunk(
    index=7,
    title="福州大学本科生奖学金管理办法（2024）",
    content="优秀学生综合奖学金一等奖 1200 元。",
    timeliness=TimelinessVerificationStatus.SUPERSEDED,
)
LANQIAO = _chunk(
    index=9,
    title="第十七届蓝桥杯报名通知",
    content="蓝桥杯省赛报名时间为 2026 年 3 月，报名通知不作为学分认定依据。",
)


def _lookup_for(*pairs: tuple[RetrievedChunk, DocumentMetadata]):
    mapping = {chunk.version_id: meta for chunk, meta in pairs}
    return lambda version_id: mapping.get(version_id)


def _student_locator(chunk_id):
    """学生条款章节定位：仅在需要按章节区分时使用。"""
    return ParsedChunk(
        chunk_no=1,
        content="学生适用条款",
        source_file_key="policy.md",
        locator_note="学生适用条款",
    )


def _full_lookup():
    return _lookup_for(
        (CREDIT_BYLAW, _meta(
            CREDIT_BYLAW,
            record_code="福大-2024-创新创业学分认定",
            applicability={"适用年级": "全体本科生", "适用专业": "全校相关本科专业"},
        )),
        (EVALUATION_BYLAW, _meta(
            EVALUATION_BYLAW,
            record_code="福大-2026-综评",
            applicability={"适用年级": "全体本科生", "适用专业": ""},
        )),
        (SCHOOL_SCHOLARSHIP, _meta(
            SCHOOL_SCHOLARSHIP,
            record_code="福大-2026-本科奖学金",
            applicability={"适用年级": "全体本科生", "适用专业": ""},
        )),
        (DEPT_SCHOLARSHIP, _meta(
            DEPT_SCHOLARSHIP,
            record_code="计算机学院-2026-院级奖学金",
            applicability={"适用年级": "全体本科生", "适用专业": "学院各专业"},
            deadline=date(2026, 4, 26),
        )),
        (XINGHUO, _meta(
            XINGHUO,
            record_code="计算机学院-2026-星火奖学金",
            applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术、软件工程"},
            deadline=date(2026, 5, 20),
        )),
        (RECOMMENDATION_REVIEW, _meta(
            RECOMMENDATION_REVIEW,
            record_code="计算机学院-2026-推免复试参考",
            applicability={
                "适用年级": "2027届应届本科毕业生；大一至大三仅升学准备参考",
                "适用专业": "计算机科学与技术、软件工程、人工智能、数据科学与大数据技术",
            },
        )),
        (CATALOG, _meta(
            CATALOG,
            record_code="福大-2026-竞赛项目级别认定",
            applicability={"适用年级": "全体本科生", "适用专业": "全校相关本科专业"},
        )),
        (SUPERSEDED_SCHOLARSHIP, _meta(
            SUPERSEDED_SCHOLARSHIP,
            record_code="福大-2024-本科奖学金",
            applicability={"适用年级": "全体本科生", "适用专业": ""},
        )),
        (LANQIAO, _meta(
            LANQIAO,
            record_code="计算机学院-2026-蓝桥杯",
            applicability={"适用年级": "全体本科生", "适用专业": "全校相关本科专业"},
        )),
    )


# ---------------------------------------------------------------- 追问规则


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("怎么办？", QUESTION_TOPIC),
        ("我拿了个奖，能加学分吗？", QUESTION_PURPOSE),
        ("全国大学生数学建模竞赛国家二等奖，作品《基于多源数据的城市交通流量预测》，团队作品，我为第一完成人，创新学分原始分是多少？", None),
        (
            "综测里我们团队的校级竞赛最高等级奖，成果是上一学期取得的、"
            "福州大学为第一署名单位，能加多少分？",
            QUESTION_ORDER,
        ),
        ("蓝桥杯省赛二等奖在综测里能加几分？", None),
        ("这个比赛在不在教务处的认定目录里？", None),
        ("竞赛获奖在推免时能加多少分？", None),
    ],
)
def test_competition_clarification(query: str, expected: str | None) -> None:
    assert alpha_clarification_rule(_request(query)) == expected


def test_credit_team_needs_top_eight() -> None:
    query = f"我们团队参加挑战杯拿了省部级一等奖，{WORK}，能认定多少创新学分？"
    assert alpha_clarification_rule(_request(query)) == QUESTION_TOP_EIGHT


def test_evaluation_team_needs_semester_and_unit() -> None:
    query = "综测里我们团队参加校级竞赛拿了最高等级奖，我是第一完成人，能加多少分？"
    assert alpha_clarification_rule(_request(query)) == QUESTION_SEMESTER

    query_with_semester = (
        "综测里我们团队参加校级竞赛拿了最高等级奖，我是第一完成人，上一学期拿的。"
    )
    assert alpha_clarification_rule(_request(query_with_semester)) == QUESTION_FIRST_UNIT


def test_competition_needs_level_and_grade() -> None:
    assert (
        alpha_clarification_rule(
            _request(f"数学建模竞赛拿奖了，{WORK}，创新学分能认定多少？")
        )
        == QUESTION_LEVEL
    )
    assert (
        alpha_clarification_rule(
            _request(f"数学建模竞赛国家级奖，{WORK}，创新学分能认定多少？")
        )
        == QUESTION_AWARD_GRADE
    )
    assert (
        alpha_clarification_rule(
            _request(f"数学建模竞赛国家级二等奖，{WORK}，创新学分能认定多少？")
        )
        == QUESTION_FORMAT
    )
    # 创新学分按作品认定，缺作品名称时先问作品
    assert (
        alpha_clarification_rule(_request("数学建模竞赛国家级二等奖，创新学分能认定多少？"))
        == QUESTION_WORK_NAME
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("我能申请奖学金吗？", QUESTION_SCHOLARSHIP_CATEGORY),
        ("优秀学生综合奖学金一等奖要什么条件？", None),
        ("申请奖学金有哪些情况会直接没有资格？", None),
        ("我是大二，上学期有一门必修挂了，还能评奖学金吗？", None),
        ("院级奖学金有什么条件？", QUESTION_DEPT_AWARD),
        ("2027 年院级奖学金什么时候截止？", None),
        ("2026 学年优秀学生综合奖学金一等奖是什么标准？", None),
        ("院级学科竞赛类的爱国者之星奖学金，金额、名额和条件是什么？", None),
    ],
)
def test_scholarship_clarification(query: str, expected: str | None) -> None:
    assert alpha_clarification_rule(_request(query)) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("怎么才能保研？", QUESTION_RECOMMENDATION_OBJECT),
        ("我能不能保研？", QUESTION_GRADE),
        ("推免复试都考什么，怎么算分？", None),
        ("推免招多少人？", QUESTION_PROFESSION),
        ("2027 年计算机技术专硕招多少推免生？", None),
        ("推免资格要求专业排名前多少？", None),
        ("2028 年推免政策是什么？", None),
        ("其他学院的推免条件是什么？", None),
    ],
)
def test_recommendation_clarification(query: str, expected: str | None) -> None:
    assert alpha_clarification_rule(_request(query)) == expected


def test_one_question_per_turn() -> None:
    question = alpha_clarification_rule(_request("我想问奖学金和竞赛加分怎么办"))
    assert isinstance(question, str)
    assert question.count("？") == 1


def test_history_fills_slots_without_reasking() -> None:
    request = _request(
        "国家级二等奖，作品《基于多源数据的城市交通流量预测》，团队作品，第一完成人，创新学分能认定多少？",
        history=["我想问创新学分认定", "数学建模竞赛"],
    )
    assert alpha_clarification_rule(request) is None


# ---------------------------------------------------------------- 证据适用性


def test_default_entry_fails_closed_without_metadata() -> None:
    # 未绑定元数据查询时无法确认文档类型、适用年度与适用范围，一律不放行。
    check = build_alpha_evidence_check(today=lambda: TODAY)
    assert check(_request("优秀学生综合奖学金一等奖要什么条件？"), SCHOOL_SCHOLARSHIP) is False
    assert check(_request("优秀学生综合奖学金一等奖要什么条件？"), SUPERSEDED_SCHOLARSHIP) is False


@pytest.mark.parametrize(
    ("query", "chunk"),
    [
        ("全国大学生数学建模竞赛国家二等奖，作品《基于多源数据的城市交通流量预测》，团队作品，我为第一完成人，创新学分原始分是多少？", CREDIT_BYLAW),
        ("综测里我们团队的校级竞赛最高等级奖能加多少分？", EVALUATION_BYLAW),
        ("优秀学生综合奖学金一等奖要什么条件？", SCHOOL_SCHOLARSHIP),
        ("院级学科竞赛类的爱国者之星奖学金，金额、名额和条件是什么？", DEPT_SCHOLARSHIP),
        ("我是大二，上学期有一门必修挂了，还能评奖学金吗？", SCHOOL_SCHOLARSHIP),
        ("推免复试都考什么，怎么算分？", RECOMMENDATION_REVIEW),
        ("2027 年计算机技术专硕招多少推免生？", RECOMMENDATION_REVIEW),
    ],
)
def test_applicable_evidence_is_kept(query: str, chunk: RetrievedChunk) -> None:
    check = build_alpha_evidence_check(
        _full_lookup(), chunk_lookup=_student_locator, today=lambda: TODAY
    )
    assert check(_request(query), chunk) is True


@pytest.mark.parametrize(
    ("query", "chunk"),
    [
        # 用途不同：创新学分问题不能拿综测分档回答
        ("数学建模竞赛国家级二等奖，作品《基于多源数据的城市交通流量预测》，团队作品，我是第一完成人，创新学分原始分是多少？", EVALUATION_BYLAW),
        # 综测定档：教务处级别认定目录不能代替学科竞赛等级目录
        ("蓝桥杯省赛二等奖在综测里能加几分？", CATALOG),
        # 赛事类别无法由目录确定
        ("蓝桥杯省赛二等奖在综测里能加几分？", EVALUATION_BYLAW),
        # 报名通知不是认定依据
        ("这个比赛在不在教务处的认定目录里？", LANQIAO),
        # 推免计分口径未入库，不能拿创新学分或综测代替
        ("竞赛获奖在推免时能加多少分？", CREDIT_BYLAW),
        ("竞赛获奖在推免时能加多少分？", EVALUATION_BYLAW),
        # 国家奖学金另文规定
        ("国家奖学金需要什么条件？", SCHOOL_SCHOLARSHIP),
        ("文化科技创新创业奖学金要什么条件？", SCHOOL_SCHOLARSHIP),
        ("宝钢奖学金怎么申请？", SCHOOL_SCHOLARSHIP),
        # 年度不匹配：2027 年院级不能套 2026 通知
        ("2027 年院级奖学金什么时候截止？", DEPT_SCHOLARSHIP),
        # 问 2026 年度也不能套 2027 方案
        ("2026 年推免复试考什么？", RECOMMENDATION_REVIEW),
        # 资格门槛不能用复试方案代替
        ("推免资格要求专业排名前多少？", RECOMMENDATION_REVIEW),
        # 未来年度不能套历史方案
        ("2028 年推免政策是什么？", RECOMMENDATION_REVIEW),
        # 外校资料不在库内
        ("其他学院的推免条件是什么？", RECOMMENDATION_REVIEW),
        # 旧版办法已废止
        ("优秀学生综合奖学金一等奖要什么条件？", SUPERSEDED_SCHOLARSHIP),
    ],
)
def test_inapplicable_evidence_is_rejected(query: str, chunk: RetrievedChunk) -> None:
    check = build_alpha_evidence_check(
        _full_lookup(), chunk_lookup=_student_locator, today=lambda: TODAY
    )
    assert check(_request(query), chunk) is False


def test_unverified_or_unconfirmed_evidence_is_rejected() -> None:
    check = build_alpha_evidence_check(_full_lookup(), today=lambda: TODAY)
    pending = _chunk(
        index=8,
        title=SCHOOL_SCHOLARSHIP.title,
        content=SCHOOL_SCHOLARSHIP.content,
        timeliness=TimelinessVerificationStatus.PENDING,
    )
    assert check(_request("优秀学生综合奖学金一等奖要什么条件？"), pending) is False


def test_major_mismatch_is_rejected_for_dept_award() -> None:
    meta = _meta(
        DEPT_SCHOLARSHIP,
        record_code="计算机学院-2026-院级奖学金",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术、软件工程"},
        deadline=date(2026, 4, 26),
    )
    check = build_alpha_evidence_check(
        _lookup_for((DEPT_SCHOLARSHIP, meta)), today=lambda: TODAY
    )
    query = "我是数学专业大二学生，想申请院级学业类奖学金，有什么条件？"
    assert check(_request(query), DEPT_SCHOLARSHIP) is False


def test_evidence_check_never_returns_string() -> None:
    check = build_alpha_evidence_check(_full_lookup(), today=lambda: TODAY)
    result = check(_request("国家奖学金需要什么条件？"), SCHOOL_SCHOLARSHIP)
    assert isinstance(result, bool)


# ---------------------------------------------------------------- 工作流联调


class _Retriever:
    def __init__(self, chunks: list[RetrievedChunk], *, metadata: DocumentMetadata | None = None) -> None:
        self._chunks = chunks
        self._metadata = metadata.model_copy(deep=True) if metadata is not None else None
        self.calls = 0

    def get_document_metadata(self, version_id) -> DocumentMetadata | None:
        if self._metadata is None or not any(chunk.version_id == version_id for chunk in self._chunks):
            return None
        return self._metadata.model_copy(deep=True)

    def get_parsed_chunk(self, chunk_id) -> ParsedChunk | None:
        chunk = next((chunk for chunk in self._chunks if chunk.chunk_id == chunk_id), None)
        if chunk is None:
            return None
        return ParsedChunk(chunk_no=1, source_file_key="test.md", content=chunk.content,
                           locator=chunk.locator, original_locator=chunk.original_locator)

    async def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        self.calls += 1
        return list(self._chunks)


class _LLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request) -> LLMResult:
        self.calls += 1
        evidence = json.loads(request.messages[-1].content)["evidence"]
        return LLMResult(content=json.dumps({
            "answer": evidence[0]["content"], "used_evidence_ids": [evidence[0]["evidence_id"]],
        }), model="stub")


@pytest.mark.anyio
async def test_workflow_returns_clarification_before_retrieval() -> None:
    retriever = _Retriever([SCHOOL_SCHOLARSHIP])
    llm = _LLM()
    workflow = AgentWorkflow(
        retriever=retriever,
        llm_client=llm,
        clarification_rule=alpha_clarification_rule,
        evidence_check=build_alpha_evidence_check(_full_lookup(), today=lambda: TODAY),
    )
    result = await workflow.run(_request("我能申请奖学金吗？"))
    assert result.status == AnswerStatus.NEEDS_CLARIFICATION
    assert result.clarifying_question == QUESTION_SCHOLARSHIP_CATEGORY
    assert result.answer is None
    assert retriever.calls == 0
    assert llm.calls == 0


@pytest.mark.anyio
async def test_workflow_rejects_inapplicable_evidence() -> None:
    retriever = _Retriever([EVALUATION_BYLAW])
    llm = _LLM()
    workflow = AgentWorkflow(
        retriever=retriever,
        llm_client=llm,
        clarification_rule=alpha_clarification_rule,
        evidence_check=build_alpha_evidence_check(_full_lookup(), today=lambda: TODAY),
    )
    result = await workflow.run(_request("蓝桥杯省赛二等奖在综测里能加几分？"))
    assert result.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert result.answer_mode == AnswerMode.INSUFFICIENT_DATA
    assert result.citations == []
    assert llm.calls == 0


@pytest.mark.anyio
async def test_workflow_answers_with_applicable_evidence() -> None:
    # Synthetic test approval only; Agent now independently verifies the same
    # retriever's metadata, even when the business rule accepts the evidence.
    metadata = _full_lookup()(SCHOOL_SCHOLARSHIP.version_id)
    metadata.temporal_notes = {"human_approved": True}
    retriever = _Retriever([SCHOOL_SCHOLARSHIP], metadata=metadata)
    llm = _LLM()
    workflow = AgentWorkflow(
        retriever=retriever,
        llm_client=llm,
        clarification_rule=alpha_clarification_rule,
        evidence_check=build_alpha_evidence_check(_full_lookup(), today=lambda: TODAY),
    )
    result = await workflow.run(_request("优秀学生综合奖学金一等奖要什么条件？"))
    assert result.status == AnswerStatus.ANSWERED
    assert result.answer_mode == AnswerMode.CURRENT_POLICY
    assert [str(citation.chunk_id) for citation in result.citations] == [
        str(SCHOOL_SCHOLARSHIP.chunk_id)
    ]


@pytest.mark.anyio
async def test_clarification_error_is_safely_rejected() -> None:
    """追问规则异常时不得产出政策答案，也不触发检索与模型调用。"""
    def broken_rule(request: AgentRequest) -> str | None:
        raise RuntimeError("rule failure")

    retriever = _Retriever([SCHOOL_SCHOLARSHIP])
    llm = _LLM()
    workflow = AgentWorkflow(
        retriever=retriever,
        llm_client=llm,
        clarification_rule=broken_rule,
    )
    try:
        result = await workflow.run(_request("优秀学生综合奖学金一等奖要什么条件？"))
    except RuntimeError:
        # 尚未合并兜底捕获的工作流版本：异常交由调用方统一拒答。
        assert retriever.calls == 0
        assert llm.calls == 0
        return
    assert result.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert result.answer_mode == AnswerMode.INSUFFICIENT_DATA
    assert result.warnings[0].code == "CLARIFICATION_RULE_FAILED"
    assert retriever.calls == 0
    assert llm.calls == 0


def test_section_sensitive_document_without_locator_is_rejected() -> None:
    """必须按章节区分的资料，无法确认章节时按未知处理。"""
    query = "全国大学生数学建模竞赛国家级二等奖，团队作品，我是第一完成人，创新学分原始分是多少？"
    check = build_alpha_evidence_check(_full_lookup(), today=lambda: TODAY)
    assert check(_request(query), CREDIT_BYLAW) is False

    def missing_chunk(chunk_id):
        return None

    check_with_lookup = build_alpha_evidence_check(
        _full_lookup(), chunk_lookup=missing_chunk, today=lambda: TODAY
    )
    assert check_with_lookup(_request(query), CREDIT_BYLAW) is False


def test_non_section_sensitive_document_does_not_require_locator() -> None:
    """不需要章节区分的资料，没有 locator_note 也继续判断。"""
    check = build_alpha_evidence_check(_full_lookup(), today=lambda: TODAY)
    assert check(_request("优秀学生综合奖学金一等奖要什么条件？"), SCHOOL_SCHOLARSHIP) is True


def test_lookup_failure_is_treated_as_unknown() -> None:
    def broken_lookup(version_id) -> DocumentMetadata | None:
        raise RuntimeError("metadata unavailable")

    check = build_alpha_evidence_check(broken_lookup, today=lambda: TODAY)
    # 取不到元数据时按“适用范围未知”处理，个人适用性问题不能放行。
    assert check(_request("我是大二，能评优秀学生综合奖学金吗？"), SCHOOL_SCHOLARSHIP) is False


def test_history_completes_scholarship_category() -> None:
    """上一轮只说了“奖学金”，本轮补上类别后不再追问类别。"""
    request = _request(
        "一等奖要什么条件？",
        history=["我想问奖学金的事情", "优秀学生综合奖学金"],
    )
    assert alpha_clarification_rule(request) is None


def test_unknown_applicability_is_rejected() -> None:
    """适用范围无法确认时不放行，即使片段内容看起来相关。"""
    meta = _meta(
        CREDIT_BYLAW,
        record_code="福大-2024-创新创业学分认定",
        applicability=None,
    )
    check = build_alpha_evidence_check(
        _lookup_for((CREDIT_BYLAW, meta)), today=lambda: TODAY
    )
    query = "全国大学生数学建模竞赛国家级二等奖，团队作品，我是第一完成人，创新学分原始分是多少？"
    assert check(_request(query), CREDIT_BYLAW) is False


def test_annual_notice_without_metadata_is_rejected() -> None:
    """年度类通知缺元数据即无法确认适用年度，按未知处理。"""
    check = build_alpha_evidence_check(today=lambda: TODAY)
    assert check(_request("院级奖学金什么时候截止？"), DEPT_SCHOLARSHIP) is False


def test_teacher_only_section_is_rejected_for_student_question() -> None:
    """同一文件里教师绩效条款不能回答学生问题。"""
    from backend.contracts.models import ParsedChunk

    meta = _meta(
        CREDIT_BYLAW,
        record_code="福大-2024-创新创业学分认定",
        applicability={"适用年级": "全体本科生", "适用专业": "全校相关本科专业"},
    )
    lookup = _lookup_for((CREDIT_BYLAW, meta))

    def teacher_section(chunk_id):
        return ParsedChunk(
            chunk_no=1,
            content=CREDIT_BYLAW.content,
            source_file_key="credit.md",
            locator_note="第六部分 教师指导工作量与绩效认定",
        )

    def student_section(chunk_id):
        return ParsedChunk(
            chunk_no=1,
            content=CREDIT_BYLAW.content,
            source_file_key="credit.md",
            locator_note="第四部分 学生学分申请与记载",
        )

    query = "全国大学生数学建模竞赛国家级二等奖，团队作品，我是第一完成人，创新学分原始分是多少？"
    rejected = build_alpha_evidence_check(
        lookup, chunk_lookup=teacher_section, today=lambda: TODAY
    )
    assert rejected(_request(query), CREDIT_BYLAW) is False

    kept = build_alpha_evidence_check(
        lookup, chunk_lookup=student_section, today=lambda: TODAY
    )
    assert kept(_request(query), CREDIT_BYLAW) is True


def test_xinghuo_sections_are_distinguished() -> None:
    """星火文件混排奖教金（教师）与奖学金（学生），必须靠章节名区分。"""
    query = "星火奖学金的学生评选条件是什么？"
    lookup = _full_lookup()

    def teacher_heading(chunk_id):
        return ParsedChunk(
            chunk_no=1,
            content=XINGHUO.content,
            source_file_key="xinghuo.json",
            locator_note='{"heading_path": ["福州大学“星火奖教金”评选细则（教师）"]}',
        )

    def student_heading(chunk_id):
        return ParsedChunk(
            chunk_no=1,
            content=XINGHUO.content,
            source_file_key="xinghuo.json",
            locator_note='{"heading_path": ["福州大学“星火奖学金”评选细则（学生）"]}',
        )

    rejected = build_alpha_evidence_check(
        lookup, chunk_lookup=teacher_heading, today=lambda: TODAY
    )
    assert rejected(_request(query), XINGHUO) is False

    kept = build_alpha_evidence_check(
        lookup, chunk_lookup=student_heading, today=lambda: TODAY
    )
    assert kept(_request(query), XINGHUO) is True

    # 没有章节查询、locator 只有“第 7 条”这类泛化定位时，同样按无法确认拒绝。
    no_section = build_alpha_evidence_check(lookup, today=lambda: TODAY)
    assert no_section(_request(query), XINGHUO) is False


def test_xinghuo_three_part_structure() -> None:
    """星火文件按总通知 / 奖教金 / 奖学金三段区分，总标题里的复合词不能当章节标识。"""
    total = "关于做好2026年福州大学“星火奖教奖学金”评选工作的通知"
    lookup = _full_lookup()
    student_query = "星火奖学金的学生评选条件是什么？"
    teacher_query = "星火奖教金的评选条件是什么？"
    procedure_query = "星火奖教奖学金的材料报送截止时间是什么？"

    def note(*sections: str):
        payload = '{"heading_path": %s}' % json.dumps([total, *sections], ensure_ascii=False)
        return lambda chunk_id: ParsedChunk(
            chunk_no=1,
            content=XINGHUO.content,
            source_file_key="xinghuo.json",
            locator_note=payload,
        )

    general = build_alpha_evidence_check(
        lookup, chunk_lookup=note("二、评选安排"), today=lambda: TODAY
    )
    assert general(_request(procedure_query), XINGHUO) is True
    assert general(_request("星火奖教奖学金的评选条件是什么？"), XINGHUO) is False

    teacher = build_alpha_evidence_check(
        lookup, chunk_lookup=note("福州大学“星火奖教金”评选细则"), today=lambda: TODAY
    )
    # 教师评奖条款一律不用于学生问答，即使提问者自称教师。
    assert teacher(_request(teacher_query), XINGHUO) is False
    assert teacher(_request(student_query), XINGHUO) is False

    student = build_alpha_evidence_check(
        lookup, chunk_lookup=note("福州大学“星火奖学金”评选细则"), today=lambda: TODAY
    )
    assert student(_request(student_query), XINGHUO) is True
    assert student(_request(teacher_query), XINGHUO) is False


# --------------------------------------------------------------------------- #31 真实元数据回归


COLLEGE_2026 = _chunk(
    index=20,
    title="关于做好福州大学计算机与大数据学院各类院级奖学金评选工作的通知",
    content="学科竞赛类爱国者之星奖学金 5000 元、5 名，评选年度获省级三等奖以上。",
)
QUALIFICATION_2027 = _chunk(
    index=21,
    title="计算机与大数据学院（软件学院）2027年推荐优秀应届本科毕业生免试攻读研究生工作方案",
    content="推荐资格按综合成绩排序，申请截止 2026-09-09。",
    timeliness=TimelinessVerificationStatus.HISTORICAL,
)
EVAL_CATALOG = _chunk(
    index=22,
    title="福州大学学生文化科技创新创业奖学金学科竞赛等级目录（2026年版）",
    content="全国大学生数学建模竞赛为 A 类赛事，省赛按 B 档计分。",
)


def test_credit_catalog_only_serves_innovation_credit() -> None:
    """教务处级别认定目录能答创新学分，不能答综测加分。"""
    meta = _meta(
        CATALOG,
        record_code="福大-2026-竞赛项目级别认定",
        applicability={
            "适用年级": "参加相关竞赛并申请学分认定的本科生，含大一至大三",
            "适用专业": "全校相关本科专业",
            "适用对象": "竞赛学分认定申请者；教师绩效条文不作为学生问答范围",
        },
    )
    check = build_alpha_evidence_check(
        _lookup_for((CATALOG, meta)), chunk_lookup=_student_locator, today=lambda: TODAY
    )
    credit_query = "全国大学生数学建模竞赛国家二等奖，作品《基于多源数据的城市交通流量预测》，团队作品，我为第一完成人，创新学分原始分是多少？"
    assert check(_request(credit_query), CATALOG) is True
    assert check(_request("全国大学生数学建模竞赛国家级二等奖，综测能加几分？"), CATALOG) is False


def test_evaluation_catalog_required_for_national_competition() -> None:
    """综测定档只认学科竞赛等级目录，缺这份资料就不能给分。"""
    meta = _meta(
        EVAL_CATALOG,
        record_code="福大-2026-学科竞赛等级目录",
        applicability={"适用年级": "全体本科生", "适用专业": "全校相关本科专业"},
    )
    check = build_alpha_evidence_check(
        _lookup_for((EVAL_CATALOG, meta)), chunk_lookup=_student_locator, today=lambda: TODAY
    )
    assert check(_request("全国大学生数学建模竞赛国家级二等奖，综测能加几分？"), EVAL_CATALOG) is True
    assert check(_request("全国大学生数学建模竞赛国家级二等奖，综测能加几分？"), CATALOG) is False


def test_competition_name_with_quanguo_is_not_national() -> None:
    """竞赛名称含“全国”不等于国家级，省赛要按省部级识别。"""
    assert _level("全国大学生数学建模竞赛省赛二等奖") == "provincial"
    assert _level("全国大学生数学建模竞赛") is None
    assert _level("全国大学生数学建模竞赛国家级二等奖") == "national"


def test_ninth_rank_is_parsed_and_not_reasked() -> None:
    """第九名及以后已经说清，不再重复追问前八名。"""
    assert _rank("团队作品，我是第九完成人") == 9
    assert _rank("排名第 12") == 12
    request = _request("数学建模竞赛省赛二等奖，作品《基于多源数据的城市交通流量预测》，团队作品，我是第九完成人，创新学分原始分是多少？")
    assert alpha_clarification_rule(request) is None


def test_negative_first_unit_and_current_semester_are_not_reasked() -> None:
    """“不是第一署名单位”“本学期成果”已经回答，不再追问。"""
    base = "综测里我们团队的校级竞赛最高等级奖能加多少分？"
    explicit = base + "我是第二完成人，本学期取得的，不是以福州大学为第一署名单位。"
    assert alpha_clarification_rule(_request(explicit)) is None
    # 未说明时仍然逐项追问，且仍按两参数签名返回 str
    assert alpha_clarification_rule(_request(base)) == QUESTION_ORDER


def test_review_qualification_material_is_review() -> None:
    """复试资格审查、材料属于复试环节，不应被归为校内推荐资格。"""
    query = "推免复试资格审查要交哪些材料？"
    assert alpha_clarification_rule(_request(query)) is None
    meta = _meta(
        RECOMMENDATION_REVIEW,
        record_code="计算机学院-2027-推免复试",
        applicability={"适用年级": "2027届应届本科毕业生", "适用专业": "计算机科学与技术"},
    )
    check = build_alpha_evidence_check(
        _lookup_for((RECOMMENDATION_REVIEW, meta)), today=lambda: TODAY
    )
    assert check(_request(query), RECOMMENDATION_REVIEW) is True


def test_recommendation_qualification_plan_distinct_from_review() -> None:
    """2027 届推荐资格方案与学院复试方案不是同一种资料。"""
    meta = _meta(
        QUALIFICATION_2027,
        record_code="计算机学院-2027-推免资格推荐",
        applicability={
            "适用年级": "2027届应届本科毕业生；大一至大三仅升学准备参考",
            "适用专业": "计算机科学与技术（含实验班）、数据科学与大数据技术、人工智能、信息安全、软件工程",
            "适用对象": "学院申请取得本科推免推荐资格的学生",
            "目标届别": "2027届",
            "使用限制": "不适用于下一届；不可回答当前报名开放",
        },
    )
    check = build_alpha_evidence_check(
        _lookup_for((QUALIFICATION_2027, meta)), today=lambda: TODAY
    )
    qualification_query = "2027届推免推荐资格怎么排名？"
    review_query = "推免复试资格审查要交哪些材料？"
    assert check(_request(qualification_query), QUALIFICATION_2027) is True
    assert check(_request(review_query), QUALIFICATION_2027) is False

    review_meta = _meta(
        RECOMMENDATION_REVIEW,
        record_code="计算机学院-2027-推免复试",
        applicability={"适用年级": "2027届应届本科毕业生", "适用专业": "计算机科学与技术"},
    )
    review_check = build_alpha_evidence_check(
        _lookup_for((RECOMMENDATION_REVIEW, review_meta)), today=lambda: TODAY
    )
    assert review_check(_request(qualification_query), RECOMMENDATION_REVIEW) is False


def test_dept_annual_ambiguity_blocks_answers() -> None:
    """院级 2026 通知标注了年度歧义，不能凭 record_code 的年份当作 2026 适用。"""
    meta = _meta(
        COLLEGE_2026,
        record_code="计算机学院-2026-院级奖学金",
        applicability={
            "学院": "福州大学计算机与大数据学院",
            "对象": "正式学籍、在读全日制本科生和研究生，各专项另有限制",
            "年度歧义": "网页发布2026-04-13；首段2025年度；待学院确认，不自行纠正",
            "学业类": "原文10名本科生",
        },
    )
    check = build_alpha_evidence_check(
        _lookup_for((COLLEGE_2026, meta)), today=lambda: TODAY
    )
    query = "院级学科竞赛类的爱国者之星奖学金，金额、名额和条件是什么？"
    assert check(_request(query), COLLEGE_2026) is False


def test_college_field_rejects_other_college() -> None:
    """元数据限定本学院时，其他学院学生的问题不适用。"""
    meta = _meta(
        XINGHUO,
        record_code="计算机学院-2026-星火奖学金",
        applicability={
            "学院": "福州大学计算机与大数据学院",
            "学生对象": "正式学籍、在读全日制本科生和研究生",
            "教师条款": "全文为完整性保留，学生问答不得引用教师资格、名额或金额",
            "年度": "2026年沿用2025细则，申请期已过",
        },
    )
    lookup = _lookup_for((XINGHUO, meta))

    def student_heading(chunk_id):
        # 契约里 locator_note 是字符串，加载器会把 heading_path 结构序列化成 JSON。
        return ParsedChunk(
            chunk_no=1,
            content=XINGHUO.content,
            source_file_key="xinghuo.json",
            locator_note=json.dumps(
                {
                    "coordinate_system": "decoded_text_lf_bom_removed",
                    "heading_path": [{
                        "level": 2,
                        "title": "关于做好2026年福州大学“星火奖教奖学金”评选工作的通知 | 福州大学“星火奖学金”评选细则（学生）",
                    }],
                },
                ensure_ascii=False,
            ),
        )

    check = build_alpha_evidence_check(
        lookup, chunk_lookup=student_heading, today=lambda: TODAY
    )
    assert check(_request("我是数学与统计学院的学生，能申请星火奖学金吗？"), XINGHUO) is False
    assert check(_request("星火奖学金的学生评选条件是什么？"), XINGHUO) is True


def test_real_locator_note_dict_heading_path() -> None:
    """#31 的 locator_note 是 dict + heading_path[{level,title}]，要能直接解析。"""
    lookup = _full_lookup()

    def heading(title: str):
        return lambda chunk_id: ParsedChunk(
            chunk_no=1,
            content=XINGHUO.content,
            source_file_key="xinghuo.json",
            locator_note=json.dumps(
                {
                    "coordinate_system": "decoded_text_lf_bom_removed",
                    "heading_path": [{"level": 2, "title": title}],
                    "note": "本输入文件定位；不是官方原件页码。",
                },
                ensure_ascii=False,
            ),
        )

    student = build_alpha_evidence_check(
        lookup,
        chunk_lookup=heading("关于做好2026年福州大学“星火奖教奖学金”评选工作的通知 | 福州大学“星火奖学金”评选细则"),
        today=lambda: TODAY,
    )
    teacher = build_alpha_evidence_check(
        lookup,
        chunk_lookup=heading("关于做好2026年福州大学“星火奖教奖学金”评选工作的通知 | 福州大学“星火奖教金”评选细则"),
        today=lambda: TODAY,
    )
    assert student(_request("星火奖学金的学生评选条件是什么？"), XINGHUO) is True
    assert teacher(_request("星火奖学金的学生评选条件是什么？"), XINGHUO) is False


# --------------------------------------------------------------------------- 本轮补充回归


def test_history_topic_switch_is_not_polluted() -> None:
    """上一轮问创新学分，本轮转问推免复试，不应被旧主题带跑。"""
    request = _request(
        "推免复试资格审查要交哪些材料？",
        history=["我想问创新学分认定", "数学建模竞赛拿了国家级二等奖"],
    )
    assert alpha_clarification_rule(request) is None


def test_shared_teacher_student_section_applies() -> None:
    """同一章节名同时标注教师与学生时为共同条款，学生问题可用。"""
    lookup = _full_lookup()

    def shared_heading(chunk_id):
        return ParsedChunk(
            chunk_no=1,
            content=XINGHUO.content,
            source_file_key="xinghuo.json",
            locator_note=json.dumps(
                {
                    "heading_path": [{
                        "level": 2,
                        "title": "关于做好2026年福州大学“星火奖教奖学金”评选工作的通知 | 评选工作共同条款（教师、学生均适用）",
                    }]
                },
                ensure_ascii=False,
            ),
        )

    check = build_alpha_evidence_check(
        lookup, chunk_lookup=shared_heading, today=lambda: TODAY
    )
    assert check(_request("星火奖学金的评选条件是什么？"), XINGHUO) is True


@pytest.mark.parametrize(
    "status",
    [RetrievalStatus.REVIEW_ONLY, RetrievalStatus.BLOCKED],
)
def test_real_review_only_and_blocked_are_rejected(status) -> None:
    """#31 真实状态：候选资料在 review_only / blocked 下不进入回答。"""
    meta = _meta(
        SCHOOL_SCHOLARSHIP,
        record_code="福大-2026-本科奖学金",
        applicability={"适用年级": "全体本科生", "适用专业": "全校相关本科专业"},
    )
    chunk = SCHOOL_SCHOLARSHIP.model_copy(update={"retrieval_status": status})
    check = build_alpha_evidence_check(
        _lookup_for((chunk, meta)), today=lambda: TODAY
    )
    assert check(_request("优秀学生综合奖学金一等奖要什么条件？"), chunk) is False


def test_individual_project_also_checks_semester_and_unit() -> None:
    """综测的学期与第一署名要求对个人项目同样适用。"""
    base = f"个人参赛，校级数学竞赛一等奖，{WORK}，"
    assert (
        alpha_clarification_rule(_request(f"{base}综测能加几分？"))
        == QUESTION_SEMESTER
    )
    assert (
        alpha_clarification_rule(
            _request(f"{base}成果是上一学期取得的，综测能加几分？")
        )
        == QUESTION_FIRST_UNIT
    )
    assert (
        alpha_clarification_rule(
            _request(
                f"{base}成果是上一学期取得的，以福州大学为第一署名单位，综测能加几分？"
            )
        )
        is None
    )


def test_positive_first_unit_is_recognised() -> None:
    """肯定表达（以福州大学为第一署名单位）算已回答，不再追问。"""
    query = (
        "综测里我们团队的校级竞赛最高等级奖，我是第二完成人，"
        "成果是上一学期取得的，并且以福州大学为第一署名单位，能加多少分？"
    )
    assert alpha_clarification_rule(_request(query)) is None
    assert _first_unit_state("以福州大学为第一署名单位") is True
    assert _first_unit_state("不是以福州大学为第一署名单位") is False


def test_review_detail_asks_degree_type_separately() -> None:
    """专业和学位类型分开追问，分组、材料投递也属于复试细节。"""
    assert (
        alpha_clarification_rule(_request("2026 年计算机技术招多少推免生？"))
        == QUESTION_DEGREE
    )
    assert (
        alpha_clarification_rule(_request("2026 年计算机技术专硕招多少推免生？")) is None
    )
    assert (
        alpha_clarification_rule(_request("推免复试分组怎么安排？"))
        == QUESTION_PROFESSION
    )
    assert (
        alpha_clarification_rule(_request("推免复试材料投递到哪？"))
        == QUESTION_PROFESSION
    )


def test_enrolment_year_grade_is_consistent() -> None:
    """2024 级在大三时的识别与证据判断保持一致。"""
    assert _grade_level("我是2024级", TODAY) == 3
    meta = _meta(
        QUALIFICATION_2027,
        record_code="计算机学院-2027-推免资格推荐",
        applicability={
            "适用年级": "2027届应届本科毕业生；大一至大三仅升学准备参考",
            "适用专业": "计算机科学与技术（含实验班）、数据科学与大数据技术、人工智能、信息安全、软件工程",
            "适用对象": "学院申请取得本科推免推荐资格的学生",
            "目标届别": "2027届",
        },
    )
    check = build_alpha_evidence_check(
        _lookup_for((QUALIFICATION_2027, meta)), today=lambda: TODAY
    )
    # 2024 级对应 2028 届，与 2027 届方案不匹配
    assert check(_request("我是2024级，2027届推免推荐资格怎么排名？"), QUALIFICATION_2027) is False
    assert check(_request("我是2023级，2027届推免推荐资格怎么排名？"), QUALIFICATION_2027) is True


def test_major_matching_is_explicit_not_fuzzy() -> None:
    """专业只做明确匹配或别名映射，不做计算机大类模糊放行。"""
    meta = _meta(
        QUALIFICATION_2027,
        record_code="计算机学院-2027-推免资格推荐",
        applicability={
            "适用年级": "2027届应届本科毕业生",
            "适用专业": "计算机科学与技术（含实验班）、数据科学与大数据技术、人工智能、信息安全、软件工程",
            "适用对象": "学院申请取得本科推免推荐资格的学生",
            "目标届别": "2027届",
        },
    )
    check = build_alpha_evidence_check(
        _lookup_for((QUALIFICATION_2027, meta)), today=lambda: TODAY
    )
    assert check(_request("计算机技术专业的2027届推免推荐资格怎么排名？"), QUALIFICATION_2027) is True
    assert check(_request("电子信息工程专业的2027届推免推荐资格怎么排名？"), QUALIFICATION_2027) is False


def test_historical_deadline_is_answered_not_dropped() -> None:
    """历史通知的截止时间与办理状态要作为历史信息回答，不直接丢证据。"""
    meta = _meta(
        XINGHUO,
        record_code="计算机学院-2026-星火奖学金",
        applicability={"学生对象": "正式学籍、在读全日制本科生和研究生", "年度": "2026年沿用2025细则"},
        deadline=date(2026, 4, 26),
    )
    lookup = _lookup_for((XINGHUO, meta))

    def student_heading(chunk_id):
        return ParsedChunk(
            chunk_no=1,
            content=XINGHUO.content,
            source_file_key="xinghuo.json",
            locator_note=json.dumps(
                {"heading_path": [{"level": 2, "title": "福州大学“星火奖学金”评选细则（学生）"}]},
                ensure_ascii=False,
            ),
        )

    check = build_alpha_evidence_check(
        lookup, chunk_lookup=student_heading, today=lambda: TODAY
    )
    assert check(_request("星火奖学金材料报送截止时间是什么？"), XINGHUO) is True

    # 现行资料且截止已过、问现在还能不能办，仍然拒绝
    current_meta = _meta(
        SCHOOL_SCHOLARSHIP,
        record_code="福大-2026-本科奖学金",
        applicability={"适用年级": "全体本科生", "适用专业": "全校相关本科专业"},
        deadline=date(2026, 10, 1),
    )
    current_check = build_alpha_evidence_check(
        _lookup_for((SCHOOL_SCHOLARSHIP, current_meta)), today=lambda: TODAY
    )
    assert current_check(
        _request("优秀学生综合奖学金现在还能申请吗？"), SCHOOL_SCHOLARSHIP
    ) is False


# --------------------------------------------------------------------------- 第六轮回归


def test_switch_competition_ignores_previous_level_and_team() -> None:
    """同一会话换竞赛，旧的级别、团队、作品不能盖掉本轮表达。"""
    history = ["数学建模竞赛拿了国家级二等奖", f"团队作品，{WORK}"]
    query = "蓝桥杯省赛二等奖，个人参赛，创新学分能认定多少？"
    request = _request(query, history=history)
    # 本轮没说作品，不能被上一场竞赛的作品顶替
    assert alpha_clarification_rule(request) == QUESTION_WORK_NAME
    assert _level_for(query, "\n".join(history) + "\n" + query) == "provincial"
    assert _team(query) is False

    completed = _request(f"蓝桥杯省赛二等奖，个人参赛，{WORK}，创新学分能认定多少？", history=history)
    assert alpha_clarification_rule(completed) is None


def test_switch_from_review_to_qualification() -> None:
    """先问复试，再问推荐资格，子场景按本轮问题判断。"""
    review_then_qualification = _request(
        "推免资格要求专业排名前多少？", history=["推免复试都考什么？"]
    )
    assert alpha_clarification_rule(review_then_qualification) is None

    qualification_then_review = _request(
        "推免复试材料投递到哪？", history=["推免资格要求专业排名前多少？"]
    )
    # 复试材料不追问年级，只确认专业
    assert alpha_clarification_rule(qualification_then_review) == QUESTION_PROFESSION


def test_review_question_with_personal_pronoun_does_not_ask_grade() -> None:
    assert alpha_clarification_rule(_request("我想知道推免复试都考什么")) is None


def test_team_needs_explicit_team_wording() -> None:
    assert _team("我们") is None
    assert _team("我们组") is True
    assert _team("团队作品") is True
    assert _team("个人参赛") is False


def test_negated_level_is_not_national() -> None:
    assert _level("不是国家级，是省级二等奖") == "provincial"
    assert _level("国家级二等奖") == "national"
    query = f"蓝桥杯不是国家级，是省级二等奖，{WORK}，团队作品，第一完成人，创新学分能认定多少？"
    assert alpha_clarification_rule(_request(query)) is None


def test_school_level_evaluation_uses_bylaw_not_grade_catalog() -> None:
    """校级、院级综测得用综评办法，学科竞赛等级目录不负责这两档。"""
    check = build_alpha_evidence_check(
        _full_lookup(), chunk_lookup=_student_locator, today=lambda: TODAY
    )
    query = "综测里校级竞赛最高等级奖能加几分？"
    assert check(_request(query), EVALUATION_BYLAW) is True

    eval_meta = _meta(
        EVAL_CATALOG,
        record_code="福大-2026-学科竞赛等级目录",
        applicability={"适用年级": "全体本科生", "适用专业": "全校相关本科专业"},
    )
    catalog_check = build_alpha_evidence_check(
        _lookup_for((EVAL_CATALOG, eval_meta)),
        chunk_lookup=_student_locator,
        today=lambda: TODAY,
    )
    # 等级目录不负责校级、院级两档
    assert catalog_check(_request(query), EVAL_CATALOG) is False
    # 国家级仍必须由等级目录定档
    assert catalog_check(
        _request("综测里国家级竞赛二等奖能加几分？"), EVAL_CATALOG
    ) is True


def test_expired_notice_answers_history_but_not_current_application() -> None:
    """过期通知能回答历史截止时间，不能回答“现在还能不能申请”。"""
    lookup = _full_lookup()

    def student_heading(chunk_id):
        return ParsedChunk(
            chunk_no=1,
            content=XINGHUO.content,
            source_file_key="xinghuo.json",
            locator_note=json.dumps(
                {"heading_path": [{"level": 2, "title": "福州大学“星火奖学金”评选细则（学生）"}]},
                ensure_ascii=False,
            ),
        )

    check = build_alpha_evidence_check(
        lookup, chunk_lookup=student_heading, today=lambda: TODAY
    )
    assert check(_request("星火奖学金去年截止到什么时候？"), XINGHUO) is True
    assert check(_request("星火奖学金现在还能申请吗？"), XINGHUO) is False


# --------------------------------------------------------------------------- 第七轮回归


def _qualification_check():
    meta = _meta(
        QUALIFICATION_2027,
        record_code="计算机学院-2027-推免资格推荐",
        applicability={
            "适用年级": "2027届应届本科毕业生；大一至大三仅升学准备参考",
            "适用专业": "计算机科学与技术（含实验班）、数据科学与大数据技术、人工智能、信息安全、软件工程",
            "适用对象": "学院申请取得本科推免推荐资格的学生",
            "目标届别": "2027届",
        },
    )
    return build_alpha_evidence_check(
        _lookup_for((QUALIFICATION_2027, meta)), today=lambda: TODAY
    )


@pytest.mark.parametrize("grade", ["大一", "大二", "大三"])
def test_lower_grade_cannot_use_reference_note_for_qualification(grade: str) -> None:
    """大一至大三仅升学准备参考，不能据此通过正式推荐资格适用性。"""
    check = _qualification_check()
    query = f"我是{grade}，2027届推免推荐资格怎么排名？"
    assert check(_request(query), QUALIFICATION_2027) is False


def test_lower_grade_can_read_preparation_questions() -> None:
    check = _qualification_check()
    assert check(_request("我是大二，2027届推免要提前准备什么？"), QUALIFICATION_2027) is True


def test_senior_grade_matches_formal_eligibility() -> None:
    check = _qualification_check()
    assert check(_request("我是大四，2027届推免推荐资格怎么排名？"), QUALIFICATION_2027) is True


def test_rank_is_not_inherited_across_competitions() -> None:
    """上一场数学建模的第二完成人不能带到蓝桥杯团队作品。"""
    history = [f"数学建模竞赛国家级二等奖，团队作品，{WORK}，我是第二完成人"]
    query = "蓝桥杯省赛二等奖，团队作品，作品《校园二手交易平台》，创新学分能认定多少？"
    assert alpha_clarification_rule(_request(query, history=history)) == QUESTION_TOP_EIGHT


def test_rank_is_not_inherited_across_works() -> None:
    """同一竞赛换了作品，旧排名不属于新作品。"""
    history = [f"数学建模竞赛国家级二等奖，团队作品，{WORK}，我是第二完成人"]
    query = "数学建模竞赛省级二等奖，团队作品，作品《空气质量预测模型》，创新学分能认定多少？"
    assert alpha_clarification_rule(_request(query, history=history)) == QUESTION_TOP_EIGHT


def test_rank_is_reused_for_same_competition_and_work() -> None:
    history = [f"数学建模竞赛国家级二等奖，团队作品，{WORK}，我是第二完成人"]
    query = f"数学建模竞赛国家级二等奖，团队作品，{WORK}，创新学分能认定多少？"
    assert alpha_clarification_rule(_request(query, history=history)) is None


def test_clarification_honours_injected_today() -> None:
    """追问与证据判断共用同一时间源。"""
    query = "2029 年推免政策是什么？"
    assert alpha_clarification_rule(_request(query), today=lambda: date(2026, 11, 19)) is None
    assert (
        alpha_clarification_rule(_request(query), today=lambda: date(2030, 1, 1))
        == QUESTION_RECOMMENDATION_OBJECT
    )


# --------------------------------------------------------------------------- 第八轮回归


def test_explicit_grade_without_applicability_is_rejected() -> None:
    """明确问了年级、资料没有适用年级时不能放行，句子里没有“我”也一样。"""
    meta = _meta(
        SCHOOL_SCHOLARSHIP,
        record_code="福大-2026-本科奖学金",
        applicability={"适用专业": "全校相关本科专业"},
    )
    check = build_alpha_evidence_check(
        _lookup_for((SCHOOL_SCHOLARSHIP, meta)), today=lambda: TODAY
    )
    assert check(_request("大三学生能申请优秀学生综合奖学金吗？"), SCHOOL_SCHOLARSHIP) is False
    # 没指定年级时不受这条影响
    assert check(_request("优秀学生综合奖学金一等奖要什么条件？"), SCHOOL_SCHOLARSHIP) is True


def test_explicit_major_without_applicability_is_rejected() -> None:
    """明确问了专业、资料没有适用专业时同样 fail-closed。"""
    meta = _meta(
        SCHOOL_SCHOLARSHIP,
        record_code="福大-2026-本科奖学金",
        applicability={"适用年级": "全体本科生"},
    )
    check = build_alpha_evidence_check(
        _lookup_for((SCHOOL_SCHOLARSHIP, meta)), today=lambda: TODAY
    )
    assert check(
        _request("计算机科学与技术专业能申请优秀学生综合奖学金吗？"), SCHOOL_SCHOLARSHIP
    ) is False
    assert check(_request("优秀学生综合奖学金一等奖要什么条件？"), SCHOOL_SCHOLARSHIP) is True


def test_work_name_without_book_marks_is_recognised() -> None:
    assert _works("作品名称叫城市交通流量预测") == {"城市交通流量预测"}
    assert _works("作品叫空气质量预测平台") == {"空气质量预测平台"}
    assert _works("论文题目是基于深度学习的图像分割") == {"基于深度学习的图像分割"}
    # “成果是上一学期取得的”不能被当成作品名
    assert _works("成果是上一学期取得的") == set()


def test_rank_is_not_inherited_across_unquoted_works() -> None:
    """同一竞赛、作品名称不带书名号但换了作品，也不能继承旧排名。"""
    history = [f"数学建模竞赛国家级二等奖，团队作品，{WORK}，我是第二完成人"]
    query = "数学建模竞赛省级二等奖，团队作品，作品名称叫空气质量预测平台，创新学分能认定多少？"
    assert alpha_clarification_rule(_request(query, history=history)) == QUESTION_TOP_EIGHT


# --------------------------------------------------------------------------- 第九轮回归


def test_preparation_wording_cannot_bypass_formal_eligibility() -> None:
    """“提前准备”不能盖过正式资格/排名意图。"""
    check = _qualification_check()
    assert check(
        _request("我是大二，想提前准备2027届推免推荐资格排名，现在能做什么？"),
        QUALIFICATION_2027,
    ) is False
    # 纯准备性问题仍按参考口径放行
    assert check(_request("我是大二，2027届推免要提前准备什么？"), QUALIFICATION_2027) is True


def test_external_college_without_college_field_is_rejected() -> None:
    """资料没有学院字段时，其他学院的问题同样 fail-closed。"""
    meta = _meta(
        QUALIFICATION_2027,
        record_code="计算机学院-2027-推免资格推荐",
        applicability={
            "适用年级": "2027届应届本科毕业生；大一至大三仅升学准备参考",
            "适用专业": "计算机科学与技术（含实验班）、数据科学与大数据技术、人工智能、信息安全、软件工程",
            "目标届别": "2027届",
        },
    )
    check = build_alpha_evidence_check(
        _lookup_for((QUALIFICATION_2027, meta)), today=lambda: TODAY
    )
    assert check(
        _request("数学与统计学院的2027届推免推荐资格怎么排名？"), QUALIFICATION_2027
    ) is False
    assert check(_request("2027届推免推荐资格怎么排名？"), QUALIFICATION_2027) is True


def test_rank_is_not_reused_without_current_work() -> None:
    """同一竞赛但本轮没说作品，不能继承历史排名。"""
    history = [f"数学建模竞赛国家级二等奖，团队作品，{WORK}，我是第二完成人"]
    query = (
        "数学建模竞赛校级最高等级奖，团队作品，综测能加几分？"
        "成果是上一学期取得的，以福州大学为第一署名单位。"
    )
    assert alpha_clarification_rule(_request(query, history=history)) == QUESTION_ORDER


# --------------------------------------------------------------------------- S4 学院资源


def _resource_meta(
    chunk: RetrievedChunk,
    *,
    record_code: str = "计算机学院-2026-青禾计划",
    category: str = "",
    directions: tuple[str, ...] = ("COLLEGE_RESOURCES",),
    applicability: dict[str, str] | None = None,
    deadline: date | None = None,
    approved: bool = True,
    policy_status: str = "当前有效",
) -> DocumentMetadata:
    return _meta(
        chunk,
        record_code=record_code,
        category=category,
        directions=directions,
        document_type="学院资源",
        applicability=applicability,
        deadline=deadline,
        approved=approved,
        policy_status=policy_status,
    )


LAB_NOTICE = _chunk(
    index=201,
    title="关于开展2026年青禾计划实验室招募的通知",
    content=(
        "青禾计划实验室需求一览表：EDA实验室，接收人数5人，"
        "联系人：张老师，联系电话：13800000000，报名截止2026-10-31。"
    ),
    timeliness=TimelinessVerificationStatus.HISTORICAL,
    source_url="https://ccds.fzu.edu.cn/",
)
LAB_INTRO = _chunk(
    index=202,
    title="计算机学院实验室研究方向简介",
    content="EDA实验室研究方向为集成电路设计自动化，科研成果见教师主页。",
    source_url="https://ccds.fzu.edu.cn/",
)
COLLEGE_CONTACT = _chunk(
    index=203,
    title="计算机与大数据学院公开联系方式",
    content="学院办公室电话：0591-2286XXXX，办公地点：旗山校区计算机学院楼。",
    source_url="https://ccds.fzu.edu.cn/",
)
COMPETITION_NOTICE = _chunk(
    index=204,
    title="关于组织参加第十七届蓝桥杯报名的通知",
    content="学院竞赛报名通知：蓝桥杯报名截止2026-09-30，报名入口见学院通知。",
    source_url="https://ccds.fzu.edu.cn/",
)
PLAN = _chunk(
    index=205,
    title="计算机科学与技术专业培养方案（2026版）",
    content="培养方案规定课程、实践与学位学分要求。",
    source_url="https://ccds.fzu.edu.cn/",
)


def _check_for(*pairs: tuple[RetrievedChunk, DocumentMetadata]):
    return build_alpha_evidence_check(
        _lookup_for(*pairs), today=lambda: TODAY
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("学院有什么资源？", QUESTION_RESOURCE_TYPE),
        ("资源怎么找？", QUESTION_RESOURCE_TYPE),
        ("学院有哪些实验室？", None),
        ("EDA实验室是研究什么的？", None),
        ("EDA实验室怎么样？", QUESTION_LAB_PURPOSE),
        ("EDA实验室现在招人吗？", None),
        ("EDA实验室地址在哪？", None),
        ("我大二能进EDA实验室吗？", None),
        ("计算机专业培养方案有哪些课程？", None),
        ("培养方案在哪看？", QUESTION_PLAN_SCOPE),
        ("学院通知在哪看？", None),
        ("学院办公室电话是多少？", None),
        ("学院有哪些竞赛可以报名？", None),
    ],
)
def test_s4_clarification(query: str, expected: str | None) -> None:
    assert alpha_clarification_rule(_request(query)) == expected


def test_s4_context_followup_does_not_lose_resource_topic() -> None:
    history = ["学院有哪些实验室？"]
    assert alpha_clarification_rule(_request("EDA 那个招几个？", history=history)) is None
    assert _analyse("学院有哪些实验室？\nEDA 那个招几个？", "EDA 那个招几个？")[0] == RESOURCES


def test_s4_topic_switch_does_not_inherit_lab() -> None:
    history = ["EDA 实验室现在招人吗？"]
    assert alpha_clarification_rule(_request("学院办公室电话是多少？", history=history)) is None
    assert _analyse(
        "EDA 实验室现在招人吗？\n学院办公室电话是多少？", "学院办公室电话是多少？"
    )[0] == RESOURCES


def test_s4_lab_recruitment_requires_applicability() -> None:
    meta_ok = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术", "适用对象": "全体本科生"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta_ok))
    assert check(_request("我大二能进EDA实验室吗？"), LAB_NOTICE) is True

    meta_missing = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability=None,
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta_missing))
    assert check(_request("我大二能进EDA实验室吗？"), LAB_NOTICE) is False


def test_s4_lab_grade_missing_field_is_rejected() -> None:
    meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用专业": "计算机科学与技术"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta))
    assert check(_request("我大二能进EDA实验室吗？"), LAB_NOTICE) is False


def test_s4_lab_intro_cannot_answer_recruitment() -> None:
    # 标题里带“实验室”不影响定类；R4 的适用范围给全，仍不能回答 R3 招募问题。
    meta = _resource_meta(
        LAB_INTRO,
        category="研究方向与公开介绍",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
        deadline=None,
    )
    check = _check_for((LAB_INTRO, meta))
    assert check(_request("EDA实验室研究什么？"), LAB_INTRO) is True
    assert check(_request("EDA实验室现在招人吗？"), LAB_INTRO) is False
    assert check(_request("EDA实验室现在还招几个？"), LAB_INTRO) is False


def test_s4_lab_notice_cannot_answer_research_intro() -> None:
    # 反向隔离：R3 招募通知即使适用范围完整，也不能冒充 R4 研究方向介绍。
    meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta))
    assert check(_request("EDA实验室研究什么？"), LAB_NOTICE) is False
    assert check(_request("EDA实验室的研究方向是什么？"), LAB_NOTICE) is False
    assert check(_request("EDA实验室怎么报名？"), LAB_NOTICE) is True


def test_s4_expired_recruitment_allows_history_but_not_current_quota() -> None:
    meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta))
    assert check(_request("EDA实验室怎么报名？"), LAB_NOTICE) is True
    assert check(_request("EDA实验室现在还招几个？"), LAB_NOTICE) is False
    assert check(_request("EDA实验室现在还招吗？"), LAB_NOTICE) is True


def test_s4_lab_contact_is_not_college_contact() -> None:
    meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta))
    assert check(_request("学院办公室电话是多少？"), LAB_NOTICE) is False


def test_s4_contact_requires_official_source() -> None:
    meta = _resource_meta(
        COLLEGE_CONTACT, record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式", applicability=None,
    )
    check = _check_for((COLLEGE_CONTACT, meta))
    assert check(_request("学院办公室电话是多少？"), COLLEGE_CONTACT) is True

    unofficial = _chunk(
        index=206,
        title="学院联系方式汇总",
        content="学院办公室电话：0591-2286XXXX。",
        source_url="https://example.invalid/contact",
        publisher="某网站",
    )
    meta = _resource_meta(
        unofficial, record_code="福大-2026-公开信息",
        category="学院公开信息与联系方式", applicability=None,
    )
    check = _check_for((unofficial, meta))
    assert check(_request("学院办公室电话是多少？"), unofficial) is False


def test_s4_curriculum_requires_scope() -> None:
    meta = _resource_meta(
        PLAN,
        record_code="计算机学院-2026-培养方案",
        category="培养方案与课程",
        applicability={"适用年级": "大二", "适用专业": "计算机科学与技术"},
    )
    check = _check_for((PLAN, meta))
    assert check(_request("计算机专业培养方案有哪些课程？"), PLAN) is True
    assert check(_request("数学专业培养方案有哪些课程？"), PLAN) is False


def test_s4_competition_notice_is_resource_not_credit() -> None:
    meta = _resource_meta(
        COMPETITION_NOTICE,
        record_code="计算机学院-2026-竞赛报名",
        category="科研实践与竞赛",
        applicability={"适用年级": "全体本科生"},
    )
    check = _check_for((COMPETITION_NOTICE, meta))
    assert check(_request("学院有哪些竞赛可以报名？"), COMPETITION_NOTICE) is True
    assert check(_request("蓝桥杯获奖能加多少创新学分？"), COMPETITION_NOTICE) is False


def test_s4_document_without_direction_code_is_rejected() -> None:
    meta = _resource_meta(
        LAB_INTRO, category="研究方向与公开介绍", directions=()
    )
    check = _check_for((LAB_INTRO, meta))
    assert check(_request("EDA实验室研究什么？"), LAB_INTRO) is False


def test_s4_external_college_is_rejected_without_college_field() -> None:
    meta = _resource_meta(
        LAB_INTRO, category="研究方向与公开介绍", applicability=None
    )
    check = _check_for((LAB_INTRO, meta))
    assert check(_request("数学与统计学院的实验室研究什么？"), LAB_INTRO) is False
    assert check(_request("EDA实验室研究什么？"), LAB_INTRO) is True


def test_s4_unapproved_or_missing_metadata_is_rejected() -> None:
    meta = _resource_meta(
        LAB_INTRO, category="研究方向与公开介绍", approved=False
    )
    check = _check_for((LAB_INTRO, meta))
    assert check(_request("EDA实验室研究什么？"), LAB_INTRO) is False
    missing = build_alpha_evidence_check(lambda version_id: None, today=lambda: TODAY)
    assert missing(_request("EDA实验室研究什么？"), LAB_INTRO) is False


@pytest.mark.parametrize(
    "url",
    [
        "http://ccds.fzu.edu.cn/",
        "https://ccds.fzu.edu.cn.evil.com/",
        "https://fzu.edu.cn.attacker.com/contact",
        "https://evil.com/?u=https://ccds.fzu.edu.cn/",
        "https://user:pass@ccds.fzu.edu.cn/",
        "https://ccds.fzu.edu.cn:8443/",
        "https://ccds.fzu.edu.cn@evil.com/",
        "https://sub.ccds.fzu.edu.cn/",
        "https://ccds.fzu.edu.cn%00.evil.com/",
    ],
)
def test_s4_official_url_rejects_spoofing(url: str) -> None:
    chunk = _chunk(
        index=300,
        title="计算机与大数据学院公开联系方式",
        content="学院办公室电话：0591-2286XXXX。",
        source_url=url,
    )
    meta = _resource_meta(
        chunk, record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式", applicability=None,
    )
    check = _check_for((chunk, meta))
    assert check(_request("学院办公室电话是多少？"), chunk) is False


def test_s4_r6_requires_college_direct_page() -> None:
    news = _chunk(
        index=301,
        title="计算机与大数据学院公开联系方式",
        content="学院办公室电话：0591-2286XXXX。",
        source_url="https://news.fzu.edu.cn/",
    )
    meta = _resource_meta(
        news, record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式", applicability=None,
    )
    check = _check_for((news, meta))
    assert check(_request("学院办公室电话是多少？"), news) is False


def test_s4_r1_official_channel_hosts() -> None:
    channel = _chunk(
        index=302,
        title="教务处办事指南",
        content="办事指南入口与材料清单见教务处办事指南栏目。",
        source_url="https://jwch.fzu.edu.cn/bszn.htm",
    )
    meta = _resource_meta(
        channel, record_code="福大-2026-教务处办事指南",
        category="通知与办事渠道", applicability={"适用对象": "本科生"},
    )
    check = _check_for((channel, meta))
    assert check(_request("教务处办事指南在哪看？"), channel) is True

    bare = _chunk(
        index=309,
        title="福州大学办事入口",
        content="学校办事入口与材料清单见官网。",
        source_url="https://fzu.edu.cn/",
    )
    bare_meta = _resource_meta(
        bare, record_code="福大-2026-办事入口",
        category="通知与办事渠道", applicability={"适用对象": "本科生"},
    )
    bare_check = _check_for((bare, bare_meta))
    assert bare_check(_request("学校办事入口在哪看？"), bare) is True


def test_s4_wechat_verified_college_account_is_allowed(monkeypatch) -> None:
    # 生产白名单暂不登记未核实 ID；测试用 fixture 注入占位账号验证核验逻辑。
    monkeypatch.setattr(business_rules, "COLLEGE_WECHAT_IDS", {"gh_college"})
    article = _chunk(
        index=303,
        title="计算机与大数据学院公开联系方式",
        content="学院办公室电话：0591-2286XXXX。",
        source_url="https://mp.weixin.qq.com/s/verified-article",
    )
    meta = _resource_meta(
        article, record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式", applicability=None,
    )
    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "福州大学计算机学院",
            "account_id": "gh_college",
            "basis": "学院官网底部公众号入口与公众号主体信息页",
        },
    }
    check = _check_for((article, meta))
    assert check(_request("学院办公室电话是多少？"), article) is True


def test_s4_wechat_requires_identity_verification() -> None:
    article = _chunk(
        index=304,
        title="计算机与大数据学院公开联系方式",
        content="学院办公室电话：0591-2286XXXX。",
        source_url="https://mp.weixin.qq.com/s/unverified-article",
    )
    meta = _resource_meta(
        article, record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式", applicability=None,
    )
    meta.temporal_notes = {"human_approved": True}
    check = _check_for((article, meta))
    assert check(_request("学院办公室电话是多少？"), article) is False

    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "福州大学计算机学院",
            "account_id": "",
            "basis": "昵称看起来像官方号",
        },
    }
    assert check(_request("学院办公室电话是多少？"), article) is False

    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "福大计算机青年备用号",
            "account_id": "gh_fake",
            "basis": "文章标题自称官方",
        },
    }
    assert check(_request("学院办公室电话是多少？"), article) is False


def test_s4_school_wechat_is_not_college_contact() -> None:
    article = _chunk(
        index=305,
        title="计算机与大数据学院公开联系方式",
        content="学院办公室电话：0591-2286XXXX。",
        source_url="https://mp.weixin.qq.com/s/school-article",
    )
    meta = _resource_meta(
        article, record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式", applicability=None,
    )
    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "福州大学",
            "account_id": "ifzu1958",
            "basis": "学校官网公众号入口",
        },
    }
    check = _check_for((article, meta))
    assert check(_request("学院办公室电话是多少？"), article) is False

    # 同一账号在学校新闻语境下可以回答问题，但只限学校层面内容。
    news = _chunk(
        index=308,
        title="福州大学校园新闻",
        content="学校本周举办校园开放日，新闻详情见官方公众号。",
        source_url="https://mp.weixin.qq.com/s/school-news",
    )
    news_meta = _resource_meta(
        news, record_code="福大-2026-校园新闻",
        category="通知与办事渠道", applicability={"适用对象": "本科生"},
    )
    news_meta.temporal_notes = dict(meta.temporal_notes)
    news_check = _check_for((news, news_meta))
    assert news_check(_request("学校新闻在哪看？"), news) is True


def test_s4_admission_wechat_only_in_admission_scope() -> None:
    article = _chunk(
        index=306,
        title="福州大学招生简章入口",
        content="招生简章与报考指南入口。",
        source_url="https://mp.weixin.qq.com/s/admission-article",
    )
    meta = _resource_meta(
        article, record_code="福大-2026-招生简章",
        category="通知与办事渠道", applicability={"适用对象": "本科生"},
    )
    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "福州大学招生考试中心",
            "account_id": "fzuzsks",
            "basis": "招生考试中心官网公众号入口",
        },
    }
    check = _check_for((article, meta))
    assert check(_request("招生简章在哪看？"), article) is True
    assert check(_request("学院通知公告在哪看？"), article) is False


def test_s4_unknown_category_is_rejected() -> None:
    meta = _resource_meta(
        LAB_INTRO, category="学院资源导航", applicability=None
    )
    check = _check_for((LAB_INTRO, meta))
    assert check(_request("EDA实验室研究什么？"), LAB_INTRO) is False


def test_s4_r4_category_is_not_inferred_from_body_keywords() -> None:
    # 正文出现“电话”也不能把 R4 改成 R6；R4 只按 category_name 定类。
    intro = _chunk(
        index=307,
        title="EDA实验室简介",
        content="研究方向为集成电路设计自动化。联系电话仅用于实验室内部。",
        source_url="https://ccds.fzu.edu.cn/",
    )
    meta = _resource_meta(
        intro, category="研究方向与公开介绍", applicability=None
    )
    check = _check_for((intro, meta))
    assert check(_request("EDA实验室研究什么？"), intro) is True
    assert check(_request("学院办公室电话是多少？"), intro) is False


def test_s4_applicability_key_conflict_is_rejected() -> None:
    meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "大二", "grade": "大三"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta))
    assert check(_request("我大二能进EDA实验室吗？"), LAB_NOTICE) is False


def test_s4_legacy_applicability_keys_still_work() -> None:
    meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"grade": "大二", "major": "计算机科学与技术", "target": "本科生"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta))
    assert check(_request("我大二能进EDA实验室吗？"), LAB_NOTICE) is True


# --------------------------------------------------------------------------- 历史政策与现行政策


HISTORICAL_SCHOLARSHIP_2025 = _chunk(
    index=207,
    title="福州大学2025年本科生奖学金评定管理办法",
    content="2025年优秀学生综合奖学金一等奖金额为1500元，参评条件以当年通知为准。",
    timeliness=TimelinessVerificationStatus.HISTORICAL,
    published_on=date(2025, 5, 20),
)


def _historical_check():
    meta = _meta(
        HISTORICAL_SCHOLARSHIP_2025,
        record_code="福大-2025-本科奖学金",
        applicability={"适用年度": "2025年", "适用年级": "全体本科生"},
    )
    return build_alpha_evidence_check(
        _lookup_for((HISTORICAL_SCHOLARSHIP_2025, meta)), today=lambda: TODAY
    )


def test_historical_notice_answers_history_but_not_current_policy() -> None:
    check = _historical_check()
    assert check(
        _request("2025年优秀学生综合奖学金一等奖是什么条件？"), HISTORICAL_SCHOLARSHIP_2025
    ) is True
    assert check(
        _request("现在优秀学生综合奖学金一等奖是什么条件？"), HISTORICAL_SCHOLARSHIP_2025
    ) is False


def test_superseded_policy_only_answers_explicit_history() -> None:
    meta = _meta(
        SUPERSEDED_SCHOLARSHIP,
        record_code="福大-2024-本科奖学金",
        applicability={"适用年级": "全体本科生"},
        policy_status="已被替代",
    )
    check = build_alpha_evidence_check(
        _lookup_for((SUPERSEDED_SCHOLARSHIP, meta)), today=lambda: TODAY
    )
    assert check(
        _request("2024年的旧奖学金办法里一等奖是什么条件？"), SUPERSEDED_SCHOLARSHIP
    ) is True
    assert check(
        _request("现在的奖学金一等奖是什么条件？"), SUPERSEDED_SCHOLARSHIP
    ) is False


def test_uncertain_policy_version_is_rejected() -> None:
    meta = _meta(
        SCHOOL_SCHOLARSHIP,
        record_code="福大-2026-本科奖学金",
        applicability={"适用年级": "全体本科生"},
        policy_status="无法确认是否为现行版本",
    )
    check = build_alpha_evidence_check(
        _lookup_for((SCHOOL_SCHOLARSHIP, meta)), today=lambda: TODAY
    )
    assert check(
        _request("现在的优秀学生综合奖学金一等奖是什么条件？"), SCHOOL_SCHOLARSHIP
    ) is False


def test_metadata_identity_mismatch_is_rejected() -> None:
    meta = _meta(
        SCHOOL_SCHOLARSHIP,
        record_code="福大-2026-本科奖学金",
        title="另一份奖学金办法",
        applicability={"适用年级": "全体本科生"},
    )
    check = build_alpha_evidence_check(
        _lookup_for((SCHOOL_SCHOLARSHIP, meta)), today=lambda: TODAY
    )
    assert check(_request("优秀学生综合奖学金一等奖是什么条件？"), SCHOOL_SCHOLARSHIP) is False


def test_metadata_lookup_exception_is_rejected() -> None:
    def explode(version_id):
        raise RuntimeError("元数据读取失败")

    check = build_alpha_evidence_check(explode, today=lambda: TODAY)
    assert check(_request("优秀学生综合奖学金一等奖是什么条件？"), SCHOOL_SCHOLARSHIP) is False


def test_human_approval_must_be_strict_true() -> None:
    meta = _meta(
        SCHOOL_SCHOLARSHIP,
        record_code="福大-2026-本科奖学金",
        applicability={"适用年级": "全体本科生"},
    )
    meta.temporal_notes = {"human_approved": "true"}
    check = build_alpha_evidence_check(
        _lookup_for((SCHOOL_SCHOLARSHIP, meta)), today=lambda: TODAY
    )
    assert check(_request("优秀学生综合奖学金一等奖是什么条件？"), SCHOOL_SCHOLARSHIP) is False



# --------------------------------------------------------------------------- 第二轮整改


def test_scenario_detection_prefers_actual_intent() -> None:
    """推免语境里的竞赛经历、竞赛计分不能被关键词抢成竞赛认定。"""
    assert _detect("推免要求竞赛经历吗")[0] == RECOMMENDATION
    assert _purpose("竞赛获奖在推免时加多少分") == PURPOSE_EVALUATION
    assert _detect("竞赛获奖在推免时加多少分") == (
        RECOMMENDATION,
        PURPOSE_EVALUATION,
    )
    assert _detect("奖学金通知在哪看")[0] == RESOURCES
    assert _detect("推免通知在哪看")[0] == RESOURCES
    # 明确问创新学分或综测加分时，仍按竞赛认定处理。
    assert _detect("推免时这个竞赛获奖能算创新学分吗")[0] == COMPETITION
    assert _detect("推免综测里竞赛获奖加几分")[0] == COMPETITION


def test_recommendation_with_competition_uses_qualification_policy() -> None:
    check = _qualification_check()
    assert check(_request("推免要求竞赛经历吗"), QUALIFICATION_2027) is True


def test_notice_channel_queries_are_resources() -> None:
    notice = _chunk(
        index=210,
        title="学院通知公告",
        content="学院通知公告入口见学院官网“学院通知”栏目。",
        source_url="https://ccds.fzu.edu.cn/xwzx/xytz.htm",
    )
    meta = _resource_meta(
        notice,
        record_code="计算机学院-2026-通知渠道",
        category="通知与办事渠道",
        applicability={"适用对象": "本科生"},
    )
    check = _check_for((notice, meta))
    assert check(_request("奖学金通知在哪看？"), notice) is True
    assert check(_request("推免通知在哪看？"), notice) is True


def test_historical_policy_requires_matching_year() -> None:
    check = _historical_check()
    # 同年度历史查询可用。
    assert check(
        _request("2025年优秀学生综合奖学金一等奖是什么条件？"),
        HISTORICAL_SCHOLARSHIP_2025,
    ) is True
    # 跨年度错配不能拿 2025 办法回答 2024 问题。
    assert check(
        _request("2024年优秀学生综合奖学金一等奖是什么条件？"),
        HISTORICAL_SCHOLARSHIP_2025,
    ) is False
    # 未指定年度的现行口径不能落到旧政策。
    assert check(
        _request("优秀学生综合奖学金一等奖是什么条件？"),
        HISTORICAL_SCHOLARSHIP_2025,
    ) is False
    # 相对年度能和资料年度对上时，可回答历史口径。
    assert check(
        _request("去年优秀学生综合奖学金一等奖是什么条件？"),
        HISTORICAL_SCHOLARSHIP_2025,
    ) is True


def test_historical_deadline_status_is_answered_not_rejected() -> None:
    meta = _meta(
        HISTORICAL_SCHOLARSHIP_2025,
        record_code="福大-2025-本科奖学金",
        applicability={"适用年度": "2025年", "适用年级": "全体本科生"},
        deadline=date(2025, 10, 31),
    )
    check = build_alpha_evidence_check(
        _lookup_for((HISTORICAL_SCHOLARSHIP_2025, meta)), today=lambda: TODAY
    )
    assert check(
        _request("2025年奖学金报名截止到什么时候？"), HISTORICAL_SCHOLARSHIP_2025
    ) is True
    assert check(
        _request("2025年奖学金还能报名吗？"), HISTORICAL_SCHOLARSHIP_2025
    ) is True
    assert check(
        _request("现在还能报名吗？"), HISTORICAL_SCHOLARSHIP_2025
    ) is False


def test_historical_quota_is_answered_but_current_quota_is_rejected() -> None:
    meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta))
    assert check(_request("2026年青禾计划当时招几个学生？"), LAB_NOTICE) is True
    assert check(_request("青禾计划2026年招几个学生？"), LAB_NOTICE) is True
    assert check(_request("EDA实验室现在还招几个？"), LAB_NOTICE) is False
    assert check(_request("EDA实验室现在还剩几个名额？"), LAB_NOTICE) is False


def test_multicategory_resource_query_judges_each_category() -> None:
    lab_meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
        deadline=date(2026, 10, 31),
    )
    plan_meta = _resource_meta(
        PLAN,
        record_code="计算机学院-2026-培养方案",
        category="培养方案与课程",
        applicability={"适用年级": "大二", "适用专业": "计算机科学与技术"},
    )
    contact_meta = _resource_meta(
        COLLEGE_CONTACT,
        record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式",
        applicability=None,
    )
    check = _check_for(
        (LAB_NOTICE, lab_meta), (PLAN, plan_meta), (COLLEGE_CONTACT, contact_meta)
    )
    query = "实验室和培养方案都讲讲"
    assert check(_request(query), LAB_NOTICE) is True
    assert check(_request(query), PLAN) is True
    # 多类别查询不能把没问的 R6 也放进来。
    assert check(_request(query), COLLEGE_CONTACT) is False


def test_multicategory_notice_and_lab_query() -> None:
    notice = _chunk(
        index=211,
        title="学院通知公告",
        content="学院通知公告入口见学院官网“学院通知”栏目。",
        source_url="https://ccds.fzu.edu.cn/xwzx/xytz.htm",
    )
    notice_meta = _resource_meta(
        notice,
        record_code="计算机学院-2026-通知渠道",
        category="通知与办事渠道",
        applicability={"适用对象": "本科生"},
    )
    lab_meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
        deadline=date(2026, 10, 31),
    )
    plan_meta = _resource_meta(
        PLAN,
        record_code="计算机学院-2026-培养方案",
        category="培养方案与课程",
        applicability={"适用年级": "大二", "适用专业": "计算机科学与技术"},
    )
    check = _check_for(
        (notice, notice_meta), (LAB_NOTICE, lab_meta), (PLAN, plan_meta)
    )
    query = "学院通知在哪看，实验室怎么报名"
    assert check(_request(query), notice) is True
    assert check(_request(query), LAB_NOTICE) is True
    assert check(_request(query), PLAN) is False


def test_multicategory_contact_and_practice_query() -> None:
    contact_meta = _resource_meta(
        COLLEGE_CONTACT,
        record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式",
        applicability=None,
    )
    practice_meta = _resource_meta(
        COMPETITION_NOTICE,
        record_code="计算机学院-2026-竞赛报名",
        category="科研实践与竞赛",
        applicability={"适用年级": "全体本科生"},
    )
    lab_meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for(
        (COLLEGE_CONTACT, contact_meta),
        (COMPETITION_NOTICE, practice_meta),
        (LAB_NOTICE, lab_meta),
    )
    query = "学院办公室电话和竞赛报名入口"
    assert check(_request(query), COLLEGE_CONTACT) is True
    assert check(_request(query), COMPETITION_NOTICE) is True
    assert check(_request(query), LAB_NOTICE) is False


def test_multiturn_time_intent_is_isolated() -> None:
    """本轮明确时间优先，历史年份不能污染跨年度判断。"""
    check = _historical_check()
    history = ["2025年优秀学生综合奖学金一等奖是什么条件？"]
    assert check(
        _request("2024年优秀学生综合奖学金一等奖是什么条件？", history=history),
        HISTORICAL_SCHOLARSHIP_2025,
    ) is False
    assert check(
        _request("现在优秀学生综合奖学金一等奖是什么条件？", history=history),
        HISTORICAL_SCHOLARSHIP_2025,
    ) is False
    # 本轮没写时间时才继承上一轮年度。
    assert check(
        _request("优秀学生综合奖学金一等奖是什么条件？", history=history),
        HISTORICAL_SCHOLARSHIP_2025,
    ) is True


def test_multiturn_current_quota_beats_historical_wording() -> None:
    """历史里的“当时”不能覆盖本轮“现在还剩”。"""
    meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta))
    history = ["2026年青禾计划当时招几个学生？"]
    assert check(
        _request("现在还剩几个名额？", history=history), LAB_NOTICE
    ) is False
    # 反过来，本轮问历史人数时也不能被上一轮的“现在”拦住。
    assert check(
        _request(
            "2026年青禾计划当时招几个学生？",
            history=["现在还剩几个名额？"],
        ),
        LAB_NOTICE,
    ) is True


def test_s4_r3_recruitment_requires_matching_year() -> None:
    meta = _resource_meta(
        LAB_NOTICE,
        category="实验室与科研团队",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
        deadline=date(2026, 10, 31),
    )
    check = _check_for((LAB_NOTICE, meta))
    assert check(_request("2026年青禾计划怎么报名？"), LAB_NOTICE) is True
    assert check(_request("2025年青禾计划怎么报名？"), LAB_NOTICE) is False
    assert check(_request("2027年青禾计划招几人？"), LAB_NOTICE) is False


def test_s4_r4_and_r6_do_not_require_annual_match() -> None:
    intro_meta = _resource_meta(
        LAB_INTRO,
        category="研究方向与公开介绍",
        applicability={"适用年级": "全体本科生", "适用专业": "计算机科学与技术"},
    )
    contact_meta = _resource_meta(
        COLLEGE_CONTACT,
        record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式",
        applicability=None,
    )
    intro_check = _check_for((LAB_INTRO, intro_meta))
    contact_check = _check_for((COLLEGE_CONTACT, contact_meta))
    assert intro_check(
        _request("2025年EDA实验室研究什么？"), LAB_INTRO
    ) is True
    assert contact_check(
        _request("2025年学院办公室电话是多少？"), COLLEGE_CONTACT
    ) is True


def test_s4_wechat_name_and_id_must_match_family() -> None:
    article = _chunk(
        index=212,
        title="计算机与大数据学院公开联系方式",
        content="学院办公室电话：0591-2286XXXX。",
        source_url="https://mp.weixin.qq.com/s/family-check",
    )
    meta = _resource_meta(
        article,
        record_code="计算机学院-2026-学院公开信息",
        category="学院公开信息与联系方式",
        applicability=None,
    )
    check = _check_for((article, meta))

    # 合法学院名称搭配学校号 ID，不能靠昵称放行。
    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "福州大学计算机学院",
            "account_id": "ifzu1958",
            "basis": "文章标题自称学院官方",
        },
    }
    assert check(_request("学院办公室电话是多少？"), article) is False

    # 合法学校名称搭配学院 ID，同样拒绝。
    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "ifzu1958",
            "account_id": "gh_college",
            "basis": "名称与 ID 来自不同主体",
        },
    }
    assert check(_request("学院办公室电话是多少？"), article) is False

    # 学院名称搭配招生号 ID。
    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "福州大学计算机学院",
            "account_id": "fzuzsks",
            "basis": "文章标题自称学院官方",
        },
    }
    assert check(_request("学院办公室电话是多少？"), article) is False

    # 生产白名单未登记 `gh_college`，即使是合法学院名称也不通过。
    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "福州大学计算机学院",
            "account_id": "gh_college",
            "basis": "文章标题自称学院官方",
        },
    }
    assert check(_request("学院办公室电话是多少？"), article) is False

    # 学院名称搭配未登记的仿冒 `gh_` ID，也不能只靠昵称放行。
    meta.temporal_notes = {
        "human_approved": True,
        "wechat_verification": {
            "verified": True,
            "account_name": "福州大学计算机学院",
            "account_id": "gh_fake",
            "basis": "文章标题自称学院官方",
        },
    }
    assert check(_request("学院办公室电话是多少？"), article) is False


@pytest.mark.parametrize(
    "timeliness",
    [TimelinessVerificationStatus.HISTORICAL, TimelinessVerificationStatus.EXPIRED],
)
def test_s4_old_contact_rejected_for_current_question(timeliness) -> None:
    """上一轮“去年”不能让本轮“现在”的旧联系方式通过。"""
    old_contact = _chunk(
        index=221,
        title="计算机与大数据学院公开联系方式（2025）",
        content="学院办公室电话：0591-2286OLD，办公地点：旗山校区计算机学院楼。",
        timeliness=timeliness,
        source_url="https://ccds.fzu.edu.cn/",
    )
    meta = _resource_meta(
        old_contact,
        record_code="计算机学院-2025-学院公开信息",
        category="学院公开信息与联系方式",
        applicability=None,
        policy_status="已过期",
    )
    check = _check_for((old_contact, meta))
    assert check(
        _request(
            "现在学院办公室电话是多少？",
            history=["去年学院办公室电话是多少？"],
        ),
        old_contact,
    ) is False
    # 明确问对应年度时，历史联系方式仍可用于历史回答。
    assert check(_request("2025年学院办公室电话是多少？"), old_contact) is True


def test_s4_old_plan_rejected_for_current_question() -> None:
    """上一轮“旧版”不能让本轮“现在”的旧培养方案通过。"""
    old_plan = _chunk(
        index=222,
        title="计算机科学与技术专业培养方案（2025版）",
        content="2025版培养方案规定课程、实践与学位学分要求。",
        timeliness=TimelinessVerificationStatus.HISTORICAL,
        source_url="https://ccds.fzu.edu.cn/",
    )
    meta = _resource_meta(
        old_plan,
        record_code="计算机学院-2025-培养方案",
        category="培养方案与课程",
        applicability={"适用专业": "计算机科学与技术", "适用年级": "2025级"},
        policy_status="已过期",
    )
    check = _check_for((old_plan, meta))
    assert check(
        _request(
            "现在计算机专业培养方案有哪些课程？",
            history=["以前旧版培养方案有哪些课程？"],
        ),
        old_plan,
    ) is False
    assert check(
        _request("2025年计算机专业培养方案有哪些课程？"), old_plan
    ) is True


def test_s4_superseded_plan_rejected_for_current_question() -> None:
    """上一轮“旧版”不能让本轮“现在”的被替代资料通过。"""
    superseded_plan = _chunk(
        index=223,
        title="计算机科学与技术专业培养方案（2024版）",
        content="2024版培养方案已被新版替代。",
        timeliness=TimelinessVerificationStatus.SUPERSEDED,
        source_url="https://ccds.fzu.edu.cn/",
    )
    meta = _resource_meta(
        superseded_plan,
        record_code="计算机学院-2024-培养方案",
        category="培养方案与课程",
        applicability={"适用专业": "计算机科学与技术", "适用年级": "2024级"},
        policy_status="已被替代",
    )
    check = _check_for((superseded_plan, meta))
    assert check(
        _request(
            "现在计算机专业培养方案有哪些课程？",
            history=["2024年旧版培养方案有哪些课程？"],
        ),
        superseded_plan,
    ) is False
    # 明确问旧版时仍可回答历史信息。
    assert check(
        _request("2024年旧版培养方案有哪些课程？"), superseded_plan
    ) is True
