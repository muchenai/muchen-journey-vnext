"""Explicit local-only live probe. Does not create comments or use learner data."""
import json

from journey_api.ai_self_check_clients import AIReviewer, Document, FeishuDocuments
from journey_api.ai_self_check_rules import SYSTEM_PROMPT, evidence_for, render_feedback, ANSWER_URLS
from journey_api.config import get_settings
from journey_api.errors import ApiError


def main():
    settings = get_settings()
    if settings.app_env != "local":
        raise SystemExit("Local-only probe")
    results = {}
    try:
        document = Document("synthetic", "synthetic", "合成测试", "公司为客户提供数据服务。学习材料让我认识到需要按规则交付并主动提报问题。" * 8, "1")
        evidence = evidence_for("DAY-0", document, [
            {"label": "合成测试材料一", "body": "公司为客户提供数据服务。"},
            {"label": "合成测试材料二", "body": "新人按规则交付，遇到问题主动提报。"},
        ])
        feedback = render_feedback(AIReviewer(settings).review(SYSTEM_PROMPT, evidence), "DAY-0", document.body)
        results["ai"] = {"ok": True, "model": settings.ai_model, "feedback_characters": len(feedback)}
    except ApiError as exc:
        results["ai"] = {"ok": False, "code": exc.code, "message": exc.message}
    try:
        documents = FeishuDocuments(settings)
        reference = documents.read(documents.resolve(next(iter(ANSWER_URLS.values()))))
        results["feishu_read"] = {"ok": True, "characters": len(reference.body), "has_title_anchor": bool(reference.title_block_id)}
    except ApiError as exc:
        results["feishu_read"] = {"ok": False, "code": exc.code, "message": exc.message, "details": exc.details}
    results["comments_sent"] = 0
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
