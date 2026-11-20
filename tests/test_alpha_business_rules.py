"""Alpha 业务规则单元测试：追问、证据适用性与工作流联调。"""

from __future__ import annotations

import json
import uuid
from datetime import date

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
    _level,
    _rank,
    alpha_clarification_rule,
    build_alpha_evidence_check,
)

TODAY = date(2026, 11, 19)


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


def _chunk(
    *,
    title: str,
    content: str,
    index: int = 1,
    timeliness: TimelinessVerificationStatus = TimelinessVerificationStatus.CURRENT,
    source: SourceVerificationStatus = SourceVerificationStatus.VERIFIED,
    published_on: date | None = date(2026, 5, 18),
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.UUID(int=100 + index),
        document_id=uuid.UUID(int=200 + index),
        version_id=uuid.UUID(int=300 + index),
        file_id=uuid.UUID(int=400 + index),
        content=content,
        title=title,
        publisher="福州大学",
        source_url="https://example.invalid/policy",
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
) -> DocumentMetadata:
    return DocumentMetadata(
        title=title or chunk.title,
        document_type="规范性文件",
        category_name="综评与奖学金",
        record_code=record_code,
        version_no="import-1",
        source_url=chunk.source_url,
        publisher=chunk.publisher,
        published_on=chunk.published_on,
        deadline_on=deadline,
        applicability_raw=applicability,
        policy_status="当前有效",
        source_verification_status=SourceVerificationStatus.VERIFIED,
        timeliness_verification_status=TimelinessVerificationStatus.CURRENT,
        extraction_status=ExtractionStatus.EXTRACTED,
        v1_inclusion_status=InclusionStatus.INCLUDED,
        retrieval_status=RetrievalStatus.ENABLED,
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
        ("全国大学生数学建模竞赛国家二等奖，团队作品，我为第一完成人，创新学分原始分是多少？", None),
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
    query = "我们团队参加挑战杯拿了省部级一等奖，能认定多少创新学分？"
    assert alpha_clarification_rule(_request(query)) == QUESTION_TOP_EIGHT


def test_evaluation_team_needs_semester_and_unit() -> None:
    query = "综测里我们团队参加校级竞赛拿了最高等级奖，我是第一完成人，能加多少分？"
    assert alpha_clarification_rule(_request(query)) == QUESTION_SEMESTER

    query_with_semester = (
        "综测里我们团队参加校级竞赛拿了最高等级奖，我是第一完成人，上一学期拿的。"
    )
    assert alpha_clarification_rule(_request(query_with_semester)) == QUESTION_FIRST_UNIT


def test_competition_needs_level_and_grade() -> None:
    assert alpha_clarification_rule(_request("数学建模竞赛拿奖了，创新学分能认定多少？")) == QUESTION_LEVEL
    assert (
        alpha_clarification_rule(_request("数学建模竞赛国家级奖，创新学分能认定多少？"))
        == QUESTION_AWARD_GRADE
    )
    assert (
        alpha_clarification_rule(_request("数学建模竞赛国家级二等奖，创新学分能认定多少？"))
        == QUESTION_FORMAT
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
        "国家级二等奖，团队作品，第一完成人，创新学分能认定多少？",
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
        ("全国大学生数学建模竞赛国家二等奖，团队作品，我为第一完成人，创新学分原始分是多少？", CREDIT_BYLAW),
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
        ("数学建模竞赛国家级二等奖，团队作品，我是第一完成人，创新学分原始分是多少？", EVALUATION_BYLAW),
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
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks
        self.calls = 0

    async def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        self.calls += 1
        return list(self._chunks)


class _LLM:
    def __init__(self, content: str = '{"evidence":[]}') -> None:
        self._content = content
        self.calls = 0

    async def generate(self, request) -> LLMResult:
        self.calls += 1
        return LLMResult(content=self._content, model="stub")


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
    retriever = _Retriever([SCHOOL_SCHOLARSHIP])
    llm = _LLM(json.dumps(
        {"evidence": [{"chunk_id": str(SCHOOL_SCHOLARSHIP.chunk_id), "quote": SCHOOL_SCHOLARSHIP.content}]},
        ensure_ascii=False,
    ))
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
    credit_query = "全国大学生数学建模竞赛国家二等奖，团队作品，我为第一完成人，创新学分原始分是多少？"
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
    request = _request("数学建模竞赛省赛二等奖，团队作品，我是第九完成人，创新学分原始分是多少？")
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
