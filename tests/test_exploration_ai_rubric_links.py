"""Imported Feishu answer keys stay private and fixed through real HTTP grading.

All documents and model responses are in-process fakes. The ``exploration``
fixture owns an isolated test organization; these tests never read real Feishu
documents, send comments, or change the interactive learner's progress.
"""
import base64
from dataclasses import replace
import json
import uuid

import pytest
from sqlalchemy import select

from journey_api.ai_self_check_clients import document_ref
from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Evaluation,
    Review,
    Submission,
    SubmissionVersion,
)
from journey_api.review_admin_models import PublishedTaskContent
from test_dynamic_exploration import command, exploration, post, publish, read
from test_dynamic_exploration_ai import ai, check, history
from test_exploration_ai_publisher_contract import (
    additional_learner,
    assert_ai_completion,
    assert_uncompleted,
)
from test_exploration_sequence import republish
from test_wp09_feishu_identity import assert_ok


SOURCE_LINK = "https://answers.feishu.cn/wiki/ReferenceAlias1234?from=copy"
SOURCE_TOKEN = "CourseReferenceDocument1234"
SOURCE_TITLE = "仅供发布人员查看的选择题标准答案"
OLD_STANDARD = "私有选择题答案：第1题选B，第2题选AD。每题50分，多选漏选按评分说明扣分。"
NEW_STANDARD = "新版私有选择题答案：第1题选C，第2题选BC。每题50分，按新版题号逐项核对。"
RUBRIC = [
    dict(
        id="answer-correctness",
        name="答案正确性",
        points=100,
        description="按附加的标准答案核对每道选择题，依据文档中的每题分值计分。",
    )
]


def import_answer_key(exploration, ai, monkeypatch, body, revision="7"):
    """Import the actual body returned by the existing fake document reader."""
    staff, _, _ = exploration
    documents, _ = ai
    documents.body, documents.revision = body, revision

    # Bind the fixture class's original method rather than a previously patched
    # instance method, so importing v2 cannot recursively wrap v1's reader.
    original_read = type(documents).read

    def source_read(token):
        document = original_read(documents, token)
        return replace(document, title=SOURCE_TITLE) if token == SOURCE_TOKEN else document

    monkeypatch.setattr(documents, "read", source_read)
    imported = assert_ok(
        post(
            staff,
            "review-admin/rubric-documents/import",
            dict(url=SOURCE_LINK, camp="exploration", difficulty=""),
        )
    )["material"]
    assert imported["type"] == "file" and imported["mime"] == "text/plain"
    assert imported["name"].endswith(".txt")
    assert imported["url"].startswith("data:text/plain;base64,")
    decoded = base64.b64decode(imported["url"].split(",", 1)[1], validate=True)
    assert decoded == body.encode("utf-8") and imported["size"] == len(decoded)
    assert document_ref(imported["sourceUrl"]) == ("docx", SOURCE_TOKEN)
    assert "?" not in imported["sourceUrl"] and "#" not in imported["sourceUrl"]
    assert imported["sourceRevision"] == revision
    assert imported["sourceTitle"] == SOURCE_TITLE
    return imported


def assert_private_learner_view(learner, task_id, standard, source_url):
    detail = read(learner, task_id)
    listing = assert_ok(learner[0].get("/api/v1/me/exploration"))
    for visible in (detail, listing):
        serialized = json.dumps(visible, ensure_ascii=False)
        for private in (
            standard,
            source_url,
            SOURCE_TITLE,
            "rubricAttachments",
            "aiRubricSnapshot",
            "sourceUrl",
            "sourceTitle",
            "sourceRevision",
            "data:text/plain;base64,",
        ):
            assert private not in serialized
    denied = learner[0].get(
        "/api/v1/me/exploration",
        params=dict(command="material", taskId=task_id, group="rubric", index=0),
    )
    assert denied.status_code == 422
    assert standard not in denied.text and source_url not in denied.text
    return detail


