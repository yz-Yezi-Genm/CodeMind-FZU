"""R3 team names confirmed from #41 for question routing."""

import re


# Catalog names identify a subject. The evidence gate checks approval separately.
_TEAM_NAME = re.compile(
    r"(?:(?<!\w)|(?<=[年届的那和与])|(?<=请问)|(?<=想问)|(?<=请问一下)|(?<=想问一下)|"
    r"(?<=关于)|(?<=加入)|(?<=了解)|(?<=换成))"
    r"(福州大学超算团队|ROIS\s*团队)"
    r"(?=$|[^\w]|的|怎么|如何|还|报名|招|接收|加入|研究|方向|做什么|简介|成果|"
    r"现在|目前|当前|剩余|计划|是否|能否|能报名|能加入|可以|今年|去年|截止|需|须|面向|拟|呢|吗|么)",
    re.IGNORECASE,
)


def r3_team_names(text: str) -> set[str]:
    """Return the verified names in the text, ignoring case and spacing."""
    return {re.sub(r"\s+", "", match[1]).casefold() for match in _TEAM_NAME.finditer(text)}


def without_r3_team_names(text: str) -> str:
    return _TEAM_NAME.sub("", text)
