from pathlib import Path

import pytest

from scripts import p0_journey_v3_browser_fixture as fixture


ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_fixture_covers_eight_distinct_https_material_links() -> None:
    urls = []
    for stable_key, title in fixture.STAGES:
        payload = fixture.task_payload(
            stable_key,
            title,
            1,
            "00000000-0000-0000-0000-000000000000",
        )
        expected_material_count = 2 if stable_key == "DAY-0" else 1
        assert len(payload["learning_materials"]) == expected_material_count
        material = payload["learning_materials"][0]
        assert material["kind"] == "HTTPS_LINK"
        assert material["url"].startswith("https://")
        assert payload["verified_material_urls"] == [
            item["url"] for item in payload["learning_materials"]
        ]
        urls.extend(payload["verified_material_urls"])

    assert len(urls) == 9
    assert len(set(urls)) == 9


def test_treasure_one_uses_the_real_newcomer_training_video() -> None:
    payload = fixture.task_payload(
        "TRE-001-COMPANY-VALUES",
        dict(fixture.STAGES)["TRE-001-COMPANY-VALUES"],
        1,
        "00000000-0000-0000-0000-000000000000",
    )

    assert payload["learning_materials"] == [
        {
            "key": "material-tre-001-company-values",
            "title": "沐晨AI新人培训视频",
            "kind": "HTTPS_LINK",
            "source_label": "P0 隔离浏览器夹具",
            "url": "https://zx6w57w0j34.feishu.cn/file/PewIbRCP3oDKAIx7MS9cSqUMnod",
            "estimated_duration_minutes": 1,
            "required": True,
        }
    ]
    assert payload["instructions"][0] == (
        "先打开完整挑战题面并确认本阶段边界："
        "https://zx6w57w0j34.feishu.cn/docx/N1CmdNwvtoF6ubxGGK6cztvnnpg"
    )


def test_reentry_helper_targets_one_existing_active_enrollment(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request(base_url, path, *, method="GET", payload=None):
        calls.append((path, method, payload))
        if path == "/api/v1/ops/enrollments":
            return {
                "items": [
                    {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "learner_display_name": "P0 Browser Learner",
                        "status": "ACTIVE",
                        "revision": 7,
                        "allowed_commands": ["create_learner_reentry"],
                    }
                ]
            }
        return {"invite_token": "r" * 48}

    monkeypatch.setattr(fixture, "request_json", fake_request)

    token = fixture.create_reentry("http://127.0.0.1:8000", "P0 Browser Learner")

    assert token == "r" * 48
    assert calls[1][0].endswith("/learner-reentry")
    assert calls[1][1] == "POST"
    assert calls[1][2]["expected_revision"] == 7


def test_reentry_helper_fails_closed_on_ambiguous_enrollment(monkeypatch) -> None:
    monkeypatch.setattr(
        fixture,
        "request_json",
        lambda *_args, **_kwargs: {
            "items": [
                {
                    "id": str(index),
                    "learner_display_name": "P0 Browser Learner",
                    "status": "ACTIVE",
                    "revision": 1,
                    "allowed_commands": ["create_learner_reentry"],
                }
                for index in range(2)
            ]
        },
    )

    with pytest.raises(RuntimeError, match="exactly one"):
        fixture.create_reentry("http://127.0.0.1:8000", "P0 Browser Learner")


def test_browser_result_cannot_be_misreported_as_real_journey_uat() -> None:
    script = (ROOT / "scripts/p0_journey_v3_browser.sh").read_text(encoding="utf-8")

    for required in (
        "invite_statuses=3",
        "reentry=new_browser",
        "old_session=revoked",
        "material_links=8",
        "completed_material_reopen=PASS",
        "ai_self_check_skip=PASS",
        "visible_task_brief=3_viewports",
        "evidence_retest=triple_click_one_post+version_2+explicit_retest_version_3",
        "post_completion_evidence_retest=result_preserved+ops_blocked+cancel_restored+version_2",
        "fixture=synthetic",
        "external_access=not_proven",
        "human_uat=not_run",
    ):
        assert required in script


def test_browser_gate_rejects_playwright_console_error_output() -> None:
    script = (ROOT / "scripts/p0_journey_v3_browser.sh").read_text(encoding="utf-8")

    assert "^Error:" in script
    assert "Errors: [1-9][0-9]*" in script


def test_evidence_retest_triple_click_emits_one_post_and_explicit_retry_is_new() -> None:
    script = (ROOT / "scripts/p0_journey_v3_browser.sh").read_text(encoding="utf-8")

    assert script.count("button.click();") >= 3
    assert "submissionPostCount !== 1" in script
    assert "submitted=retest&version=2" in script
    assert "submitted=retest&version=3" in script


def test_completed_journey_browser_flow_preserves_result_and_restores_completion() -> None:
    script = (ROOT / "scripts/p0_journey_v3_browser.sh").read_text(encoding="utf-8")

    assert "一项自证站正在重新测试" in script
    assert "当前结果基于上一次完整完成记录" in script
    assert "本轮结束前暂停 Enrollment 运营命令" in script
    assert "确认取消并丢弃草稿" in script
    assert "07-post-completion-retest-restored.png" in script