def test_imported_answer_key_scores_from_private_frozen_body_and_completes_at_pass_line(
    exploration, ai, monkeypatch
):
    documents, reviewer = ai
    _, learner, _ = exploration
    imported = import_answer_key(exploration, ai, monkeypatch, OLD_STANDARD)
    assert documents.reads == [SOURCE_TOKEN]
    task_id, live, content = publish(
        exploration,
        "assessment",
        reviewMode="ai",
        passScore=80,
        rubric=RUBRIC,
        rubricAttachments=[imported],
    )
    assert live["rubricAttachments"][0]["sourceUrl"] == imported["sourceUrl"]
    assert live["rubricAttachments"][0]["sourceRevision"] == "7"
    available = assert_private_learner_view(
        learner, task_id, OLD_STANDARD, imported["sourceUrl"]
    )
    task = assert_ok(command(learner, available, "claim"))

    # A later source edit or loss of document access must not change the
    # publisher's already imported standards, or make text grading unavailable.
    documents.body, documents.revision = "源文档已被修改，此文本不属于发布版本。", "8"
    documents.read_error = ApiError(
        502, "FEISHU_DOCUMENT_ACCESS", "导入后，源文档已不再允许读取。"
    )
    reviewer.score_factor = .79
    below = assert_ok(check(learner, task, "第1题：B。第2题：A。"))
    assert below["record"]["score"] == 79
    assert_uncompleted(below["task"], below["record"])
    reviewer.score_factor = .8
    passed = assert_ok(check(learner, below["task"], "第1题：B。第2题：AD。"))
    assert passed["record"]["score"] == 80
    assert_ai_completion(passed["task"], passed["record"], content, 80)
    assert [entry["score"] for entry in history(learner, task)] == [80, 79]
    assert documents.reads == [SOURCE_TOKEN]
    assert not documents.comments and not documents.updates
    assert len(reviewer.calls) == 2
    for evidence in reviewer.calls:
        policy = evidence["grading_policy"]
        assert policy["pass_score"] == 80
        assert policy["dimensions"] == RUBRIC
        assert [item["body"] for item in policy["reference_documents"]] == [OLD_STANDARD]
        assert evidence["reference_documents"] == []
        serialized = json.dumps(evidence, ensure_ascii=False)
        assert "data:" not in serialized and "base64" not in serialized
        assert "源文档已被修改" not in serialized
    with SessionLocal() as session:
        published = session.get(PublishedTaskContent, uuid.UUID(live["versionId"]))
        assert published.content["rubricAttachments"][0]["sourceRevision"] == "7"
        assert published.content["aiRubricSnapshot"]["reference_documents"][0]["body"] == OLD_STANDARD
        assert session.scalar(
            select(Review.id).where(
                Review.assignment_id == uuid.UUID(task["assignmentId"])
            )
        ) is None


@pytest.mark.parametrize("alias", [False, True], ids=["canonical-docx", "wiki-alias"])
def test_imported_answer_source_or_its_wiki_alias_cannot_be_submitted_or_commented(
    exploration, ai, monkeypatch, alias
):
    documents, reviewer = ai
    _, learner, _ = exploration
    imported = import_answer_key(exploration, ai, monkeypatch, OLD_STANDARD)
    task_id, _, _ = publish(
        exploration,
        "assessment",
        reviewMode="ai",
        passScore=80,
        rubric=RUBRIC,
        rubricAttachments=[imported],
    )
    task = assert_ok(command(learner, read(learner, task_id), "claim"))
    answer_url = SOURCE_LINK if alias else imported["sourceUrl"]
    result = assert_ok(check(learner, task, "我的答题文档：" + answer_url))
    assert result["record"]["status"] == "FAILED"
    assert "自己的答题文档" in result["record"]["errorMessage"]
    assert result["record"]["commentStatus"] == "FAILED"
    assert result["record"]["taskCompleted"] is False
    assert result["task"]["status"] == "active"
    assert not reviewer.calls
    assert not documents.comments and not documents.updates and not documents.mentions
    assert documents.reads == [SOURCE_TOKEN], "The rejected answer must not read the private answer key again"
    assert len(history(learner, task)) == 1


