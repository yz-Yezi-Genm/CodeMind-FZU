"""Conversation context and time scope used by AgentWorkflow."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit

from backend.contracts.models import AgentRequest, AnswerMode, DocumentMetadata, LLMRole
from backend.contracts.models import TimelinessVerificationStatus as Timeliness
from backend.services.resource_team_names import r3_team_names, without_r3_team_names


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
_LAB_NAME = (
    r"(?!我|你|他|各|青禾计划的实验室)"
    r"(?![\w ]{0,59}?(?:哪些|哪个|这个|那个|所有|多个|某个|专业|本科生|外校|外院)"
    r"[\w +·—\-”」]{0,59}?(?:实验室|课题组|团队))"
    r"[“「]?[A-Za-z\u3400-\u9fff][\w +·—\-”」]{0,59}?"
    r"(?:实验室(?:[A-Za-z][\w-]*小组)?|课题组|团队)"
)
# Strip conversational framing, dates and verbs before capturing the subject.
_LAB_PREFIX = (
    rf"(?:{_PERIOD.pattern}|"
    r"请问(?:一下)?|那么|那|想(?:问|了解)(?:一下)?|我想|"
    r"换成|改成|改问|另一个|关于|青禾计划的|今年|去年|现在|目前|当前|"
    r"怎么(?:报名|申请)|如何(?:报名|申请)|(?:还(?:能|可以))?报名|加入|进入|了解|介绍)\s*"
)
_LAB_SUBJECT = re.compile(
    rf"(?<!\w)(?:{_LAB_PREFIX})*(?!{_LAB_PREFIX})(?P<name>{_LAB_NAME})"
)
_LAB_REFERENCE = re.compile(r"(?<![\w])([A-Za-z][A-Za-z0-9_-]*)\s*那个")
_LAB_TOPIC = re.compile(r"实验室|课题组|科研团队|青禾计划")
_LAB_KIND = re.compile(r"实验室(?=(?:[A-Za-z][\w-]*小组)?$)|课题组$|科研团队$")
_ASCII_LAB = re.compile(r"[a-z][a-z0-9_-]*(?:实验室|课题组|科研团队)")
_OTHER_QUOTA_TOPIC = re.compile(r"助学金|奖助|单项奖|励志奖|招生办|招生简章")
_LIVE_LAB_QUOTA = re.compile(
    r"实时.{0,16}(?:名额|人数)|(?:剩余|还剩|还有|剩下).{0,10}(?:名额|几个|多少|几人)"
    r"|名额.{0,10}(?:剩余|还剩|剩下)|(?:现在|目前|当前).{0,16}(?:还招|还接收).{0,6}(?:几个|几人|多少)"
    r"|还招(?:几个|几人|多少)"
)
_CURRENT_LAB_QUOTA = re.compile(r"(?:目前|当前|现在).{0,16}名额")
_QUESTION_SEPARATOR = re.compile(
    r"[，,。！？?!；;\n]+|以及|并且|另外|同时(?:问|(?=\s*(?:现在|目前|当前|还有|还剩|剩余|还招)))"
    r"|和(?=(?:现在|目前|还有|还剩|剩余))"
)
_QUOTA_QUALIFIER = re.compile(r"^(?:(?:主要|具体)想知道|想知道|想确认|我是想问)")
_STILL = r"(?:(?:现在|目前|当前)\s*)?"
_RECRUITING = r"(?:还(?:在)?招(?:人|募|收)?|还(?:能|可以)报名)"
_QUOTA = r"(?:还剩(?:几个|多少)(?:名额)?|还招(?:几个|几人|多少人?))"
_RECRUITMENT_SUFFIX = rf"{_STILL}(?:{_RECRUITING}|{_QUOTA})(?:吗|么)?[？?。]*"
_RECRUITMENT_FOLLOW_UP = re.compile(rf"(?:请问[，,]?\s*|那\s*)?(?P<question>{_RECRUITMENT_SUFFIX})")
_TEAM_PURPOSE_REPLY = re.compile(r"(?:报名|怎么报名|怎么进|加入|研究方向|研究什么)[？?。]*")
_TEAM_REGISTRATION = re.compile(r"报名|怎么进|如何进|加入|招新")
_COMPETITION_TEAM_FOLLOW_UP = re.compile(r"^(?:我们)?(?:的)?(?:竞赛|比赛)团队还(?:能|可以)报名吗[？?。]*$")
_SOURCE_DEADLINE = re.compile(
    r"截止(?:日期|时间)?[为是于：: ]*"
    r"(?:(?P<year>20\d{2})[-/.年]\s*)?(?P<month>\d{1,2})[-/.月]\s*(?P<day>\d{1,2})日?"
    r"|(?:(?P<before_year>20\d{2})年)?(?P<before_month>\d{1,2})月(?P<before_day>\d{1,2})日"
    r"前(?:报名|提交|发送)"
)
_QINGHE = "青禾计划"
_QINGHE_LABS = "青禾计划实验室"
_QINGHE_STATUS = re.compile(rf"(?:请问[，,]?\s*)?{_QINGHE}\s*(?P<question>{_RECRUITMENT_SUFFIX})")
_LAB_STATUS = re.compile(
    rf"(?:请问[，,]?\s*)?(?:(?:{_LAB_PREFIX})*(?!{_LAB_PREFIX})(?P<lab>{_LAB_NAME})\s*{_STILL}{_RECRUITING}"
    rf"|{_STILL}还(?:能|可以)报名\s*(?P<after>{_LAB_NAME}))(?:吗|么)?[？?。]*"
)


def _is_college_resource(metadata: DocumentMetadata, category: str) -> bool:
    return metadata.category_name.strip() == category and _COLLEGE_RESOURCES in metadata.business_direction_codes


def _is_college_contact_page(url: str) -> bool:
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.hostname == "ccds.fzu.edu.cn"
            and parts.username is None and parts.password is None
            and parts.port in (None, 443) and not parts.netloc.endswith(":"))


def _topics(text: str) -> set[int]:
    topics = {index for index, cue in enumerate(_TOPICS) if cue.search(text)}
    if r3_team_names(text):
        topics.add(3)
    return topics


def _lab_key(name: str) -> str:
    return re.sub(r'[\s“”「」]+', "", name).casefold()


def _named_labs(text: str) -> set[str]:
    return {_lab_key(match["name"]) for match in _LAB_SUBJECT.finditer(text)}


def _slot_matches(text: str) -> dict[re.Pattern[str], list[re.Match[str]]]:
    names = [match.span("name") for match in _LAB_SUBJECT.finditer(text)] if _topics(text) == {3} else []
    return {
        slot: [match for match in slot.finditer(text)
               if not any(start < match.end() and match.start() < end for start, end in names)]
        for slot in _SLOTS
    }


def recruitment_rule_request(
    request: AgentRequest, metadata: DocumentMetadata, content: str,
) -> AgentRequest:
    """Keep words inside a verified R3 subject out of student applicability rules."""
    if not _is_college_resource(metadata, _R3_CATEGORY) or _topics(request.query) != {3}:
        return request
    match = _LAB_SUBJECT.match(request.query.lstrip())
    if not match or not (label := _LAB_KIND.search(match["name"])):
        return request
    lab = _lab_key(match["name"])
    if lab == _QINGHE_LABS or lab not in _named_labs(content):
        return request

    # The Retriever and PolicyScope still see the exact lab name. The business
    # rules receive its resource type and the user's literal eligibility terms.
    def replace_name(raw: str) -> str:
        return _LAB_SUBJECT.sub(
            lambda item: item[0].replace(item["name"], label[0], 1)
            if _lab_key(item["name"]) == lab else item[0],
            raw,
        )

    return request.model_copy(update={
        "query": replace_name(request.query),
        "history": [turn.model_copy(update={"content": replace_name(turn.content)}) for turn in request.history],
    })


def is_live_quota_question(text: str) -> bool:
    return bool(_LIVE_LAB_QUOTA.search(text) or (_CURRENT_LAB_QUOTA.search(text) and "计划" not in text))


def _lab_quota_topic(text: str) -> bool | None:
    """Identify an explicit lab topic, a different topic, or an implicit subject."""
    other_text = _LAB_TOPIC.sub("", without_r3_team_names(text))
    if _topics(other_text) or _OTHER_QUOTA_TOPIC.search(other_text):
        return False
    return True if _LAB_TOPIC.search(text) or r3_team_names(text) else None


def separate_live_lab_quota(request: AgentRequest) -> str | None:
    """Return the remaining questions, or None for a request without a lab quota issue."""
    query = request.query
    history = [turn.content for turn in reversed(request.history) if turn.role == LLMRole.USER]
    lab_topic = next((topic for text in history if (topic := _lab_quota_topic(text)) is not None), False)
    clauses = [clause.strip() for clause in _QUESTION_SEPARATOR.split(query) if clause.strip()]
    remaining = []
    removed = False
    only_lab_context = True
    for clause in clauses:
        topic = _lab_quota_topic(clause)
        if topic is not None:
            lab_topic = topic
            only_lab_context = only_lab_context and topic
        if not (lab_topic and is_live_quota_question(clause)):
            remaining.append(clause)
            continue
        removed = True
        if remaining and _QUOTA_QUALIFIER.match(clause) and _LAB_STATUS.fullmatch(remaining[-1]):
            # The user narrowed a general recruitment question to the remaining seats.
            remaining.pop()
    if not removed:
        # A single lab topic can also split one quota question across punctuation.
        if (only_lab_context and lab_topic and is_live_quota_question(query)
                and not any(is_live_quota_question(clause) for clause in clauses)):
            return ""
        return None

    # A research-direction clause may borrow its subject from the omitted clause.
    lab = next((match["name"] for text in [query, *history] if (match := _LAB_SUBJECT.search(text))), "")
    return "。".join(
        lab + clause if _PUBLIC_INTRO.search(clause) and _lab_quota_topic(clause) is None else clause
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
    filled = {slot for slot, matches in _slot_matches(query).items() if matches}
    follow_up = _FOLLOW_UP.search(query) or _COMPETITION_TEAM_FOLLOW_UP.fullmatch(query)
    recruitment_follow_up = _RECRUITMENT_FOLLOW_UP.fullmatch(query)
    team_purpose_reply = _TEAM_PURPOSE_REPLY.fullmatch(query)
    # A self-contained new question starts afresh even within the same domain.
    named_works = set(_NAMED_WORK.findall(query))
    named_labs = _named_labs(query)
    references = tuple(match[1].casefold() for match in _LAB_REFERENCE.finditer(query))
    if (_NEW_TOPIC.search(query)
            or (current_topics and not (named_works or follow_up))
            or (not current_topics and not (filled or follow_up or recruitment_follow_up
                                            or team_purpose_reply or _MISSING_TOPIC.search(query)))):
        return request.model_copy(update={"history": history})

    for turn in reversed(request.history):
        if turn.role != LLMRole.USER:
            continue
        topics = _topics(turn.content)
        if topics and current_topics and topics != current_topics:
            break
        if named_works and topics and not named_works.intersection(_NAMED_WORK.findall(turn.content)):
            break
        if current_topics <= {3} and topics <= {3}:
            prior_labs = _named_labs(turn.content)
            if prior_labs and (named_labs and named_labs.isdisjoint(prior_labs)
                               or references and not any(name.startswith(references) for name in prior_labs)):
                history.clear()
                break
        if _NEW_TOPIC.search(turn.content) and not topics:
            break
        # Carry forward only non-overridden slots. Keep a topic-bearing question
        # intact when possible so its specific resource or policy name survives.
        removals = []
        for slot, matches in _slot_matches(turn.content).items():
            if slot in filled:
                removals.extend(match.span() for match in matches)
            elif matches:
                filled.add(slot)
        content = turn.content
        for start, end in sorted(set(removals), reverse=True):
            content = content[:start] + content[end:]
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
        elif (recruitment_follow_up or team_purpose_reply) and _topics(topic) == {3}:
            labs = {_lab_key(match["name"]): match["name"] for match in _LAB_SUBJECT.finditer(topic)}
            if len(labs) == 1 and recruitment_follow_up:
                resolved_query = next(iter(labs.values())) + recruitment_follow_up["question"]
            elif len(labs) == 1 and team_purpose_reply and r3_team_names(next(iter(labs.values()))):
                resolved_query = next(iter(labs.values())) + query
            elif recruitment_follow_up and not labs and _QINGHE in topic:
                resolved_query = _QINGHE_LABS + recruitment_follow_up["question"]
        if team_purpose_reply and resolved_query == request.query and not _MISSING_TOPIC.search(query):
            history.clear()
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

    def expired_team_registration_mode(self, metadata: DocumentMetadata) -> tuple[AnswerMode, str | None] | None:
        """Permit a historical process answer for an explicitly named team."""
        if (len(r3_team_names(self.fact_question)) != 1 or _topics(self.fact_question) != {3}
                or not _TEAM_REGISTRATION.search(self.fact_question)
                or self.needs_window or not _is_college_resource(metadata, _R3_CATEGORY)
                or not self._recruitment_closed(metadata)):
            return None
        return self._evidence_mode(metadata, closing_recruitment=True)

    def _recruitment_closed(self, metadata: DocumentMetadata) -> bool:
        deadline = metadata.deadline_on
        if deadline is not None and deadline >= self.today:
            return False
        return (metadata.timeliness_verification_status == Timeliness.EXPIRED
                or (metadata.timeliness_verification_status == Timeliness.HISTORICAL and deadline is not None))

    def closed_recruitment_period(self, metadata: DocumentMetadata, content: str) -> str | None:
        """Allow a closure statement for a named lab or verified team's status inquiry."""
        match = _LAB_STATUS.fullmatch(self.fact_question.strip())
        if (not match or not _is_college_resource(metadata, _R3_CATEGORY)
                or not self._recruitment_closed(metadata)):
            return None
        name = match["lab"] or match["after"]
        teams = r3_team_names(name)
        if teams:
            if not teams.intersection(r3_team_names(content)):
                return None
        elif metadata.deadline_on is None or (name.endswith("团队") and not name.endswith("科研团队")):
            return None
        lab = _lab_key(name)
        normalized_content = re.sub(r"\s+", "", content).casefold()
        if lab == _QINGHE_LABS:
            if _QINGHE not in metadata.title or _QINGHE not in normalized_content:
                return None
        elif not teams and lab not in _named_labs(content):
            # Keep the existing match for names like EDA embedded in Chinese prose.
            if not (_ASCII_LAB.fullmatch(lab) and re.search(rf"(?<![a-z0-9_]){re.escape(lab)}", normalized_content)):
                return None
        result = self._evidence_mode(metadata, closing_recruitment=True)
        return result[1] if result and result[0] == AnswerMode.HISTORICAL else None

    def recruitment_deadline(self, metadata: DocumentMetadata, content: str) -> str | None:
        if metadata.deadline_on is not None:
            deadline = metadata.deadline_on
            return f"{deadline.year}年{deadline.month}月{deadline.day}日"
        # An explicitly expired notice may give a month and day without a year.
        deadlines = set()
        for match in _SOURCE_DEADLINE.finditer(content):
            year = match["year"] or match["before_year"]
            try:
                deadline = date(int(year or 2000), int(match["month"] or match["before_month"]),
                                int(match["day"] or match["before_day"]))
            except ValueError:
                return None
            if year and deadline >= self.today:
                return None
            month_day = f"{deadline.month}月{deadline.day}日"
            deadlines.add(f"{year}年{month_day}" if year else month_day)
        return next(iter(deadlines)) if len(deadlines) == 1 else None

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
