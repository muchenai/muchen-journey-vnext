#!/usr/bin/env python3
"""Create a disposable, PII-free Journey V3 fixture on a loopback API only."""

from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
import sys
import uuid
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


STAGES = (
    ("DAY-0", "Day 0｜启程"),
    ("TRE-001-COMPANY-VALUES", "宝藏一｜公司价值"),
    ("TRE-002-AI-DATA-BASICS", "宝藏二｜AI 与数据基础"),
    ("TRE-003-PROJECT-AWARENESS", "宝藏三｜项目认知"),
    ("TRE-004-DELIVERY-FIT", "宝藏四｜交付边界"),
    ("ASM-001-RULE-BREAKDOWN", "评测一｜规则拆解"),
    ("ASM-002-MODEL-JUDGEMENT", "评测二｜模型判断"),
    ("ASM-003-DATA-CONSTRUCTION", "评测三｜数据构造"),
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
    material_url = (
        "https://example.feishu.cn/wiki/"
        f"P0LearnerExperienceMaterial{stable_key.replace('-', '')}"
        "?from=from_copylink&source=p0-2r2-real-length-layout-regression"
    )
    challenge_url = (
        "https://example.feishu.cn/docx/"
        f"P0LearnerChallenge{stable_key.replace('-', '')}"
        "?from=from_copylink&source=p0-2r2-real-length-layout-regression"
    )
    answer_url = (
        "https://example.feishu.cn/docx/"
        f"P0LearnerAnswer{stable_key.replace('-', '')}"
        "?from=from_copylink&source=p0-2r2-real-length-layout-regression"
    )
    requires_external_document = stable_key.startswith("ASM-")
    return {
        "expected_revision": revision,
        "title": title,
        "purpose": "验证新人可以先完成学习输入，再留下当前阶段的结构化证据并继续旅程。",
        "learner_outcome": "新人能够辨认当前位置、完成输入并提交一份与当前主题对应的证据。",
        "instructions": [
            f"先打开完整挑战题面并确认本阶段边界：{challenge_url}",
            "在飞书文档副本中写下判断、依据和下一步。" if requires_external_document else "写下判断、依据和下一步。",
        ],
        "completion_criteria": [
            "固定输入已完成，判断与证据可以对应",
            "提交后可以查看示例答案并完成自检",
        ],
        "required_deliverables": [
            "一份飞书文档链接" if requires_external_document else "一份不少于四十字的结构化记录"
        ],
        "content_source_notes": ["P0 浏览器隔离夹具；不得进入 staging 或 production。"],
        "change_summary": "建立一次性 Journey V3 浏览器黄金路径夹具。",
        "reviewer_calibration_note": "仅用于机器验证交互闭环，不代表真人 Reviewer 校准。",
        "allowed_attachment_types": [],
        "max_attachment_size_bytes": 0,
        "reference_materials": [f"参考答案：{answer_url}"],
        "learning_materials": [
            {
                "key": f"material-{stable_key.lower()}",
                "title": f"{title}学习输入",
                "kind": "HTTPS_LINK",
                "source_label": "P0 隔离浏览器夹具",
                "url": material_url,
                "estimated_duration_minutes": 1,
                "required": True,
            }
        ],
        "verified_material_urls": [material_url],
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


def create_invite(
    base_url: str,
    *,
    purpose: str,
    reviewer_id: str,
    journey_version_id: str,
) -> dict[str, object]:
    return request_json(
        base_url,
        "/api/v1/ops/invites",
        method="POST",
        payload={
            "purpose": purpose,
            "expires_in_hours": 1,
            "role": "LEARNER",
            "reviewer_id": reviewer_id,
            "journey_version_id": journey_version_id,
            "target_user_id": None,
        },
    )


def exchange_without_confirmation(base_url: str, token: str) -> None:
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    request = Request(
        f"{base_url}/api/v1/join/exchange",
        data=json.dumps({"token": token, "return_to": "/app"}).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(request, timeout=10) as response:
            result = json.load(response)["data"]
    except HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"fixture API failed while preparing pending invite: HTTP {error.code}: {message}"
        ) from error
    if result.get("status") != "PENDING_IDENTITY":
        raise RuntimeError("fixture pending invite did not stop before identity confirmation")


def create_reentry(base_url: str, learner_display_name: str) -> str:
    enrollments = request_json(base_url, "/api/v1/ops/enrollments")["items"]
    matches = [
        item
        for item in enrollments
        if item["learner_display_name"] == learner_display_name
        and item["status"] == "ACTIVE"
        and "create_learner_reentry" in item["allowed_commands"]
    ]
    if len(matches) != 1:
        raise RuntimeError(
            "fixture requires exactly one active learner enrollment eligible for reentry"
        )
    enrollment = matches[0]
    result = request_json(
        base_url,
        f"/api/v1/ops/enrollments/{enrollment['id']}/learner-reentry",
        method="POST",
        payload={
            "expected_revision": enrollment["revision"],
            "expires_in_minutes": 30,
            "reason": "P0 浏览器验证模拟浏览器中断后安全继续既有旅程",
        },
    )
    return str(result["invite_token"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--create-reentry", action="store_true")
    parser.add_argument("--learner-display-name", default="P0 Browser Learner")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("P0 browser fixture is restricted to a loopback HTTP API")
    base_url = args.base_url.rstrip("/")

    if args.create_reentry:
        sys.stdout.write(create_reentry(base_url, args.learner_display_name))
        return 0

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
    invite = create_invite(
        base_url,
        purpose="P0_BROWSER_PRIMARY",
        reviewer_id=reviewer_id,
        journey_version_id=journey["id"],
    )
    pending_invite = create_invite(
        base_url,
        purpose="P0_BROWSER_PENDING",
        reviewer_id=reviewer_id,
        journey_version_id=journey["id"],
    )
    create_invite(
        base_url,
        purpose="P0_BROWSER_UNUSED",
        reviewer_id=reviewer_id,
        journey_version_id=journey["id"],
    )
    exchange_without_confirmation(base_url, str(pending_invite["invite_token"]))
    sys.stdout.write(invite["invite_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