def test_reimported_v2_answer_key_never_changes_an_existing_learners_scoring_version(
    exploration, ai, monkeypatch
):
    documents, reviewer = ai
    _, original_learner, _ = exploration
    old_import = import_answer_key(exploration, ai, monkeypatch, OLD_STANDARD, "7")
    task_id, old_live, old_content = publish(
        exploration,
        "assessment",
        reviewMode="ai",
        passScore=80,
        rubric=RUBRIC,
        rubricAttachments=[old_import],
    )
    old_task = assert_ok(command(original_learner, read(original_learner, task_id), "claim"))
    new_import = import_answer_key(exploration, ai, monkeypatch, NEW_STANDARD, "8")
    new_live, new_content = republish(
        exploration,
        task_id,
        old_live,
        old_content,
        rubricAttachments=[new_import],
    )
    newcomer = additional_learner(exploration)
    new_task = assert_ok(command(newcomer, read(newcomer, task_id), "claim"))
    assert old_task["versionId"] == old_live["versionId"]
    assert new_task["versionId"] == new_live["versionId"] != old_task["versionId"]
    assert read(original_learner, task_id)["versionId"] == old_task["versionId"]
    assert documents.reads == [SOURCE_TOKEN, SOURCE_TOKEN]

    documents.read_error = ApiError(
        502, "FEISHU_DOCUMENT_ACCESS", "后续评分只能读取对应发布版本中的标准答案快照。"
    )
    reviewer.score_factor = .8
    for learner, task, content, standard, revision in (
        (original_learner, old_task, old_content, OLD_STANDARD, "7"),
        (newcomer, new_task, new_content, NEW_STANDARD, "8"),
    ):
        assert_private_learner_view(learner, task_id, standard, new_import["sourceUrl"])
        result = assert_ok(check(learner, task, "第1题选择B，第2题选择AD，已逐题核对本任务要求。"))
        assert_ai_completion(result["task"], result["record"], content, 80)
        policy = reviewer.calls[-1]["grading_policy"]
        assert [item["body"] for item in policy["reference_documents"]] == [standard]
        with SessionLocal() as session:
            published = session.get(PublishedTaskContent, uuid.UUID(task["versionId"]))
            assert published.content["rubricAttachments"][0]["sourceRevision"] == revision
    assert documents.reads == [SOURCE_TOKEN, SOURCE_TOKEN]
    assert len(reviewer.calls) == 2
    assert not documents.comments and not documents.updates


def test_answer_link_without_custom_dimensions_publishes_and_completes_from_frozen_standard(
    exploration, ai, monkeypatch
):
    documents, reviewer = ai
    _, learner, _ = exploration
    imported = import_answer_key(exploration, ai, monkeypatch, OLD_STANDARD, "7")
    task_id, live, content = publish(
        exploration,
        "assessment",
        reviewMode="ai",
        passScore=60,
        rubric=[],
        rubricAttachments=[imported],
    )
    assert live["rubric"] == []
    available = assert_private_learner_view(
        learner, task_id, OLD_STANDARD, imported["sourceUrl"]
    )
    assert [
        (row["id"], row["name"], row["points"])
        for row in available["rubric"]
    ] == [("answer-document", "标准答案评分", 100)]
    assert all(not row.get("description") for row in available["rubric"])
    task = assert_ok(command(learner, available, "claim"))

    # The publisher can replace the source and raise the passing line without
    # changing the imported answers or policy of the learner's claimed v1.
    replacement = import_answer_key(
        exploration, ai, monkeypatch, NEW_STANDARD, "8"
    )
    new_live, _ = republish(
        exploration,
        task_id,
        live,
        content,
        passScore=80,
        rubricAttachments=[replacement],
    )
    assert new_live["rubric"] == []
    assert new_live["versionId"] != task["versionId"]
    pinned = assert_private_learner_view(
        learner, task_id, OLD_STANDARD, imported["sourceUrl"]
    )
    assert pinned["versionId"] == task["versionId"] and pinned["passScore"] == 60
    assert NEW_STANDARD not in json.dumps(pinned, ensure_ascii=False)

    documents.body, documents.revision = "源文档已更新，不应替换已领取版本。", "9"
    documents.read_error = ApiError(
        502, "FEISHU_DOCUMENT_ACCESS", "评分必须使用已发布版本中的标准答案。"
    )
    reviewer.score_factor = .59
    below = assert_ok(check(learner, task, "第1题选择B，第2题选择A。"))
    assert below["record"]["score"] == 59
    assert below["record"]["dimensions"][0]["id"] == "answer-document"
    assert_uncompleted(below["task"], below["record"])

    reviewer.score_factor = .6
    passed = assert_ok(check(learner, below["task"], "第1题选择B，第2题选择AD。"))
    record, completed = passed["record"], passed["task"]
    assert record["score"] == 60
    assert record["passed"] is True and record["taskCompleted"] is True
    assert completed["status"] == "completed"
    assert completed["feedback"]["source"] == "AI"
    assert completed["feedback"]["score"] == 60
    assert [row["source"] for row in completed["submissionHistory"]] == ["AI"]
    assert [row["score"] for row in history(learner, task)] == [60, 59]
    assert documents.reads == [SOURCE_TOKEN, SOURCE_TOKEN]
    assert not documents.comments and not documents.updates
    assert len(reviewer.calls) == 2

    with SessionLocal() as session:
        published = session.get(PublishedTaskContent, uuid.UUID(task["versionId"]))
        newer = session.get(PublishedTaskContent, uuid.UUID(new_live["versionId"]))
        for version, standard, revision in (
            (published, OLD_STANDARD, "7"),
            (newer, NEW_STANDARD, "8"),
        ):
            assert version.content["rubric"] == []
            assert version.content["rubricAttachments"][0]["sourceRevision"] == revision
            policy = version.content["aiRubricSnapshot"]
            assert [
                (row["id"], row["name"], row["points"])
                for row in policy["dimensions"]
            ] == [("answer-document", "标准答案评分", 100)]
            assert [row["body"] for row in policy["reference_documents"]] == [standard]
        old_policy = published.content["aiRubricSnapshot"]
        for evidence in reviewer.calls:
            assert evidence["grading_policy"] == old_policy
            assert evidence["reference_documents"] == []
            assert NEW_STANDARD not in json.dumps(evidence, ensure_ascii=False)
        assignment = session.get(Assignment, uuid.UUID(task["assignmentId"]))
        assert assignment.status == AssignmentStatus.COMPLETED
        assert str(assignment.task_version_id) == task["versionId"]
        submission = session.scalar(
            select(Submission).where(Submission.assignment_id == assignment.id)
        )
        versions = list(
            session.scalars(
                select(SubmissionVersion).where(
                    SubmissionVersion.submission_id == submission.id
                )
            )
        )
        assert submission.current_version_no == 1 and len(versions) == 1
        proof = versions[0].ai_use["exploration_ai_evaluation"]
        assert proof["taskVersionId"] == task["versionId"]
        assert proof["score"] == 60
        assert proof["rubricHash"] == old_policy["canonical_hash"]
        assert [row["id"] for row in proof["dimensions"]] == ["answer-document"]
        for model in (Review, Evaluation):
            assert session.scalar(
                select(model.id).where(model.assignment_id == assignment.id)
            ) is None


