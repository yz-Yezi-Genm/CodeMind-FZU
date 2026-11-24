"""Conversation context and time scope used by AgentWorkflow."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit

from backend.contracts.models import AgentRequest, AnswerMode, DocumentMetadata, LLMRole
from backend.contracts.models import TimelinessVerificationStatus as Timeliness


# Topic cues only delimit history. The injected rules own scenario and applicability decisions.
_TOPICS = tuple(map(re.compile, (
    r"竞赛|创新创业|创新学分|综测|综评|综合素质|蓝桥杯",
    r"奖学金|评奖|爱国者之星|星火奖",
    r"推免|保研|免试攻读|推荐资格",
    r"学院资源|实验室|科研团队|课题组|学习资源|科研资源|培养方案|办事渠道|青禾计划|学院通知|办公室|联系方式|官网",
    r"转专业|辅修|选课|重修|学位|毕业|学生证|学籍|课程|英语",
)))
_FOLLOW_UP = re.compile(r"^(?:那|那么|这个|这项|它|该|上述|上面|同一|还有|还需要|再问|改成|改问|更正|补充)|呢[？?。]*$")
_MISSING_TOPIC = re.compile(
    r"^(?:(?:请问|所以)[，,]?\s*)?(?:怎么办|怎么(?:申请|办理|报名)|要什么条件|需要什么材料|"
    r"截止时间|什么时候截止|多少钱|哪些条件|还(?:能|可以)(?:申请|报名|办理|提交))"
)
_NEW_TOPIC = re.compile(r"换[个一]?(?:话题|问题)|改问|另一个|另外想问|不问.+了")
_PERIOD = re.compile(
    r"(?<!\d)(20\d{2})(?:\s*[-—–－至/]\s*(20\d{2}))?\s*(学年|学期|年(?!级)|届|版)(?!度?级)"
)
_BARE_PERIOD = re.compile(r"^\s*(20\d{2})(?:\s*[-—–－至/]\s*(20\d{2}))?\s*呢?[。.!？?]?\s*$")
_RELATIVE_PERIOD = re.compile(r"去年|前年|明年|下一届|下届|下一轮|上一?年度|上学年|上学期|本学年|当前学年|本学期|这学期|今年|本年度|当年")
_HISTORY = re.compile(r"往年|历年|历史(?:政策|通知|资料|规定|版本)|旧版|原政策|以前|曾经|当时|过去的")
_CURRENT = re.compile(r"现在|目前|现行|当前|最新|仍有效|还有效")
_WINDOW = re.compile(
    r"还能|还可以(?:申请|报名|办理|提交)|现在还|目前还|是否还|仍在招募|仍在报名|办理窗口|"
    r"(?:现在|目前|今年|当前).{0,12}(?:申请|报名|招募|招人|招收|提交|办理)|"
    r"(?:申请|报名|招募)(?:开始了|开放了吗|结束了吗|截止了吗)|(?:现在|还有|有没有).{0,12}(?:招募|报名|招生)?名额"
)
_DEADLINE = re.compile(r"截止|截至哪|最晚何时|最晚什么时候")
_NAMED_WORK = re.compile(r"《([^》]+)》")
_NAMED_LAB = re.compile(r"\b([A-Za-z][\w-]*?)\s*(?:实验室|课题组|那个)")
_SLOTS = (
    re.compile(rf"{_PERIOD.pattern}|{_BARE_PERIOD.pattern}|{_RELATIVE_PERIOD.pattern}"),
    re.compile(rf"{_HISTORY.pattern}|{_CURRENT.pattern}"),
    re.compile(r"20\d{2}\s*级|大[一二三四五]|[一二三四五]年级"),
    re.compile(r"排名(?:第)?\s*\d+|第\s*\d+\s*名|前\s*\d+\s*%"),
    re.compile(r"本科生|研究生|学术型|专业型|直博|全日制|非全日制"),
    re.compile(r"国家级|省级|校级|院级|国际级"),
    re.compile(r"[一二三]等奖|特等奖|金奖|银奖|铜奖"),
    re.compile(r"个人(?:赛|奖|项目)?|集体(?:赛|奖|项目)?|团队(?:赛|奖|项目)?"),
)
_YEAR_KEYS = ("适用年度", "适用届别", "适用学年", "适用年份", "目标届别", "年度")
_ARCHIVED = {Timeliness.HISTORICAL, Timeliness.SUPERSEDED, Timeliness.EXPIRED}
_COLLEGE_RESOURCES = "COLLEGE_RESOURCES"
_R3_CATEGORY = "实验室与科研团队"
_R4_CATEGORY = "研究方向与公开介绍"
_R6_CATEGORY = "学院公开信息与联系方式"
_PUBLIC_INTRO = re.compile(r"研究(?:方向|什么|内容|哪些)|做什么|成果|简介")
_PUBLIC_CONTACT = re.compile(r"(?:学院|办公室|办公).*(?:电话|办公地点|地址|邮箱|联系方式)")
_PERSONAL_RESOURCE = re.compile(r"能不能|能否|可否|是否适用|是否符合|资格|我.{0,16}(?:能|可以|适用|符合)|报名|招募|名额|办理条件")
_LAB = r"[\w\-· ]{1,40}?(?:实验室|课题组|科研团队)"
_LAB_SUBJECT = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_-]*\s*(?:实验室|课题组|科研团队)")
_LAB_TOPIC = re.compile(r"实验室|课题组|科研团队|青禾计划")
_LIVE_LAB_QUOTA = re.compile(
    r"实时.{0,16}(?:名额|人数)|(?:剩余|还剩|还有|剩下).{0,10}(?:名额|几个|多少|几人)"
    r"|名额.{0,10}(?:剩余|还剩|剩下)|(?:现在|目前|当前).{0,16}(?:还招|还接收).{0,6}(?:几个|几人|多少)"
    r"|还招(?:几个|几人|多少)"
)
_CURRENT_LAB_QUOTA = re.compile(r"(?:目前|当前|现在).{0,16}名额")
_QUESTION_SEPARATOR = re.compile(r"[，,。！？?!；;\n]+|以及|并且|另外|同时问|和(?=(?:现在|目前|还有|还剩|剩余))")
_QUOTA_QUALIFIER = re.compile(r"^(?:(?:主要|具体)想知道|想知道|想确认|我是想问)")
_STILL = r"(?:(?:现在|目前|当前)\s*)?"
_RECRUITING = r"(?:还(?:在)?招(?:人|募|收)?|还(?:能|可以)报名)"
_QUOTA = r"(?:还剩(?:几个|多少)(?:名额)?|还招(?:几个|几人|多少人?))"
_RECRUITMENT_SUFFIX = rf"{_STILL}(?:{_RECRUITING}|{_QUOTA})(?:吗|么)?[？?。]*"
_RECRUITMENT_FOLLOW_UP = re.compile(rf"(?:请问[，,]?\s*|那\s*)?(?P<question>{_RECRUITMENT_SUFFIX})")
_QINGHE = "青禾计划"
_QINGHE_LABS = "青禾计划实验室"
_QINGHE_STATUS = re.compile(rf"(?:请问[，,]?\s*)?{_QINGHE}\s*(?P<question>{_RECRUITMENT_SUFFIX})")
_LAB_STATUS = re.compile(
    rf"(?:请问[，,]?\s*)?(?:(?P<lab>{_LAB})\s*{_STILL}{_RECRUITING}"
    rf"|{_STILL}还(?:能|可以)报名\s*(?P<after>{_LAB}))(?:吗|么)?[？?。]*"
)


def _is_college_resource(metadata: DocumentMetadata, category: str) -> bool:
    return metadata.category_name.strip() == category and _COLLEGE_RESOURCES in metadata.business_direction_codes


def _is_college_contact_page(url: str) -> bool:
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.hostname == "ccds.fzu.edu.cn"
            and parts.username is None and parts.password is None
            and parts.port in (None, 443) and not parts.netloc.endswith(":"))


def _topics(text: str) -> set[int]:
    return {index for index, cue in enumerate(_TOPICS) if cue.search(text)}


def is_live_quota_question(text: str) -> bool:
    return bool(_LIVE_LAB_QUOTA.search(text) or (_CURRENT_LAB_QUOTA.search(text) and "计划" not in text))


def separate_live_lab_quota(request: AgentRequest) -> str | None:
    """Return the remaining questions, or None for a request without a lab quota issue."""
    query = request.query
    lab_context = [query, *(turn.content for turn in reversed(request.history))]
    if not (_LAB_TOPIC.search(query) or (
        not _topics(query) and any(_LAB_TOPIC.search(text) for text in lab_context[1:])
    )):
        return None

    clauses = [clause.strip() for clause in _QUESTION_SEPARATOR.split(query) if clause.strip()]
    remaining = []
    for clause in clauses:
        if not is_live_quota_question(clause):
            remaining.append(clause)
        elif remaining and _QUOTA_QUALIFIER.match(clause) and _LAB_STATUS.fullmatch(remaining[-1]):
            # The user narrowed a general recruitment question to the remaining seats.
            remaining.pop()
    if len(remaining) == len(clauses):
        # If the quota intent crosses a clause boundary, retain the refusal.
        return "" if is_live_quota_question(query) else None

    # A research-direction clause may borrow its subject from the omitted clause.
    lab = next((match.group() for text in lab_context if (match := _LAB_SUBJECT.search(text))), "")
    return "。".join(
        lab + clause if _PUBLIC_INTRO.search(clause) and not _LAB_TOPIC.search(clause) else clause
        for clause in remaining
    )


def _year_reply(text: str) -> str | None:
    reply = text.strip().rstrip("呢。.!？?")
    bare = _BARE_PERIOD.fullmatch(reply)
    if bare:
        return reply + ("学年" if bare[2] else "年")
    return reply if _PERIOD.fullmatch(reply) else None


def contextual_request(request: AgentRequest) -> AgentRequest:
    """Keep one recent user topic and the latest values of recognized slots."""
    query = request.query.strip()
    qinghe = _QINGHE_STATUS.fullmatch(query)
    if qinghe:
        # Give the S4 rules an explicit lab subject for the program shorthand.
        return request.model_copy(update={"query": _QINGHE_LABS + qinghe["question"], "history": []})
    current_topics = _topics(query)
    history = []
    filled = {slot for slot in _SLOTS if slot.search(query)}
    follow_up = _FOLLOW_UP.search(query)
    recruitment_follow_up = _RECRUITMENT_FOLLOW_UP.fullmatch(query)
    # A self-contained new question starts afresh even within the same domain.
    named_works = set(_NAMED_WORK.findall(query))
    named_labs = {name.casefold() for name in _NAMED_LAB.findall(query)}
    if (_NEW_TOPIC.search(query)
            or (current_topics and not (named_works or follow_up))
            or (not current_topics and not (filled or follow_up or recruitment_follow_up or _MISSING_TOPIC.search(query)))):
        return request.model_copy(update={"history": history})

    for turn in reversed(request.history):
        if turn.role != LLMRole.USER:
            continue
        topics = _topics(turn.content)
        if topics and current_topics and topics != current_topics:
            break
        if named_works and topics and not named_works.intersection(_NAMED_WORK.findall(turn.content)):
            break
        prior_labs = {name.casefold() for name in _NAMED_LAB.findall(turn.content)}
        if named_labs and prior_labs and named_labs.isdisjoint(prior_labs):
            break
        if _NEW_TOPIC.search(turn.content) and not topics:
            break
        # Carry forward only non-overridden slots. Keep a topic-bearing question
        # intact when possible so its specific resource or policy name survives.
        content = turn.content
        for slot in _SLOTS:
            if slot in filled:
                content = slot.sub("", content)
            elif slot.search(content):
                filled.add(slot)
        if topics or any(slot.search(content) for slot in _SLOTS) or _FOLLOW_UP.search(content):
            if content.strip():
                history.append(turn.model_copy(update={"content": content.strip()}))
        if topics:
            break
    if history and not any(_topics(turn.content) for turn in history):
        history.clear()
    resolved_query = request.query
    if history:
        topic = history[-1].content
        year = _year_reply(query)
        if year and _HISTORY.search(topic):
            # The rules prioritize the current turn for year and time intent.
            # Pass both the inherited historical subject and the new year together.
            subject = history.pop().content.strip().rstrip("？?。！!")
            resolved_query = f"{year}的{subject}？"
        elif recruitment_follow_up and _topics(topic) == {3}:
            labs = set(_LAB_SUBJECT.findall(topic))
            if len(labs) == 1:
                resolved_query = next(iter(labs)) + recruitment_follow_up["question"]
            elif not labs and _QINGHE in topic:
                resolved_query = _QINGHE_LABS + recruitment_follow_up["question"]
    return request.model_copy(update={"query": resolved_query, "history": list(reversed(history))})


@dataclass(frozen=True)
class PolicyPeriod:
    start: int
    end: int | None = None

    @property
    def label(self) -> str:
        return f"{self.start}—{self.end}学年" if self.end else f"{self.start}年"

    def ended(self, today: date) -> bool:
        # Use the FZU rollover already used by the Alpha workflow.
        return today > (date(self.end, 8, 30) if self.end else date(self.start, 12, 31))

    def matches(self, other: PolicyPeriod) -> bool:
        return self == other or (self.start == other.start and not (self.end and other.end))


def _explicit_periods(text: str) -> set[PolicyPeriod]:
    bare = _BARE_PERIOD.fullmatch(text)
    if bare:
        start, end = bare.groups()
        return {PolicyPeriod(int(start), int(end) if end else None)}
    return {
        PolicyPeriod(int(start), int(end) if end else None)
        for start, end, _ in _PERIOD.findall(text)
    }


@dataclass(frozen=True)
class PolicyScope:
    today: date
    periods: frozenset[PolicyPeriod]
    historical: bool
    current: bool
    needs_window: bool
    asks_deadline: bool
    fact_question: str

    @property
    def future(self) -> bool:
        return any(period.start > self.today.year for period in self.periods)

    @classmethod
    def from_request(cls, request: AgentRequest, today: date) -> PolicyScope:
        text = request.query
        fact_question = text
        reply = text.strip().rstrip("呢。.!？?")
        if request.history and (_BARE_PERIOD.fullmatch(reply) or _PERIOD.fullmatch(reply)
                                or _RELATIVE_PERIOD.fullmatch(reply)):
            fact_question = "\n".join(turn.content for turn in request.history)
        if not (_explicit_periods(text) or _RELATIVE_PERIOD.search(text)
                or _HISTORY.search(text) or _CURRENT.search(text)):
            text = "\n".join(turn.content for turn in request.history) + "\n" + text
        periods = _explicit_periods(text)
        relative = _RELATIVE_PERIOD.search(text)
        if not periods and relative:
            academic_start = today.year - (today < date(today.year, 8, 31))
            term = relative.group()
            offset = {"去年": -1, "上年度": -1, "上一年度": -1, "前年": -2, "今年": 0, "本年度": 0,
                      "明年": 1, "下一届": 1, "下届": 1, "下一轮": 1}
            if term in offset:
                periods.add(PolicyPeriod(today.year + offset[term]))
            elif term in {"上学年", "本学年", "当前学年"}:
                start = academic_start - (term == "上学年")
                periods.add(PolicyPeriod(start, start + 1))
        current = bool(_CURRENT.search(text) or re.search(r"今年|本年度|本学年|本学期|这学期", text))
        return cls(
            today, frozenset(periods),
            bool(_HISTORY.search(text) or re.search(r"当年|上学期", text) or any(p.ended(today) for p in periods)),
            current, bool(_WINDOW.search(fact_question) or _LAB_STATUS.fullmatch(fact_question.strip())),
            bool(_DEADLINE.search(fact_question)), fact_question,
        )

    def evidence_mode(self, metadata: DocumentMetadata) -> tuple[AnswerMode, str | None] | None:
        return self._evidence_mode(metadata, closing_recruitment=False)

    def closed_recruitment_period(self, metadata: DocumentMetadata, content: str) -> str | None:
        """Allow a dated closure statement for a named lab's status inquiry."""
        match = _LAB_STATUS.fullmatch(self.fact_question.strip())
        if (not match or not _is_college_resource(metadata, _R3_CATEGORY)
                or metadata.timeliness_verification_status not in {Timeliness.HISTORICAL, Timeliness.EXPIRED}
                or not metadata.deadline_on or metadata.deadline_on >= self.today):
            return None
        lab = re.sub(r"\s+", "", match["lab"] or match["after"]).casefold()
        normalized_content = re.sub(r"\s+", "", content).casefold()
        if lab == _QINGHE_LABS:
            if _QINGHE not in metadata.title or _QINGHE not in normalized_content:
                return None
        elif not re.search(rf"(?<![a-z0-9_]){re.escape(lab)}", normalized_content):
            return None
        result = self._evidence_mode(metadata, closing_recruitment=True)
        return result[1] if result and result[0] == AnswerMode.HISTORICAL else None

    def _allows_public_resource_without_applicability(self, metadata: DocumentMetadata) -> bool:
        if self.needs_window:
            return False
        if _is_college_resource(metadata, _R4_CATEGORY):
            return bool(_PUBLIC_INTRO.search(self.fact_question))
        return (_is_college_resource(metadata, _R6_CATEGORY)
                and bool(_PUBLIC_CONTACT.search(self.fact_question))
                and _is_college_contact_page(metadata.source_url))

    def _evidence_mode(
        self, metadata: DocumentMetadata, *, closing_recruitment: bool,
    ) -> tuple[AnswerMode, str | None] | None:
        applicability = metadata.applicability_raw or {}
        if (_PERSONAL_RESOURCE.search(self.fact_question)
                and (_is_college_resource(metadata, _R4_CATEGORY) or _is_college_resource(metadata, _R6_CATEGORY))):
            return None
        if not any(value and str(value).strip() for value in applicability.values()):
            if metadata.applicability_raw is not None or not self._allows_public_resource_without_applicability(metadata):
                return None
        if any("歧义" in key and str(value).strip().lower() not in {"", "无", "否", "none", "-", "false"}
               for key, value in applicability.items()):
            return None

        declared = set()
        for facts in (applicability, metadata.temporal_notes or {}):
            for key in _YEAR_KEYS:
                value = str(facts.get(key) or "").strip()
                declared.update(_explicit_periods(value + "年" if value.isdecimal() else value))
        document_periods = declared or _explicit_periods(metadata.title)
        if len(document_periods) > 1:
            return None
        period = next(iter(document_periods), None)
        if self.future and period is None:
            return None
        if self.periods and period and not all(p.matches(period) for p in self.periods):
            return None

        status = metadata.timeliness_verification_status
        deadline = metadata.deadline_on
        ended = bool(deadline and deadline < self.today)
        notice = bool(deadline or re.search(r"年度规则|年度通知|报名通知|招募通知", metadata.document_type)
                      or (period and re.search(r"通知|公告|报名|招募", metadata.title)))
        if status in _ARCHIVED or ended:
            # An explicit historical question or matching year is required, even
            # when an elapsed deadline has yet to be reflected in the status.
            if not closing_recruitment and (self.current or self.needs_window or not (self.historical or self.periods)):
                return None
            if not period or (self.asks_deadline and not deadline):
                return None
            return AnswerMode.HISTORICAL, period.label
        if status != Timeliness.CURRENT or self.historical:
            return None
        if (self.needs_window or self.asks_deadline or notice) and deadline is None:
            return None
        if notice:
            return AnswerMode.PROCEDURE_REFERENCE, period.label if period else None
        return AnswerMode.CURRENT_POLICY, None
