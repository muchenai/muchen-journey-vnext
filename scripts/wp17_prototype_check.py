#!/usr/bin/env python3
"""Fail-closed contract checks for the static WP-17 Learner prototype."""

from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototypes" / "wp17" / "index.html"
DOC = ROOT / "docs" / "33_WP17_LEARNER_EXPERIENCE_PROTOTYPE.md"


class PrototypeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.views: set[str] = set()
        self.result_states: set[str] = set()
        self.buttons = 0
        self.paragraphs = 0
        self.route_points = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        values = dict(attrs)
        if tag == "section" and values.get("data-panel"):
            self.views.add(values["data-panel"] or "")
        if values.get("data-result-panel"):
            self.result_states.add(values["data-result-panel"] or "")
        if tag == "button":
            self.buttons += 1
        if tag == "p":
            self.paragraphs += 1
        if "route-point" in (values.get("class") or "").split():
            self.route_points += 1
            require(bool(values.get("aria-label")), "route points need accessible names")
            require(bool(values.get("aria-describedby")), "route points need tooltip relationships")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"WP-17 prototype contract failed: {message}")


def main() -> None:
    html = PROTOTYPE.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")
    parser = PrototypeParser()
    parser.feed(html)

    require(parser.views == {"entry", "task", "result"}, "three prototype views are required")
    require(parser.result_states == {"pass", "revise"}, "pass and revise result states are required")
    require(parser.buttons >= 8, "prototype interactions must use semantic buttons")
    require("prefers-reduced-motion" in html, "reduced-motion support is required")
    require("旅程" in html and "当前任务" in html and "里程碑" in html and "反馈" in html and "完成" in html, "narrative stages are incomplete")
    require(parser.paragraphs <= 8, "prototype relies on too many explanatory paragraphs")
    require(parser.route_points == 3, "the route must expose exactly three progressive-disclosure points")
    require('class="route-point feedback"' not in html, "route points must not reuse result-card feedback styles")
    require("接下来约 60 分钟" not in html and "你只需关注" not in html, "redundant explanatory copy returned")
    require("revise: ['done', 'done', 'current', '']" in html, "revision must remain visually incomplete")
    require("/review" not in html and "/ops" not in html, "professional tools must not be included in the Learner prototype")
    require("PROTOTYPE_READY_FOR_REVIEW" in doc, "document must not claim implementation or deployment")
    require("/review" in doc and "/ops" in doc, "document must preserve professional-tool exclusions")
    require("不得一次性重写全部路由" in doc, "single-WIP implementation boundary is missing")

    print("WP-17 prototype contract: PASS")
    print(f"views={','.join(sorted(parser.views))}; results={','.join(sorted(parser.result_states))}; buttons={parser.buttons}")


if __name__ == "__main__":
    main()