@pytest.mark.parametrize(
    "rubric,with_document",
    [
        pytest.param([], False, id="no-dimensions-and-no-answer-document"),
        pytest.param(
            [dict(id="unfinished", name="", points=0, description="")],
            True,
            id="blank-custom-row-does-not-fall-back",
        ),
        pytest.param(
            [dict(id="unfinished", name="选项正确性", points=100, description="")],
            True,
            id="missing-custom-description-does-not-fall-back",
        ),
        pytest.param(
            [dict(id="partial", name="选项正确性", points=50, description="按答案核对。")],
            True,
            id="custom-total-below-100-does-not-fall-back",
        ),
    ],
)
def test_document_only_scoring_does_not_bypass_missing_or_incomplete_standards(
    exploration, ai, monkeypatch, rubric, with_document
):
    staff, _, _ = exploration
    documents, reviewer = ai
    imported = (
        [import_answer_key(exploration, ai, monkeypatch, OLD_STANDARD)]
        if with_document else []
    )
    task_id = str(uuid.uuid4())
    content = dict(
        title="不得绕过未完成的评分标准",
        summary="发布前必须有可读取的标准答案，或完整有效的评分维度。",
        camp="exploration",
        order=9999,
        completionMode="assessment",
        domain="",
        difficulty="",
        badges=[],
        materials=[
            dict(
                id="learning",
                name="课程学习材料",
                type="link",
                url="https://example.com/learning",
            )
        ],
        assessmentUrl="https://example.com/test",
        reviewMode="ai",
        passScore=60,
        rubric=rubric,
        rubricAttachments=imported,
    )
    draft = assert_ok(
        staff[0].put(
            "/api/v1/review-admin/tasks/" + task_id,
            headers={"X-CSRF-Token": staff[1]},
            json=dict(id=task_id, expected_revision=0, content=content),
        )
    )
    assert draft["rubric"] == rubric
    rejected = post(
        staff,
        "review-admin/tasks/" + task_id + "/publish",
        dict(
            expected_revision=draft["revision"],
            verified_material_urls=[
                "https://example.com/learning",
                "https://example.com/test",
            ],
        ),
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "AI_RUBRIC_INVALID"
    assert not reviewer.calls and not documents.comments and not documents.updates
    assert documents.reads == ([SOURCE_TOKEN] if with_document else [])
