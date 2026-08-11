#!/usr/bin/env python3
"""Create a disposable, PII-free Journey V3 fixture on a loopback API only."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


STAGES = (
    ("DAY-0", "启程"),
    ("TRE-001-COMPANY-VALUES", "公司价值"),
    ("TRE-002-AI-DATA-BASICS", "AI 与模型"),
    ("TRE-003-PROJECT-AWARENESS", "项目认知"),
    ("TRE-004-DELIVERY-FIT", "交付边界"),
    ("ASM-001-RULE-BREAKDOWN", "规则拆解"),
    ("ASM-002-MODEL-JUDGEMENT", "模型判断"),
    ("ASM-003-DATA-CONSTRUCTION", "数据构造"),
)


def request_json(base_url: str, path: str, *, method: str = "GET", payload=None):
    headers = {"Accept": "application/json", "X-Fixture-Role": "OPERATOR"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Idempotency-Key"] = str(uuid.uuid4())
    try:
        with urlopen(
            Request(f"{base_url}{path}", data=body, headers=headers, method=method),
            timeout=10,
        ) as response:
            return json.load(response)["data"]
    except HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"fixture API failed at {path}: HTTP {error.code}: {message}") from error


def task_payload(stable_key: str, title: str, revision: int, reviewer_id: str):
    material_body = (
        "浏览器黄金路径材料。请打开 https://example.com/journey-v3-learning，"
        "然后返回当前页面完成材料。"
        if stable_key == "DAY-0"
        else "浏览器黄金路径使用的隔离合成材料；它不包含公司事实、用户信息或正式评价结论。"
    )
    return {
        "expected_revision": revision,
        "title": f"{title} · P0 浏览器验证",
        "purpose": "验证新人可以先完成学习输入，再留下当前阶段的结构化证据并继续旅程。",
        "learner_outcome": "新人能够辨认当前位置、完成输入并提交一份与当前主题对应的证据。",
        "instructions": ["先完成固定学习材料。", "写下判断、依据和下一步。"],
        "completion_criteria": ["固定输入已完成", "判断与证据可以对应"],
        "required_deliverables": ["一份不少于四十字的结构化记录"],
        "content_source_notes": ["P0 浏览器隔离夹具；不得进入 staging 或 production。"],
        "change_summary": "建立一次性 Journey V3 浏览器黄金路径夹具。",
        "reviewer_calibration_note": "仅用于机器验证交互闭环，不代表真人 Reviewer 校准。",
        "allowed_attachment_types": [],
        "max_attachment_size_bytes": 0,
        "reference_materials": [],
        "learning_materials": [
            {
                "key": f"material-{stable_key.lower()}",
                "title": f"{title}学习输入",
                "kind": "TEXT",
                "source_label": "P0 隔离浏览器夹具",
                "body": material_body,
                "estimated_duration_minutes": 1,
                "required": True,
            }
        ],
        "estimated_duration_minutes": 5,
        "rubric": {
            "version": 1,
            "dimensions": [
                {
                    "dimension_key": "evidence_traceability",
                    "title": "证据可定位",
                    "purpose": "确认判断来自当前题面与材料。",
                    "evidence_expected": "一处可以定位的判断依据。",
                    "levels": {"MEETS": "证据与判断对应", "NEEDS_WORK": "判断缺少证据"},
                    "required": True,
                    "feedback_prompt": "指出缺口与下一步修改。",
                    "blocking_rule": "REQUIRE_FEEDBACK",
                }
            ],
        },
        "reviewer_role": "REVIEWER",
        "feedback_sla_business_days": 2,
        "sensitivity": "INTERNAL",
        "audience": "LEARNER",
        "reviewed_by": reviewer_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("P0 browser fixture is restricted to a loopback HTTP API")
    base_url = args.base_url.rstrip("/")

    identity_items = request_json(base_url, "/api/v1/ops/identity-access")["items"]
    reviewer_id = next(item["user_id"] for item in identity_items if item["role"] == "REVIEWER")
    current = request_json(
        base_url,
        "/api/v1/ops/formal-journeys/publish",
        method="POST",
        payload={
            "reviewed_by": reviewer_id,
            "catalog_version": 2,
            "expected_current_version": 0,
            "expected_absent": True,
            "review_acknowledged": True,
        },
    )
    definitions = request_json(base_url, "/api/v1/ops/task-definitions")["items"]
    by_key = {item["stable_key"]: item for item in definitions}
    task_version_ids = []
    for stable_key, title in STAGES:
        definition = by_key[stable_key]
        published = request_json(
            base_url,
            f"/api/v1/ops/task-definitions/{definition['id']}/publish",
            method="POST",
            payload=task_payload(stable_key, title, definition["revision"], reviewer_id),
        )
        task_version_ids.append(published["id"])
    journey = request_json(
        base_url,
        "/api/v1/ops/formal-journeys/assemble-v3",
        method="POST",
        payload={
            "reviewed_by": reviewer_id,
            "expected_current_version": current["version"],
            "task_version_ids": task_version_ids,
            "content_review_note": "P0 隔离浏览器夹具已核对八站顺序、输入门禁和固定版本绑定。",
            "review_acknowledged": True,
        },
    )
    invite = request_json(
        base_url,
        "/api/v1/ops/invites",
        method="POST",
        payload={
            "purpose": "完成 P0 Journey V3 隔离浏览器黄金路径",
            "expires_in_hours": 1,
            "role": "LEARNER",
            "reviewer_id": reviewer_id,
            "journey_version_id": journey["id"],
            "target_user_id": None,
        },
    )
    sys.stdout.write(invite["invite_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
