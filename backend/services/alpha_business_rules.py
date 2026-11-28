"""S1—S4 业务规则：主动追问与证据适用性判断。

规则来源为 `docs/assignment-03/beta/business-rules.md`，Beta 阶段按
`Beta 接口规范 V2.1-Final` 扩充 S4 学院资源导航与历史政策判断。
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
from decimal import Decimal, localcontext
from enum import Enum
from fractions import Fraction
from unicodedata import normalize
from urllib.parse import urlsplit
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
from backend.services.resource_team_names import r3_team_names

MetadataLookup = Callable[[UUID], DocumentMetadata | None]
ChunkLookup = Callable[[UUID], ParsedChunk | None]
EvidenceCheck = Callable[[AgentRequest, RetrievedChunk], bool]

# 场景与用途标签（仅本模块内部使用，不写入公共契约）
COMPETITION = "competition"
SCHOLARSHIP = "scholarship"
RECOMMENDATION = "recommendation"
RESOURCES = "resources"

# S4 资源类别仅作为模块内部标签，不写入公共契约，也不等于数据库 category_name。
RES_NOTICE = "resource_notice"        # R1 通知与办事渠道
RES_STUDY = "resource_study"          # R2 培养方案、课程与学习资源
RES_LAB = "resource_lab"              # R3 实验室与科研团队
RES_INTRO = "resource_intro"          # R4 研究方向与公开介绍
RES_PRACTICE = "resource_practice"    # R5 科研实践、竞赛及相关资源
RES_CONTACT = "resource_contact"      # R6 学院公开信息与联系方式

RESOURCE_DIRECTION_CODE = "COLLEGE_RESOURCES"

# S4 资料的 category_name 必须使用这六个正式名称之一；不再用正文关键词给资料定类。
RESOURCE_CATEGORY_MAP: dict[str, str] = {
    "通知与办事渠道": RES_NOTICE,
    "培养方案与课程": RES_STUDY,
    "实验室与科研团队": RES_LAB,
    "研究方向与公开介绍": RES_INTRO,
    "科研实践与竞赛": RES_PRACTICE,
    "学院公开信息与联系方式": RES_CONTACT,
}

# 已核实的官方来源域名。fzu.edu.cn 子域名不在表内时一律拒绝，不用后缀包含判断。
OFFICIAL_RESOURCE_HOSTS = {
    "fzu.edu.cn",
    "ccds.fzu.edu.cn",
    "news.fzu.edu.cn",
    "zsks.fzu.edu.cn",
    "xwgk.fzu.edu.cn",
    "xcb.fzu.edu.cn",
    # 以下两个来自林彦翔提供的 R1 已核验栏目，仅用于教务/学工通知渠道。
    "jwch.fzu.edu.cn",
    "stuic.fzu.edu.cn",
}
COLLEGE_RESOURCE_HOST = "ccds.fzu.edu.cn"
WECHAT_ARTICLE_HOST = "mp.weixin.qq.com"
COLLEGE_WECHAT_ACCOUNTS = {"福州大学计算机学院", "福大计算机青年"}
SCHOOL_WECHAT_ACCOUNTS = {"ifzu1958", "fzuzsks"}
# 账号 ID 只认资料侧已核实的官方号。两个学院号的真实 ID 尚未补齐，生产白名单
# 暂为空；补齐前来自 mp.weixin.qq.com 的学院公众号文章不作为已核验来源。
COLLEGE_WECHAT_IDS: set[str] = set()
SCHOOL_WECHAT_IDS = {"ifzu1958"}
ADMISSION_WECHAT_IDS = {"fzuzsks"}
# 名称与账号 ID 必须属同一类主体；不能用合法学院昵称搭配学校号/招生号 ID。
_WECHAT_COLLEGE_NAME_ALIASES = COLLEGE_WECHAT_ACCOUNTS
_WECHAT_SCHOOL_NAME_ALIASES = {"ifzu1958", "福州大学"}
_WECHAT_ADMISSION_NAME_ALIASES = {"fzuzsks", "福州大学招生考试中心"}


def _wechat_family(value: str, *, is_id: bool) -> str | None:
    if is_id:
        if value in SCHOOL_WECHAT_IDS:
            return "school"
        if value in ADMISSION_WECHAT_IDS:
            return "admission"
        if value in COLLEGE_WECHAT_IDS:
            return "college"
        return None
    if value in _WECHAT_COLLEGE_NAME_ALIASES:
        return "college"
    if value in _WECHAT_SCHOOL_NAME_ALIASES:
        return "school"
    if value in _WECHAT_ADMISSION_NAME_ALIASES:
        return "admission"
    return None
_COLLEGE_CONTACT_QUESTION = re.compile(r"学院.*(?:办公电话|电话|邮箱|办公地点|办公室|地址)|办公电话")
_ADMISSION_SCOPE = re.compile(r"招生|报考|录取|招生简章|招生办")


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
QUESTION_VOLUNTEER_COHORT = "请问你想查哪一届推免推荐资格方案的志愿服务计分？"
QUESTION_VOLUNTEER_HOURS = "请提供准确的志愿服务时长，例如 29.5 小时或 30 分钟。"
QUESTION_VOLUNTEER_SCORE_KIND = "你想查志愿服务原始分档、百分制成绩的换算公式，还是它在综合测评总成绩中的权重？"
QUESTION_PROFESSION = "你关注的是哪个专业？"
QUESTION_DEGREE = "你关注的是学术型、专业型，还是直博？"
QUESTION_GRADE = "你现在是大几？不同年级参考的年度通知不同。"
QUESTION_RESOURCE_TYPE = (
    "你想查的是培养方案与课程、实验室与科研团队、竞赛与科研实践，"
    "还是学院通知与办事渠道？"
)
QUESTION_LAB_PURPOSE = "你是想了解这个实验室的研究方向，还是了解怎么报名进实验室？"
QUESTION_PLAN_SCOPE = "你想查哪个专业、哪一级的培养方案？"

_COMPETITION_TOPIC = re.compile(
    r"竞赛|比赛|大赛|挑战杯|数学建模|蓝桥杯|获奖|奖项|(?<!学)奖(?!学金)"
    r"|创新学分|学分认定|综测加分|综测里|综测能加|加几分|能加多少分"
)
_RECOMMENDATION_TOPIC = re.compile(r"推免|保研|免试攻读|直博")
_SCHOLARSHIP_TOPIC = re.compile(r"奖学金|助学金|奖助|单项奖|励志奖")
_RESOURCE_TOPIC = re.compile(
    r"资源|实验室|科研团队|课题组|进组|导师|培养方案|课程|选课|辅修|通识"
    r"|学位要求|科研项目|大创|开放探索|青禾计划|办事|渠道|通知公告|通知在哪|在哪看"
    r"|办公地点|办公室|联系方式|电话|邮箱|官网|学院简介|系所简介|教师主页"
    r"|学院.*(?:竞赛|比赛).*(?:报名|目录|名单|有哪些)"
)
_RESOURCE_FORMAL = re.compile(
    r"创新学分|学分认定|综测|加分|加多少分|能加几分|多少钱|金额|资格|排名"
    r"|遴选|能不能|能否|可否|申请条件|申请资格|够不够|名额"
)
# “通知在哪看”“公告怎么查”问的是 R1 渠道，不是奖学金/推免政策本身。
_NOTICE_CHANNEL_QUERY = re.compile(
    r"(?:通知|公告|公示|消息|信息).{0,12}(?:在哪|哪里|哪儿|怎么查|如何查|查|看|找|渠道|入口)"
    r"|(?:在哪|哪里|哪儿|怎么查|如何查).{0,12}(?:通知|公告|公示|消息)"
)
_BROAD_RESOURCE_QUESTION = re.compile(
    r"学院(?:里|内)?(?:有|提供|能提供)?(?:哪些|什么|啥)资源|资源(?:怎么找|在哪找|都有哪些)"
    r"|学院(?:里|内)?(?:有|提供)(?:哪些|什么|啥)(?:资源|渠道)"
)
_LAB_QUESTION = re.compile(r"实验室|科研团队|课题组|进组|青禾计划")
_LAB_INTRO = re.compile(r"研究方向|研究什么|做什么|研究内容|简介|成果|教师主页|导师")
_LAB_JOIN = re.compile(
    r"报名|怎么进|如何进|进入|能进|能不能进|可以进|进实验室|招|接收|加入|申请|名额|条件"
    r"|联系人|地点|地址|联系方式|电话|邮箱"
)
_LAB_ADMISSION = re.compile(
    r"(?:能(?:不能|否)?|可(?:不可以|以|否)|是否)(?:够)?(?:进|加入|被接收)"
    r"|(?:接收|招募|招新|申请|报名|入组|加入)(?:对象|要求|条件|资格)|接收哪些|接收什么"
    r"|我[^？?，,。]{0,20}(?:能|可|是否)[^？?，,。]{0,8}报名"
)
_LAB_CONTACT_DETAILS = r"联系方式|联系电话|电话|邮箱|联系人|联系谁|联系哪个|负责人"
_LAB_CONTACT = re.compile(rf"{_LAB_CONTACT_DETAILS}|地址|地点")
_LAB_LIST = re.compile(r"有哪些实验室|实验室(?:名单|名录|一览|列表|目录)|学院.*实验室|哪些实验室")
_COMPETITION_REGISTRATION = re.compile(r"报名|参赛")
_STUDY_QUESTION = re.compile(r"培养方案|课程|选课|辅修|通识|学位要求|修多少")
_PLAN_MAJOR = re.compile(r"计算机专业|软件专业|计算机类|软件类|人工智能专业|大数据专业|信息安全专业")
_CONTACT_QUESTION = re.compile(r"联系方式|电话|邮箱|办公地点|办公室|地址|官网|学院简介|系所简介")
_NOTICE_QUESTION = re.compile(r"通知|公告|办事|办理|渠道|在哪看|在哪办|材料|窗口|盖章")
_PRACTICE_QUESTION = re.compile(r"科研项目|大创|开放探索|竞赛|比赛|报名|目录|名单")
_CURRENT_INTENT = re.compile(r"现在|目前|当前|今年|最新|现行|本学期|这学期")
_HISTORICAL_INTENT = re.compile(
    r"去年|前年|往年|以前|原政策|旧版|旧[^，。]{0,4}(?:办法|政策|文件|通知|版本)"
    r"|原(?:办法|文件|通知)|之前|以前年度|当时|上一年度|历史|原来"
)
# “招几个/接收几个”是年度计划人数，不等于当前剩余名额；只有现在、剩余、
# 名额等当前口径才触发名额拒绝。
_CURRENT_QUOTA = re.compile(
    r"现在还?招(?:几个|几人|多少|多少名)|目前还?招(?:几个|几人|多少)"
    r"|现在.*(?:几个|名额|剩下|还剩|剩余)|目前.*(?:几个|名额|剩下|还剩|剩余)"
    r"|当前.*(?:几个|名额|剩下|还剩|剩余)|还有.*名额|剩余.*名额|名额.*剩|还剩"
)

_PURPOSE_CREDIT = re.compile(r"创新学分|学分认定|认定多少学分|原始分")
_PURPOSE_EVALUATION = re.compile(
    r"综测|综合素质测评|综合素质评价|能加多少分|加多少分|加几分|加分|折算多少分"
)

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
_TEAM = re.compile(r"团队|集体|合作|组队|队友|队员|共同完成")
_TEAM_WE = re.compile(r"我们(?:组|队|团队|小组|一起|合作)")
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
_RECOMMENDATION_QUALIFICATION = re.compile(r"资格|排名|遴选|推荐办法|加分|加多少分|要求|条件|经历|名额分配")
_VOLUNTEER = re.compile(r"志愿服务|志愿时长|志愿活动")
_VOLUNTEER_SCORE = re.compile(r"成绩|原始分|计分|加分|算分|得分|评分|(?:[多少几]|[0-9])分|分数|怎么算|怎么给分")
_VOLUNTEER_RAW = re.compile(r"原始分|分档|时长计分|按时长")
_VOLUNTEER_RAW_MAX = re.compile(
    r"原始分(?:的)?(?:最高|最大)(?:档(?:位)?|(?:可以|能|可)?(?:加|计|得|拿)(?:几|多少)分)"
)
_VOLUNTEER_MAX_REFERENCE = r"(?:最高|最大)原始分|原始分(?:最高|最大)"
_VOLUNTEER_PERCENT = re.compile(
    rf"百分制|基础分|换算公式|归一化"
    rf"|(?:专业|入围学生)(?:的)?(?:志愿服务)?(?:{_VOLUNTEER_MAX_REFERENCE})"
)
_SCORE_CONNECTOR = r"\s*(?:以及|和|与|及|还有|、)\s*"
_VOLUNTEER_RAW_WITH_PERCENT = re.compile(
    rf"原始分档|原始分(?:分别|是|有|为)?多少|原始分{_SCORE_CONNECTOR}(?:百分制|总评|权重)"
    rf"|百分制(?:成绩)?{_SCORE_CONNECTOR}原始分"
)
_VOLUNTEER_WEIGHT = re.compile(r"权重|占比|占(?:多少|几)|百分比|百分之零点三|0\.3\s*%")
_VOLUNTEER_OTHER_ISSUE = re.compile(
    r"复试|报名|申请流程|怎么申请|申报|材料|证明|奖学金|创新学分|学分认定|是否符合|能否推免|能不能推免"
)
_HOUR_VALUE = r"[+\-−]?\d+(?:\.\d+)?"
_HOUR_UNIT = r"(?:小时|钟头)"
_DURATION_UNIT = r"(?:小时|钟头|分钟|刻钟)"
_DURATION_ENDPOINT = rf"(?:{_HOUR_VALUE}|[零〇一二两三四五六七八九十百千万半点几数]+|若干)"
_DURATION_NUMBER_BOUNDARY = r"(?<![0-9A-Za-z.+\-−零〇一二两三四五六七八九十百千万点个])(?<!\d,)"
_DURATION_COUNT = re.compile(rf"{_DURATION_UNIT}|秒(?:钟)?")
_DURATION_PART = re.compile(rf"({_HOUR_VALUE}|半)\s*(?:个\s*)?({_DURATION_UNIT})")
_DURATION_IN_HOURS = {"小时": Fraction(1), "钟头": Fraction(1), "分钟": Fraction(1, 60), "刻钟": Fraction(1, 4)}
_INEXACT_HOUR_PREFIX = (
    r"不到|不足|不满|未满|少于|低于|超过|超出|多于|大于(?:等于)?|小于(?:等于)?|高于|不超过|不低于|不少于|不多于"
    r"|至少|至多|最多|最少|约(?:有|为)?|大约|大概|估计|近|差不多|将近|接近|大致|[<>≤≥]"
)
_INEXACT_HOUR_SUFFIX = (
    r"(?:及其|或者|及|或)?\s*以[上下内外]|(?:之)?内(?!容)|不到|不足|未满"
    r"|左右|上下|多(?:一点|一些)?(?![少长大久])|余|出头|起|或更[多少]"
)
_HOUR_RANGE = r"(?:到|至|或(?:者)?|[-—–~～±])"
_DURATION_TERM = rf"{_DURATION_ENDPOINT}\s*(?:个\s*)?{_DURATION_UNIT}"
_DURATION_RANGE = (
    rf"(?:{_DURATION_TERM}\s*{_HOUR_RANGE}\s*{_DURATION_ENDPOINT}(?:\s*{_DURATION_UNIT})?"
    rf"|{_DURATION_ENDPOINT}\s*{_HOUR_RANGE}\s*{_DURATION_TERM})"
)
_VOLUNTEER_DURATION = re.compile(
    rf"{_DURATION_NUMBER_BOUNDARY}(?:"
    rf"{_HOUR_VALUE}\s*(?:个\s*)?{_HOUR_UNIT}(?:\s*(?:{_HOUR_VALUE}\s*分钟|半))?"
    rf"|(?:{_HOUR_VALUE}|半)\s*(?:个\s*)?{_DURATION_UNIT})"
)
_INEXACT_VOLUNTEER_HOURS = re.compile(
    rf"(?:{_INEXACT_HOUR_PREFIX})\s*{_DURATION_TERM}"
    rf"|{_DURATION_RANGE}"
    rf"|{_DURATION_UNIT}(?:\s*半)?\s*(?:\(\s*)?(?:{_INEXACT_HOUR_SUFFIX})"
    rf"|(?:{_HOUR_VALUE}|[零〇一二两三四五六七八九十百千万]+)\s*(?:个\s*)?半\s*{_HOUR_UNIT}"
)
_VOLUNTEER_HOURS_REPLY = re.compile(
    rf"(?:那(?:么)?[，,]?\s*)?(?:(?:{_INEXACT_HOUR_PREFIX})\s*)?"
    rf"(?:{_DURATION_RANGE}|{_DURATION_TERM}(?:\s*(?:{_HOUR_VALUE}\s*分钟|半))?)"
    rf"(?:\s*(?:\(\s*)?(?:{_INEXACT_HOUR_SUFFIX})\)?)?"
    r"(?:\s*(?:呢|(?:是|能加|可以加|算|计)?(?:多少|几)分))?[？?。！!]*"
)
_VOLUNTEER_COHORT_REPLY = re.compile(r"(?:20\d{2}年|20\d{2}届)(?:呢|[？?。！!])*\s*")
_VOLUNTEER_KIND_REPLY = re.compile(
    r"(?:我想(?:问|查|看)|想(?:问|查|看)|查|看)?\s*"
    rf"({_VOLUNTEER_RAW_MAX.pattern}(?:是?多少)?|原始分(?:档|数)?"
    r"|百分制(?:成绩|换算(?:公式)?)?|(?:总评|综合测评)?(?:权重|占比))[？?。！!]*"
)
_VOLUNTEER_SCORE_RECORD = "计算机学院-2027-推免资格推荐"
_VOLUNTEER_SCORE_SOURCE = "https://ccds.fzu.edu.cn/info/1119/11932.htm"
_VOLUNTEER_SCORE_ROW = re.compile(
    r"志愿服务[^。；]*?0[-—–至]30小时[）)]?加原始分2分[；;，,]"
    r"30[-—–至]60小时[）)]?加原始分4分[；;，,]"
    r"60[-—–至]100小时及以上加原始分6分"
)
_VOLUNTEER_WEIGHT_TERM = re.compile(r"志愿服务成绩[×xX*]\s*0\.3%")
_VOLUNTEER_PERCENT_FORMULA = re.compile(
    r"参加志愿服务成绩=\(基础分60\+被推荐学生参加志愿服务(?:成绩|原始分)\)"
    r"/\(基础分60\+本专业推免入围学生参加志愿服务(?:成绩|原始分)最高值\)[×xX*]100(?![\d.])"
)
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
    category_name: str = ""
    business_direction_codes: tuple[str, ...] = ()
    document_type: str = ""
    source_url: str = ""
    publisher: str | None = None
    version_no: str = ""
    policy_status: str = ""
    temporal_notes: dict[str, object] | None = None
    published_on: date | None = None
    effective_on: date | None = None


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


def alpha_clarification_rule(
    request: AgentRequest,
    *,
    today: Callable[[], date] = date.today,
) -> str | None:
    """必要信息不足时返回单个追问问句，信息齐备时返回 None。

    `today` 与证据判断共用同一个时间源，固定日期测试时追问口径不会漂移。
    """
    request = contextual_volunteer_request(request) or request
    text = _user_text(request)
    if selection := volunteer_scoring_request(request):
        if selection.invalid_hours:
            return QUESTION_VOLUNTEER_HOURS
        if not selection.kinds:
            return QUESTION_VOLUNTEER_SCORE_KIND
        if not _years(text) and not _has_time_intent(text):
            return QUESTION_VOLUNTEER_COHORT
        return None
    scenario, _ = _analyse(text, request.query)
    if scenario is None:
        return QUESTION_TOPIC
    if scenario == COMPETITION:
        return _clarify_competition(text, request.query)
    if scenario == SCHOLARSHIP:
        return _clarify_scholarship(text, request.query, today=today())
    if scenario == RESOURCES:
        return _clarify_resources(text, request.query)
    return _clarify_recommendation(text, request.query, today=today())


def alpha_evidence_check(request: AgentRequest, chunk: RetrievedChunk) -> bool:
    """默认入口；查询函数来自 `bind_metadata_lookup` / `bind_chunk_lookup`。"""
    return _assess(request, chunk, _lookup, _chunk_lookup, date.today())


# --------------------------------------------------------------------------- 文本解析


def _user_text(request: AgentRequest) -> str:
    previous = [turn.content for turn in request.history if turn.role == LLMRole.USER]
    return "\n".join([*previous, request.query]).strip()


class VolunteerScoreKind(Enum):
    RAW = "原始分"
    PERCENT = "百分制成绩"
    WEIGHT = "总评权重"


@dataclass(frozen=True)
class VolunteerScoringRequest:
    kinds: frozenset[VolunteerScoreKind]
    hours: tuple[Fraction, ...]
    invalid_hours: bool
    raw_max: bool = False


def volunteer_scoring_request(request: AgentRequest) -> VolunteerScoringRequest | None:
    query = normalize("NFKC", request.query)
    if not _VOLUNTEER.search(query) or _VOLUNTEER_OTHER_ISSUE.search(query):
        return None
    duration_units = _DURATION_COUNT.findall(query)
    kinds = {kind for kind, cue in (
        (VolunteerScoreKind.RAW, _VOLUNTEER_RAW),
        (VolunteerScoreKind.PERCENT, _VOLUNTEER_PERCENT),
        (VolunteerScoreKind.WEIGHT, _VOLUNTEER_WEIGHT),
    ) if cue.search(query)}
    raw_max = bool(_VOLUNTEER_RAW_MAX.search(query))
    # Only an explicit tier question or a joint request selects RAW alongside the formula.
    if VolunteerScoreKind.PERCENT in kinds and not (raw_max or _VOLUNTEER_RAW_WITH_PERCENT.search(query)):
        kinds.discard(VolunteerScoreKind.RAW)
    ambiguous_max = kinds == {VolunteerScoreKind.RAW} and not raw_max and re.search(_VOLUNTEER_MAX_REFERENCE, query)
    if ambiguous_max:
        kinds.clear()
    if duration_units and not (kinds or ambiguous_max) and "成绩" not in query and "折算" not in query:
        kinds.add(VolunteerScoreKind.RAW)
    if not (kinds or duration_units or _VOLUNTEER_SCORE.search(query) or "折算" in query):
        return None
    durations = _VOLUNTEER_DURATION.findall(query)
    if duration_units and (sum(len(_DURATION_COUNT.findall(value)) for value in durations) != len(duration_units)
                           or _INEXACT_VOLUNTEER_HOURS.search(query)):
        return VolunteerScoringRequest(frozenset(kinds), (), invalid_hours=True)
    hours = []
    for duration in durations:
        parts = [
            (Fraction(1, 2) if value == "半" else Fraction(value.replace("−", "-"))) * _DURATION_IN_HOURS[unit]
            for value, unit in _DURATION_PART.findall(duration)
        ]
        if any(part < 0 for part in parts):
            return VolunteerScoringRequest(frozenset(kinds), (), invalid_hours=True)
        hours.append(sum(parts, Fraction(1, 2) if duration.endswith("半") else Fraction(0)))
    return VolunteerScoringRequest(frozenset(kinds), tuple(hours), invalid_hours=False, raw_max=raw_max)


def contextual_volunteer_request(request: AgentRequest) -> AgentRequest | None:
    """Resolve short hour/cohort replies using only the latest matching user topic."""
    query = normalize("NFKC", request.query.strip())
    current = volunteer_scoring_request(request)
    hours_reply = _VOLUNTEER_HOURS_REPLY.fullmatch(query)
    cohort_reply = _VOLUNTEER_COHORT_REPLY.fullmatch(query)
    kind_reply = _VOLUNTEER_KIND_REPLY.fullmatch(query)
    if not (current or hours_reply or cohort_reply or kind_reply):
        return None
    previous = None
    previous_scoring = None
    retained_cohort = None
    retained_kind = None
    retained_hours = None
    for turn in reversed(request.history):
        if turn.role != LLMRole.USER:
            continue
        content = normalize("NFKC", turn.content.strip())
        if _VOLUNTEER_HOURS_REPLY.fullmatch(content):
            if retained_hours is None:
                retained_hours = content
            continue
        if _VOLUNTEER_COHORT_REPLY.fullmatch(content):
            if retained_cohort is None:
                retained_cohort = _YEAR.search(content)[0]
            continue
        if concept := _VOLUNTEER_KIND_REPLY.fullmatch(content):
            if retained_kind is None:
                retained_kind = concept[1]
            continue
        previous_scoring = volunteer_scoring_request(request.model_copy(update={"query": turn.content}))
        if previous_scoring:
            previous = turn
        break
    if previous_scoring is None:
        return request.model_copy(update={"query": query, "history": []}) if current else None
    history = [previous]
    if hours_reply:
        kinds = "和".join(kind.value for kind in VolunteerScoreKind if kind in previous_scoring.kinds)
        topic = retained_kind or kinds or "成绩"
        return request.model_copy(update={
            "query": f"{retained_cohort or ''}推免志愿服务{topic}：{query}",
            "history": [] if retained_cohort else history,
        })
    if kind_reply:
        original = normalize("NFKC", previous.content)
        # Keep an uncorrected range intact so it can never become a single endpoint.
        if previous_scoring.invalid_hours and not retained_hours:
            return request.model_copy(update={"query": f"{retained_cohort or ''}{original}", "history": []})
        hours = retained_hours or "、".join(_VOLUNTEER_DURATION.findall(original))
        return request.model_copy(update={
            "query": f"{retained_cohort or ''}推免志愿服务{kind_reply[1]} {hours}".strip(),
            "history": [] if retained_cohort else history,
        })
    if cohort_reply:
        subject = _YEAR.sub("", normalize("NFKC", previous.content))
        if retained_kind:
            if retained_hours or not previous_scoring.invalid_hours:
                hours = retained_hours or "、".join(_VOLUNTEER_DURATION.findall(subject))
                subject = f"推免志愿服务{retained_kind} {hours}"
        return request.model_copy(update={"query": f"{query} {subject}", "history": []})
    if retained_cohort and not _has_time_intent(query):
        query = f"{retained_cohort} {query}"
    return request.model_copy(update={"query": query, "history": [] if _has_time_intent(query) else history})


def volunteer_service_raw_score(hours: int | Decimal | Fraction) -> int:
    """Project interpretation for the 2027 recommendation plan, in hours."""
    if (isinstance(hours, Decimal) and not hours.is_finite()) or hours < 0:
        raise ValueError("Volunteer service hours must be finite and nonnegative")
    if hours < 30:
        return 2
    if hours < 60:
        return 4
    return 6


def format_volunteer_hours(hours: Fraction) -> str:
    """Display an exact decimal where possible, otherwise retain the fraction."""
    with localcontext() as context:
        context.prec = len(str(hours.numerator)) + hours.denominator.bit_length()
        decimal = Decimal(hours.numerator) / Decimal(hours.denominator)
    return f"{decimal:f}" if Fraction(decimal) == hours else str(hours)


def volunteer_scoring_evidence(
    record_code: str | None, chunk: RetrievedChunk, selection: VolunteerScoringRequest,
) -> set[VolunteerScoreKind]:
    if record_code != _VOLUNTEER_SCORE_RECORD or chunk.source_url != _VOLUNTEER_SCORE_SOURCE:
        return set()
    compact = re.sub(r"\s+", "", normalize("NFKC", chunk.content))
    return {kind for kind, clause in (
        (VolunteerScoreKind.RAW, _VOLUNTEER_SCORE_ROW),
        (VolunteerScoreKind.PERCENT, _VOLUNTEER_PERCENT_FORMULA),
        (VolunteerScoreKind.WEIGHT, _VOLUNTEER_WEIGHT_TERM),
    ) if kind in selection.kinds and clause.search(compact)}


def _has_time_intent(text: str) -> bool:
    """本轮是否明确写了年份、当前时点或历史时点。"""
    return bool(
        _CURRENT_INTENT.search(text)
        or _HISTORICAL_INTENT.search(text)
        or _CURRENT_QUOTA.search(text)
        or _CURRENT_AVAILABILITY.search(text)
        or _years(text)
        or re.search(r"20\d{2}\s*[-—–]\s*20\d{2}\s*学年", text)
        or "去年" in text
        or "前年" in text
    )


def _temporal_text(request: AgentRequest, full_text: str) -> str:
    """时间判断只看本轮明确口径；本轮没写时间时才回退到最近一条带时间的历史。

    不能把全部历史与 query 拼在一起做年份或“当时/现在”判断，否则上一轮的
    2025 会污染本轮的 2024，上一轮的“当时”会覆盖本轮的“现在”。
    """
    query = (request.query or "").strip()
    if query and _has_time_intent(query):
        return query
    for turn in reversed(request.history):
        if turn.role != LLMRole.USER:
            continue
        content = turn.content.strip()
        if content and _has_time_intent(content):
            return content
    return query or full_text


def _detect(text: str) -> tuple[str | None, str | None]:
    competition = _COMPETITION_TOPIC.search(text)
    recommendation = _RECOMMENDATION_TOPIC.search(text)
    scholarship = _SCHOLARSHIP_TOPIC.search(text)
    resource = _RESOURCE_TOPIC.search(text)
    purpose = _purpose(text)
    # “奖学金通知在哪看”“推免通知在哪看”问的是通知渠道，先按 S4 处理。
    if (
        resource
        and _NOTICE_CHANNEL_QUERY.search(text)
        and not _RESOURCE_FORMAL.search(text)
    ):
        return RESOURCES, None
    # 推免语境优先：竞赛经历、竞赛获奖只是推免条件或计分材料，不能因为出现
    # “竞赛”就整题判成竞赛认定。只有明确问创新学分或综测加分才回到 S1/S2。
    if recommendation:
        if _PURPOSE_CREDIT.search(text) and re.search(r"创新学分|学分认定", text):
            return COMPETITION, PURPOSE_CREDIT
        if _PURPOSE_EVALUATION.search(text) and re.search(
            r"综测|综合素质测评|综合素质评价", text
        ):
            return COMPETITION, PURPOSE_EVALUATION
        if _PURPOSE_EVALUATION.search(text):
            # 推免计分仍归 S3，但保留“加分”意图供回答组织，不按综测定档。
            return RECOMMENDATION, PURPOSE_EVALUATION
        return RECOMMENDATION, None
    # 只有资源类名词、没有正式办理/资格/加分意图时，归 S4。
    if not competition and not scholarship and (resource or r3_team_names(text)):
        return RESOURCES, None
    # 奖学金名称里也常带“学科竞赛类”等字样，只有明确问创新学分或综测加分
    # 才按竞赛认定处理，否则仍归奖学金场景。
    if competition and scholarship:
        return (
            (COMPETITION if purpose in {PURPOSE_CREDIT, PURPOSE_EVALUATION} else SCHOLARSHIP),
            purpose,
        )
    if competition:
        # “学院有哪些竞赛可以报名”“竞赛通知在哪看”问的是资源入口，不是认定规则。
        if resource and not _RESOURCE_FORMAL.search(text):
            return RESOURCES, None
        return COMPETITION, purpose
    if scholarship:
        if resource and _BROAD_RESOURCE_QUESTION.search(text):
            return RESOURCES, None
        return SCHOLARSHIP, None
    if resource:
        return RESOURCES, None
    return None, None


def is_lab_admission_question(text: str) -> bool:
    return bool(_LAB_ADMISSION.search(text) and _detect(text)[0] == RESOURCES
                and (_LAB_QUESTION.search(text) or r3_team_names(text)))


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


_LEVEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("international", re.compile(r"国际级|国际性|国际竞赛")),
    ("national", re.compile(r"国家级|国家[特一二三]?等(?:奖)?|国家奖|全国奖|全国总决赛|国赛")),
    ("provincial", re.compile(r"省部级|省级|省赛|赛区|省[一二三]等")),
    ("school", re.compile(r"校级|学校级")),
    ("college", re.compile(r"院级|学院级")),
)
# 否定、转折表达要把被否定的级别排除，例如“不是国家级，是省级二等奖”。
_NEGATION_BEFORE = re.compile(r"(不是|并非|而非|而不是|也不算|不算|不能算|没有|未获|并没有)([^，。；,;]{0,4})?$")


def _level(text: str) -> str | None:
    """级别只看明确写出的奖项级别；竞赛名称里的“全国”不等于国家级。"""
    for name, pattern in _LEVEL_PATTERNS:
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 10):match.start()]
            if _NEGATION_BEFORE.search(prefix):
                continue
            return name
    return None


def _level_for(subject: str | None, text: str) -> str | None:
    """本轮问题写了级别就采信本轮，历史只在没写级别时补位。"""
    if subject:
        level = _level(subject)
        if level is not None:
            return level
    return _level(text)


def _award_grade(text: str) -> str | None:
    match = _AWARD_GRADE.search(text)
    return match.group() if match else None


def _team(text: str) -> bool | None:
    if _TEAM.search(text) or _TEAM_WE.search(text):
        return True
    if _INDIVIDUAL.search(text):
        return False
    return None


_COMPETITION_NAMES = re.compile(r"数学建模|蓝桥杯|挑战杯|互联网\+|电子设计|程序设计|机器人大赛|智能车|创新创业大赛")
_WORK_NAME = re.compile(r"《([^》]{1,80})》")
_WORK_NAMED = re.compile(
    r"(?:作品|项目|论文|成果)(?:名称|题目|名字|名|叫)(?:叫|为|是|：|:)?\s*"
    r"[“\"「]?([^，。；;、\s”\"」]{2,40})"
)


def _competition_keys(text: str) -> set[str]:
    return set(_COMPETITION_NAMES.findall(text))


def _works(text: str) -> set[str]:
    """作品标识：书名号标题，或“作品名称叫 XXX”这类不带书名号的写法。"""
    names = set(_WORK_NAME.findall(text))
    names.update(_WORK_NAMED.findall(text))
    return names


def _history_text(text: str, subject: str | None) -> str:
    """从拼接后的上下文里取历史部分：`_user_text` 把本轮问题放在最后。"""
    if subject and text.endswith(subject):
        return text[: -len(subject)]
    return text


def _rank_for(subject: str | None, history_text: str) -> int | None:
    """本轮排名优先；历史排名只在本轮没写、且确认同一竞赛同一作品时复用。"""
    current = subject or history_text
    rank = _rank(current)
    if rank is not None:
        return rank
    if not subject or not history_text:
        return None
    if not (_competition_keys(subject) & _competition_keys(history_text)):
        return None
    # 只有本轮明确同一作品时才继承；本轮没说作品、或换了作品都重新追问。
    current_works = _works(subject)
    if not current_works:
        return None
    if not (current_works & _works(history_text)):
        return None
    return _rank(history_text)


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
    if _works(text):
        return True
    return bool(re.search(r"(?:作品|项目|论文)是[《“]", text))


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


_PRACTICE_CATEGORY = re.compile(r"科研项目|大创|开放探索|竞赛|比赛|目录|名单")
_NOTICE_CATEGORY = re.compile(r"通知|公告|公示|办事|办理|渠道|在哪看|在哪办|窗口|盖章")


def _resource_categories(text: str) -> set[str]:
    """返回问题涉及的资源类别；多类别问题按分句分别识别，不互相覆盖。"""
    categories: set[str] = set()
    parts = re.split(r"[，,；;、]|以及|还有|和|与|及", text)
    for part in parts:
        current = part.strip()
        if not current:
            continue
        if _LAB_QUESTION.search(current) or r3_team_names(current):
            join = bool(_LAB_JOIN.search(current))
            intro = bool(_LAB_INTRO.search(current))
            contact = bool(_LAB_CONTACT.search(current))
            if join or contact:
                categories.add(RES_LAB)
            if intro:
                categories.add(RES_INTRO)
            if not (join or intro or contact):
                # 只提“实验室怎么样”时，招募与方向两类资料都可用于比对。
                categories.update({RES_LAB, RES_INTRO})
            continue
        if _STUDY_QUESTION.search(current):
            # “培养方案在哪看”问的是方案本身；同一分句里的“在哪看”不能加成 R1。
            categories.add(RES_STUDY)
            continue
        if _PRACTICE_CATEGORY.search(current):
            categories.add(RES_PRACTICE)
        if _NOTICE_CATEGORY.search(current):
            categories.add(RES_NOTICE)
        if _CONTACT_QUESTION.search(current):
            categories.add(RES_CONTACT)
    return categories


def _resource_category(text: str) -> str | None:
    """单个类别入口；多类别场景由 `_resource_categories()` 处理。"""
    categories = _resource_categories(text)
    for category in (
        RES_LAB, RES_INTRO, RES_STUDY, RES_PRACTICE, RES_NOTICE, RES_CONTACT
    ):
        if category in categories:
            return category
    return None


def _clarify_resources(
    text: str, subject: str | None = None
) -> str | None:
    current = subject or text
    categories = _resource_categories(current)
    if not categories:
        # 本轮省略主语时，从完整上下文补齐资源类别。
        categories = _resource_categories(text)
    if not categories and _BROAD_RESOURCE_QUESTION.search(text):
        return QUESTION_RESOURCE_TYPE
    if not categories:
        # 本轮只给了一个实验室/资源名称或省略主语，先确认要办哪类事。
        return QUESTION_RESOURCE_TYPE
    if len(categories) > 1:
        # 多类别问题分别判断，不因实验室或培养方案的追问卡住另一类。
        if categories <= {RES_LAB, RES_INTRO}:
            if (
                _LAB_LIST.search(current)
                or _LAB_JOIN.search(current)
                or _LAB_INTRO.search(current)
            ):
                return None
            return QUESTION_LAB_PURPOSE
        return None
    category = next(iter(categories))
    if category == RES_LAB:
        # 名录类问题直接答；问某个实验室但没说目的时才追问研究方向还是报名。
        if _LAB_LIST.search(current) or _LAB_JOIN.search(current) or re.search(_LAB_CONTACT_DETAILS, current):
            return None
        if _LAB_INTRO.search(current):
            return None
        return QUESTION_LAB_PURPOSE
    if category == RES_STUDY:
        # 培养方案依赖专业与年级；只说“培养方案/课程”无法定位适用版本。
        if not _PROFESSION.search(current) and not _PLAN_MAJOR.search(current) and not _GRADE.search(current):
            return QUESTION_PLAN_SCOPE
    return None


def _clarify_competition(text: str, subject: str | None = None) -> str | None:
    """追问时本轮问题优先，历史只补本轮没说的槽位。

    同一会话换竞赛或换事项时，历史里的级别、个人/团队、作品不能盖掉本轮表达。
    """
    current = subject or text
    # 查目录、查级别归属属于资料缺口，追问解决不了，交给证据判断。
    if _LEVEL_LOOKUP_QUESTION.search(current):
        return None
    purpose = _purpose(current) or _purpose(text)
    if purpose is None:
        if "团队" in current and _COMPETITION_REGISTRATION.search(current):
            if not _competition_keys(text):
                return QUESTION_COMPETITION_NAME
            return QUESTION_LEVEL if _level_for(subject, text) is None else None
        return QUESTION_PURPOSE
    if purpose == PURPOSE_RECOMMENDATION:
        return None
    level = _level_for(subject, text)
    # 综测加分依赖《学科竞赛等级目录》定档；国家级与省部级无法定类，
    # 补齐个人/集体也仍然无法给出分值，直接走证据不足。
    if purpose == PURPOSE_EVALUATION and level in {
        "international", "national", "provincial",
    }:
        return None
    if not re.search(r"竞赛|比赛|大赛|杯|赛区", text):
        return QUESTION_COMPETITION_NAME
    if purpose == PURPOSE_CREDIT and not _work_mentioned(current):
        # 创新学分按作品认定，赛事与作品必须能对上；换了竞赛后旧作品不算。
        return QUESTION_WORK_NAME
    if level is None:
        return QUESTION_LEVEL
    rank = _rank_for(subject, _history_text(text, subject))
    if _award_grade(current) is None and _award_grade(text) is None and rank is None:
        return QUESTION_AWARD_GRADE
    team = _team(current)
    if team is None:
        team = _team(text)
    if team is None:
        return QUESTION_FORMAT
    if team and purpose == PURPOSE_CREDIT:
        # 只在前八名之外未说明时追问；已经说清第九名及以后不再重复追问。
        if rank is None:
            return QUESTION_TOP_EIGHT
    if purpose == PURPOSE_EVALUATION:
        # 个人项目同样要计上一学期成果、同样要求福大第一署名，不因为个人申报跳过。
        if team and rank is None and not _ORDER.search(current):
            return QUESTION_ORDER
        if _semester_state(text) is None:
            return QUESTION_SEMESTER
        if _first_unit_state(text) is None:
            return QUESTION_FIRST_UNIT
    return None


def _clarify_scholarship(
    text: str, subject: str | None = None, *, today: date | None = None
) -> str | None:
    # 库外年度直接证据不足，不追问年度（2.5）。
    if _future_year(text, today=today or date.today()):
        return None
    category = _scholarship_category(subject or "") or _scholarship_category(text)
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


def _clarify_recommendation(
    text: str, subject: str | None = None, *, today: date | None = None
) -> str | None:
    if _future_year(text, today=today or date.today()) or _EXTERNAL_SCHOOL.search(text):
        return None
    obj = _recommendation_object(subject) if subject else None
    if obj is None:
        obj = _recommendation_object(text)
    if obj == REVIEW and _REVIEW_DETAIL.search(subject or text):
        # 专业与学位类型是两件事：认出专业不等于知道学术型/专业型/直博。
        if not _PROFESSION.search(text):
            return QUESTION_PROFESSION
        if _degree_type(text) is None:
            return QUESTION_DEGREE
        return None
    if obj == REVIEW:
        # 复试、材料、招生计划属于学院接收环节，与年级、排名无关，不追问年级。
        return None
    # 年级只对校内推荐资格、排名和遴选有意义。
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
        request = contextual_volunteer_request(request) or request
        volunteer = volunteer_scoring_request(request)
        text = _user_text(request)
        facts = _document_facts(chunk, lookup)
        if not _basic_gates(chunk, today):
            return False
        if not facts.has_metadata:
            return False
        # 人工审核、版本一致性与未来日期属于所有场景的公共门禁。
        if not _human_approved(facts):
            return False
        if not _metadata_consistent(facts, chunk, today):
            return False
        if _EXTERNAL_SCHOOL.search(text):
            return False
        scenario, purpose = (RECOMMENDATION, None) if volunteer else _analyse(text, request.query)
        # 未识别场景不能绕过元数据与适用范围检查直接放行。
        if scenario is None:
            return False
        temporal_text = _temporal_text(request, text)
        if scenario != RESOURCES and _timeliness_conflict(
            temporal_text, facts, today, chunk.timeliness_verification_status
        ):
            return False
        if scenario == RESOURCES:
            return _check_resources(
                request, text, facts, chunk, chunk_lookup, today, temporal_text
            )
        # S1—S3 都要确认文档类型与适用范围；缺元数据即视为无法确认。
        if not facts.applicability:
            return False
        kind = _classify(facts)
        if _applicability(text, facts, today) is False:
            return False
        if not _section_applies(text, facts, chunk, chunk_lookup):
            return False
        if _year_conflict(temporal_text, kind, facts, today):
            return False
        if _deadline_conflict(
            temporal_text, facts, today, chunk.timeliness_verification_status
        ):
            return False
        if scenario == COMPETITION:
            return _check_competition(text, purpose, kind, request.query)
        if scenario == SCHOLARSHIP:
            return _check_scholarship(text, kind, today, request.query)
        if volunteer:
            return (not volunteer.invalid_hours and kind == _KIND_RECOMMENDATION_QUALIFICATION
                    and any(volunteer_scoring_evidence(facts.record_code, chunk, volunteer)))
        return _check_recommendation(text, kind, request.query)
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
        TimelinessVerificationStatus.SUPERSEDED,
        TimelinessVerificationStatus.EXPIRED,
    }:
        return False
    if not chunk.content.strip() or not chunk.title.strip():
        return False
    for value in (chunk.published_on, chunk.effective_on):
        if value is not None and value > today:
            return False
    return True


def _check_competition(
    text: str, purpose: str | None, kind: str, subject: str | None = None
) -> bool:
    current = subject or text
    if _LEVEL_LOOKUP_QUESTION.search(current):
        return kind == _KIND_CREDIT_CATALOG
    if purpose == PURPOSE_RECOMMENDATION:
        return False
    if purpose == PURPOSE_CREDIT:
        # 创新学分只认教务处级别认定目录与学分认定办法。
        return kind in {_KIND_CREDIT, _KIND_CREDIT_CATALOG}
    if purpose == PURPOSE_EVALUATION:
        level = _level_for(subject, text)
        if level is None:
            return False
        if level in {"international", "national", "provincial"}:
            # 综测 A+/A/A-/B/C 只能由学科竞赛等级目录定档；教务处级别认定目录不顶替。
            return kind == _KIND_EVAL_CATALOG
        # 校级、院级两档写在综合素质评价办法里，等级目录不负责这两档。
        return kind == _KIND_EVALUATION
    return False


def _check_scholarship(
    text: str, kind: str, today: date, subject: str | None = None
) -> bool:
    category = _scholarship_category(subject or text)
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


def _check_recommendation(
    text: str, kind: str, subject: str | None = None
) -> bool:
    obj = _recommendation_object(subject) if subject else None
    if obj is None:
        obj = _recommendation_object(text)
    if obj == REVIEW:
        # 复试、材料、招生计划只认学院接收推免的复试方案。
        return kind == _KIND_RECOMMENDATION_REVIEW
    if obj == QUALIFICATION or (obj is None and _PERSONAL.search(text)):
        # 推荐资格只认学院推荐资格方案；校级办法未入库，复试方案不能代替。
        return kind == _KIND_RECOMMENDATION_QUALIFICATION
    return kind == _KIND_RECOMMENDATION_QUALIFICATION


# --------------------------------------------------------------------------- S4 学院资源导航

_RESOURCE_APPLICABILITY_REQUIRED = {
    RES_NOTICE, RES_STUDY, RES_LAB, RES_PRACTICE,
}


def _resource_document_kinds(facts: _DocumentFacts, chunk: RetrievedChunk | None = None) -> set[str]:
    """S4 资料只按正式 category_name 定类，避免正文关键词把 R3/R4 混在一起。"""
    name = (facts.category_name or "").strip()
    kind = RESOURCE_CATEGORY_MAP.get(name)
    return {kind} if kind else set()


def _official_url_host(url: str) -> str | None:
    """严格解析 URL：仅 HTTPS、无 userinfo、无非法端口、hostname 精确匹配白名单。"""
    try:
        parts = urlsplit(url)
    except (ValueError, TypeError):
        return None
    if parts.scheme.lower() != "https":
        return None
    if parts.username is not None or parts.password is not None:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    if port not in (None, 443) or parts.netloc.endswith(":"):
        return None
    host = (parts.hostname or "").lower()
    if not host or host not in OFFICIAL_RESOURCE_HOSTS:
        return None
    return host


def _verified_wechat_identity(facts: _DocumentFacts) -> dict[str, str] | None:
    """读取公众号身份核验记录；只有人工核验过的账号才能作为 S4 来源。"""
    notes = facts.temporal_notes
    if not isinstance(notes, dict):
        return None
    nested = notes.get("wechat_verification") or notes.get("official_account")
    if isinstance(nested, dict):
        verified = nested.get("verified") is True
        name = str(nested.get("account_name") or "").strip()
        account_id = str(nested.get("account_id") or "").strip()
        basis = str(nested.get("basis") or "").strip()
    else:
        verified = notes.get("wechat_verified") is True
        name = str(notes.get("wechat_account_name") or "").strip()
        account_id = str(notes.get("wechat_account_id") or "").strip()
        basis = str(notes.get("wechat_verification_basis") or "").strip()
    if not verified or not name or not account_id or not basis:
        return None
    name_family = _wechat_family(name, is_id=False)
    id_family = _wechat_family(account_id, is_id=True)
    if name_family is None or id_family is None or name_family != id_family:
        # 名称与 ID 必须同属学院、学校或招生主体，不能只靠昵称放行。
        return None
    return {"name": name, "account_id": account_id}


def _official_resource_source(
    facts: _DocumentFacts, category: str | None, text: str
) -> bool:
    """官方来源判定：学院信息要求 ccds 直接页面；公众号必须单独核验身份。"""
    host = _official_url_host(facts.source_url or "")
    if host is not None:
        if category == RES_CONTACT and host != COLLEGE_RESOURCE_HOST:
            # 学院公开信息与联系方式只采用计算机学院官网直接公开页面。
            return False
        if category == RES_NOTICE:
            if host == "zsks.fzu.edu.cn" and not _ADMISSION_SCOPE.search(text):
                return False
            if host in {"news.fzu.edu.cn", "xcb.fzu.edu.cn"} and not re.search(
                r"学校|全校|校园|新闻|宣传", text
            ):
                return False
        return True
    try:
        parts = urlsplit(facts.source_url or "")
    except (ValueError, TypeError):
        return False
    if parts.scheme.lower() != "https" or (parts.hostname or "").lower() != WECHAT_ARTICLE_HOST:
        return False
    if parts.username is not None or parts.password is not None:
        return False
    try:
        port = parts.port
    except ValueError:
        return False
    if port not in (None, 443) or parts.netloc.endswith(":"):
        return False
    identity = _verified_wechat_identity(facts)
    if identity is None:
        return False
    if category == RES_CONTACT:
        # 学院联系方式只认学院自己的两个公众号，学校号/招生号不能代替。
        if identity["name"] not in COLLEGE_WECHAT_ACCOUNTS and identity["account_id"] not in COLLEGE_WECHAT_ACCOUNTS:
            return False
    if identity["account_id"] == "fzuzsks" or identity["name"] == "fzuzsks":
        if not _ADMISSION_SCOPE.search(text):
            return False
    if identity["account_id"] == "ifzu1958" or identity["name"] == "ifzu1958":
        if category == RES_CONTACT:
            return False
        if not re.search(r"学校|全校|校园|新闻|宣传", text):
            return False
    return True


def _check_resources(
    request: AgentRequest,
    text: str,
    facts: _DocumentFacts,
    chunk: RetrievedChunk,
    chunk_lookup: ChunkLookup | None,
    today: date,
    temporal_text: str,
) -> bool:
    # 准入先看正式业务方向代码；不能用标题里的“实验室”自行认作 S4 资料。
    if RESOURCE_DIRECTION_CODE not in set(facts.business_direction_codes):
        return False
    named_college = _EXTERNAL_COLLEGE.search(text)
    if named_college and "计算机" not in named_college.group() and "软件" not in named_college.group():
        # 资料只服务本学院；R4/R6 即使不强制 applicability，也不能回答外院。
        return False
    if not facts.source_url.strip():
        return False
    categories = _resource_categories(request.query or text)
    # 单轮省略主语的追问（“EDA 那个招几个”）回看历史后仍能定位类别。
    if not categories:
        categories = _resource_categories(text)
    kinds = _resource_document_kinds(facts, chunk)
    if not kinds:
        return False
    matched = categories & kinds if categories else kinds
    if not matched:
        # 问招募却拿历史介绍、问研究方向却拿报名通知，都属类别不匹配。
        return False
    # 来源规则按资料自身类别执行，不因同一问题里还有别的资源类别而放松。
    doc_kind = next(iter(kinds))
    teams = r3_team_names(request.query)
    if teams and doc_kind in {RES_LAB, RES_INTRO} and not teams.intersection(r3_team_names(chunk.content)):
        return False
    if not _official_resource_source(facts, doc_kind, text):
        return False
    requires_app = doc_kind in _RESOURCE_APPLICABILITY_REQUIRED
    if requires_app and not facts.applicability:
        return False
    if facts.applicability:
        allowed = _applicability(text, facts, today, strict=requires_app)
        if allowed is False:
            return False
    if doc_kind == RES_LAB:
        # R3 招募通知是年度资料：明确写了年份时必须与资料适用年度一致。
        doc_year = _document_year(facts)
        years = _query_years(temporal_text, today)
        if years and (doc_year is None or doc_year not in years):
            return False
        if _LAB_ADMISSION.search(current := request.query or text):
            expired = facts.deadline is not None and today > facts.deadline
            historical_notice = chunk.timeliness_verification_status in {
                TimelinessVerificationStatus.HISTORICAL, TimelinessVerificationStatus.EXPIRED,
                TimelinessVerificationStatus.SUPERSEDED,
            } or expired
            if historical_notice:
                if not years or _CURRENT_INTENT.search(temporal_text) or re.search(r"如今|当下|现阶段|仍然|仍可", temporal_text):
                    return False
                app = facts.applicability or {}
                if not (_first_value(app, _GRADE_KEYS) and _first_value(app, _MAJOR_KEYS)):
                    return False
                if _PERSONAL.search(current) and not (_grade_level(text, today) and _PROFESSION.search(text)):
                    return False
        # 过期通知可以回答“本年度已截止”和当时的计划人数，但不能回答当前名额。
        if _current_quota_question(temporal_text):
            if (
                chunk.timeliness_verification_status
                not in {TimelinessVerificationStatus.CURRENT}
                or (facts.deadline is not None and today > facts.deadline)
            ):
                return False
    timeliness = chunk.timeliness_verification_status
    if timeliness == TimelinessVerificationStatus.SUPERSEDED:
        # 被新版本替代的资源只能回答历史问题；历史消息不能把当前问题伪装成历史问句。
        return _historical_question(temporal_text)
    if (
        doc_kind in {RES_STUDY, RES_CONTACT}
        and timeliness in {
            TimelinessVerificationStatus.HISTORICAL,
            TimelinessVerificationStatus.EXPIRED,
        }
        and _current_question(temporal_text)
    ):
        # 旧培养方案、旧联系方式不能冒充现行版本；历史消息不能盖过本轮的当前时点。
        return False
    return True


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
            category_name=metadata.category_name,
            business_direction_codes=tuple(metadata.business_direction_codes),
            document_type=metadata.document_type,
            source_url=metadata.source_url,
            publisher=metadata.publisher,
            version_no=metadata.version_no,
            policy_status=metadata.policy_status,
            temporal_notes=(
                dict(metadata.temporal_notes)
                if isinstance(metadata.temporal_notes, dict)
                else None
            ),
            published_on=metadata.published_on,
            effective_on=metadata.effective_on,
        )
    return _DocumentFacts(
        record_code=None,
        title=chunk.title,
        applicability=None,
        deadline=None,
        has_metadata=False,
    )


def _human_approved(facts: _DocumentFacts) -> bool:
    """人工审核标记必须严格为布尔 true；字符串 "true" 不算通过。"""
    notes = facts.temporal_notes
    return isinstance(notes, dict) and notes.get("human_approved") is True


def _metadata_consistent(facts: _DocumentFacts, chunk: RetrievedChunk, today: date) -> bool:
    """文档版本与片段身份必须一致；任一冲突都视为无法确认。"""
    if not facts.title.strip() or facts.title != chunk.title:
        return False
    if not facts.source_url.strip() or facts.source_url != chunk.source_url:
        return False
    if facts.publisher != chunk.publisher:
        return False
    if facts.published_on != chunk.published_on:
        return False
    if facts.effective_on != chunk.effective_on:
        return False
    for value in (facts.published_on, facts.effective_on):
        if value is not None and value > today:
            return False
    return True


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


_REFERENCE_QUESTION = re.compile(r"准备|参考|提前|规划|了解|流程|时间线|什么时候|何时|大几|几年级")
# 正式资格、排名、遴选、能否申请等意图出现时，准备性关键词不再放行低年级。
_FORMAL_ELIGIBILITY = re.compile(
    r"资格|排名|遴选|能否申请|能不能申请|可否申请|申请条件|申请资格|名额|入选|推荐名单|够不够"
)
_AVAILABILITY_QUESTION = re.compile(r"还能|现在还|目前还|是否还|办理窗口|现在.*(申请|报名|提交)|今年.*(申请|报名)")
# 历史通知只拒绝“当前时点还能不能办”；“去年还能报名吗”“当时截止到哪天”属历史状态。
_CURRENT_AVAILABILITY = re.compile(
    r"(?:现在|目前|当前|如今|今天).{0,10}(?:还能|还|是否|可以|能|来得及|申请|报名|提交|办理)"
    r"|(?:今年|本学期|这学期).{0,10}(?:申请|报名|提交|办理|截止)"
)
_UNCERTAIN_POLICY = re.compile(
    r"无法确认(?:是否|现行)|现行版本(?:未确认|不明)|版本(?:不明|待定)|uncertain", re.I
)


def _historical_question(text: str) -> bool:
    return bool(_HISTORICAL_INTENT.search(text))


def _current_question(text: str) -> bool:
    return bool(_CURRENT_INTENT.search(text)) and not _historical_question(text)


def _current_quota_question(text: str) -> bool:
    """只有当前剩余名额口径才拒绝历史通知；计划人数可作历史信息回答。"""
    if _historical_question(text):
        return False
    return bool(_CURRENT_QUOTA.search(text))


def _relative_year(text: str, today: date) -> int | None:
    """识别“去年/前年”等相对年度；不把“今年”当成历史年度。"""
    if "前年" in text:
        return today.year - 2
    if "去年" in text:
        return today.year - 1
    return None


def _query_years(text: str, today: date) -> set[int]:
    """问题里的明确年度，含“今年/去年/前年”；相对年度不能盖过明确年份。"""
    years = _years(text)
    relative = _relative_year(text, today)
    if relative is not None:
        years.add(relative)
    if re.search(r"今年|本年", text):
        years.add(today.year)
    return years


def _historical_year_conflict(
    text: str, facts: _DocumentFacts, today: date
) -> bool:
    """历史资料必须能对上问题里的适用年度；未指定年度的旧政策不用于作答。"""
    doc_year = _document_year(facts)
    years = _years(text)
    if years:
        # 明确写了年份时，资料适用年度必须命中，不能拿别的年度顶替。
        return doc_year is None or doc_year not in years
    if doc_year is None:
        # 没有适用年度元数据，无法证明历史资料对应哪一年。
        return True
    # 未写年份时，只有本年度或未来周期的历史通知可按“本年度已截止”作答；
    # 更早年份的历史政策必须由用户明确指定年度或相对年度。
    if doc_year < today.year:
        relative = _relative_year(text, today)
        if relative is not None:
            return doc_year != relative
        return True
    return False


def _timeliness_conflict(
    text: str,
    facts: _DocumentFacts,
    today: date,
    timeliness: TimelinessVerificationStatus,
) -> bool:
    """历史资料可以回答历史问题，但不能冒充现行政策。"""
    if _UNCERTAIN_POLICY.search(facts.policy_status or ""):
        # 无法确认是否为现行版本时，任何确定性结论都不可用。
        return True
    if timeliness == TimelinessVerificationStatus.SUPERSEDED:
        # 已被新版本替代的资料只能回答历史问题，且年度必须对得上。
        return not _historical_question(text) or _historical_year_conflict(
            text, facts, today
        )
    if timeliness in {
        TimelinessVerificationStatus.HISTORICAL,
        TimelinessVerificationStatus.EXPIRED,
    }:
        # 问“现在/今年/最新”时，历史或过期资料不能作为现行依据。
        if _current_question(text):
            return True
        return _historical_year_conflict(text, facts, today)
    return False


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
    availability = bool(_AVAILABILITY_QUESTION.search(text))
    if timeliness in {
        TimelinessVerificationStatus.HISTORICAL,
        TimelinessVerificationStatus.EXPIRED,
    }:
        # 过期资料可以回答“当时/去年还能不能办、截止到哪天”，
        # 只有问当前时点还能不能办才拒绝，不能见“还能”就一律丢证据。
        return bool(_CURRENT_AVAILABILITY.search(text))
    return availability


_GRADE_KEYS = (
    "适用年级", "年级", "学生对象", "招生对象", "grade", "对象", "适用对象", "target",
)
_MAJOR_KEYS = ("适用专业", "专业", "招生专业", "major")
_TARGET_KEYS = ("适用对象", "对象", "学生对象", "招生对象", "target", "audience")
_COLLEGE_KEYS = ("学院", "适用学院", "所属学院", "college")
_CONFLICT_GROUPS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("适用年级", "年级"), "grade"),
    (("适用专业", "专业", "招生专业"), "major"),
    (("适用对象", "学生对象", "招生对象", "对象"), "target"),
    (("学院", "适用学院", "所属学院"), "college"),
    (("适用届别", "目标届别"), "cohort"),
)


def _applicability_conflict(app: dict[str, str]) -> bool:
    """同一含义的中文核心键与旧英文键不一致时，标记为需复核并拒绝使用。"""
    for keys, legacy in _CONFLICT_GROUPS:
        values = [str(app.get(key) or "").strip() for key in keys]
        values.append(str(app.get(legacy) or "").strip())
        distinct = {value for value in values if value}
        if len(distinct) > 1:
            return True
    return False


def _first_value(app: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = app.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _applicability(
    text: str, facts: _DocumentFacts, today: date, *, strict: bool = True
) -> bool | None:
    app = facts.applicability or {}
    if _applicability_conflict(app):
        return False
    # #31 实际元数据里年级/专业/对象分别落在 适用年级 / 学生对象 / 对象 / 学院 等键上。
    grade_text = _first_value(app, _GRADE_KEYS)
    major_text = _first_value(app, _MAJOR_KEYS)
    target_text = _first_value(app, _TARGET_KEYS)

    query_grade = _grade_level(text, today)
    query_major = _PROFESSION.search(text)
    allow_reference = (
        bool(_REFERENCE_QUESTION.search(text))
        and not _FORMAL_ELIGIBILITY.search(text)
    )
    unknown = False

    query_cohort = _enrolment_year(text)
    target_cohort = _cohort_year(app)
    if query_cohort and target_cohort and query_cohort + 4 != target_cohort:
        # 入学年份与目标届别对不上，说明这份年度方案不是该学生的届别。
        return False

    named = _EXTERNAL_COLLEGE.search(text)
    if named and "计算机" not in named.group() and "软件" not in named.group():
        # 资料只服务本学院；连学院字段都没有时，外院问题同样无法核实。
        return False

    if query_grade and grade_text:
        allowed = _grade_allowed(
            grade_text, query_grade, allow_reference=allow_reference
        )
        if allowed is False:
            return False
        unknown = unknown or allowed is None
    elif query_grade and not grade_text and strict:
        unknown = True

    if query_major and major_text:
        if not _major_allowed(major_text, query_major.group()):
            return False
    elif query_major and not major_text and strict:
        unknown = True

    if re.search(r"研究生|硕士(?!生源)|博士", text) and target_text:
        if "本科" in target_text and "研究生" not in target_text:
            return False
    if re.search(r"本科生|本科|大[一二三四]", text) and target_text:
        if "研究生" in target_text and "本科" not in target_text:
            return False

    if unknown:
        # 用户明确问了年级/专业，但资料没有对应适用范围：无法核实即不适用，
        # 不因为句子里没有“我”就放行。
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


def _grade_allowed(
    grade_text: str, grade: int, *, allow_reference: bool = False
) -> bool | None:
    """区分正式申请资格与仅作参考的说明。

    #31 的 2027 届方案写明“大一至大三仅升学准备参考”，低年级学生不能据此
    通过正式推荐资格的适用性检查；只有问准备、流程类问题时才按参考口径放行。
    """
    if re.search(r"全体|全部|全校|各年级|所有年级", grade_text):
        return True
    if re.fullmatch(r"本科生|本科|全体本科生|全体学生", grade_text.strip()):
        return True
    if "大一至大三" in grade_text:
        reference_only = bool(re.search(r"仅[^；;。]{0,12}参考|仅供参考", grade_text))
        if grade <= 3:
            return True if allow_reference or not reference_only else False
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
