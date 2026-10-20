"""Check assessment question bodies against the authoritative task template.

This checks task identity, never answer correctness. Titles and copied task
instructions are deliberately insufficient evidence of a match.
"""
import math
import re
import unicodedata
from collections import Counter

from journey_api.errors import ApiError


TASK_NAMES = {
    "ASM-002-MODEL-JUDGEMENT": "测评二／模型判断",
    "ASM-003-DATA-CONSTRUCTION": "测评三／数据构造",
}
QUESTION = re.compile(r"^\s*(?:第\s*\d+\s*题|题目\s*\d+)\s*[:：]", re.M)


def normalized(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", unicodedata.normalize("NFKC", text).casefold())


def ensure_task_questions(stage: str, body: str, references: list[dict]) -> None:
    if stage not in TASK_NAMES:
        return  # Other tasks still require the model's explicit alignment check.
    reference = next((item["body"] for item in references if item["label"] == "题目"), "")
    # Exclude the shared instructions before question 1. Shared lines such as
    # "write an explanation" cannot identify a particular question/task.
    sections = QUESTION.split(reference)[1:]
    if len(sections) < 2:
        raise ApiError(502, "AI_TASK_REFERENCE_UNVERIFIABLE", "当前测评题目无法完整核对，尚未进行自查，请联系管理员检查题目材料。")
    anchors = [{normalized(line) for line in section.splitlines()
                if 12 <= len(normalized(line)) <= 300} for section in sections]
    frequencies = Counter(anchor for group in anchors for anchor in group)
    content = normalized(body)
    matched = sum(any(frequencies[anchor] == 1 and anchor in content for anchor in group) for group in anchors)
    submitted_questions = len(QUESTION.findall(body))
    # A partial answer may be reviewed; a mostly unrelated/mixed template may
    # not qualify merely by including one question from the expected task.
    required = max(1, math.ceil(min(submitted_questions, len(sections)) * 0.6))
    if matched < required:
        name = TASK_NAMES[stage]
        raise ApiError(422, "AI_TASK_DOCUMENT_MISMATCH",
                       f"文档题干与当前任务「{name}」不匹配或无法确认。请使用当前任务题目创建答题副本，保留题干并填写答案后重新自查。尚未发表评论。")
