"""Conversation context and time scope used by AgentWorkflow."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

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
_MISSING_TOPIC = re.compile(r"^(?:请问|所以)?(?:怎么办|怎么(?:申请|办理|报名)|要什么条件|需要什么材料|截止时间|什么时候截止|多少钱|哪些条件)")
_NEW_TOPIC = re.compile(r"换[个一]?(?:话题|问题)|改问|另一个|另外想问|不问.+了")
_PERIOD = re.compile(
    r"(?<!\d)(20\d{2})(?:\s*[-—–－至/]\s*(20\d{2}))?\s*(学年|学期|年(?!级)|届|版)(?!度?级)"
)
_BARE_PERIOD = re.compile(r"^\s*(20\d{2})(?:\s*[-—–－至/]\s*(20\d{2}))?\s*呢?[。.!？?]?\s*$")
_RELATIVE_PERIOD = re.compile(r"去年|前年|明年|下一届|下届|下一轮|上一?年度|上学年|上学期|本学年|当前学年|本学期|这学期|今年|本年度|当年")
_HISTORY = re.compile(r"往年|历年|历史(?:政策|通知|资料|规定|版本)|旧版|原政策|以前|曾经|当时|过去的")
_CURRENT = re.compile(r"现在|目前|现行|当前|最新|仍有效|还有效")
_WINDOW = re.compile(
    r"还能|现在还|目前还|是否还|仍在招募|仍在报名|办理窗口|"
    r"(?:现在|目前|今年|当前).{0,12}(?:申请|报名|招募|招人|招收|提交|办理)|"
    r"(?:申请|报名|招募)(?:开始了|开放了吗|结束了吗|截止了吗)|(?:现在|还有|有没有).{0,12}(?:招募|报名|招生)?名额"
)
_DEADLINE = re.compile(r"截止|截至哪|最晚何时|最晚什么时候")
_NAMED_WORK = re.compile(r"《([^》]+)》")
_NAMED_LAB = re.compile(r"\b([A-Za-z][\w-]*?)\s*(?:实验室|课题组|那个)")
_SLOTS = (
    re.compile(rf"{_PERIOD.pattern}|{_BARE_PERIOD.pattern}|{_RELATIVE_PERIOD.pattern}|{_HISTORY.pattern}|{_CURRENT.pattern}"),
    re.compile(r"20\d{2}\s*级|大[一二三四五]|[一二三四五]年级"),
    re.compile(r"排名(?:第)?\s*\d+|第\s*\d+\s*名|前\s*\d+\s*%"),
    re.compile(r"本科生|研究生|学术型|专业型|直博|全日制|非全日制"),
    re.compile(r"国家级|省级|校级|院级|国际级"),
    re.compile(r"[一二三]等奖|特等奖|金奖|银奖|铜奖"),
    re.compile(r"个人(?:赛|奖|项目)?|集体(?:赛|奖|项目)?|团队(?:赛|奖|项目)?"),
)
_YEAR_KEYS = ("适用年度", "适用届别", "适用学年", "适用年份", "目标届别", "年度")
_ARCHIVED = {Timeliness.HISTORICAL, Timeliness.SUPERSEDED, Timeliness.EXPIRED}


def _topics(text: str) -> set[int]:
    return {index for index, cue in enumerate(_TOPICS) if cue.search(text)}


def contextual_request(request: AgentRequest) -> AgentRequest:
    """Keep one recent user topic and the latest values of recognized slots."""
    current_topics = _topics(request.query)
    history = []
    filled = {slot for slot in _SLOTS if slot.search(request.query)}
    follow_up = _FOLLOW_UP.search(request.query)
    # A self-contained new question starts afresh even within the same domain.
    named_works = set(_NAMED_WORK.findall(request.query))
    named_labs = {name.casefold() for name in _NAMED_LAB.findall(request.query)}
    if (_NEW_TOPIC.search(request.query)
            or (current_topics and not (named_works or follow_up))
            or (not current_topics and not (filled or follow_up or _MISSING_TOPIC.search(request.query)))):
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
    return request.model_copy(update={"history": list(reversed(history))})


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
            current, bool(_WINDOW.search(fact_question)), bool(_DEADLINE.search(fact_question)), fact_question,
        )

    def evidence_mode(self, metadata: DocumentMetadata) -> tuple[AnswerMode, str | None] | None:
        applicability = metadata.applicability_raw or {}
        if not any(value and str(value).strip() for value in applicability.values()):
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
            if self.current or self.needs_window or not (self.historical or self.periods):
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
