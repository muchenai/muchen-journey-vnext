"""Read saved advice only for documents in the review's fixed submission.

No external requests, inference, comments or task mutations on a review read.
"""
import re

from sqlalchemy import select

from journey_api.ai_self_check_clients import document_ref
from journey_api.errors import ApiError
from journey_api.models import AISelfCheck
from journey_api.schemas import ReviewDocumentAiCheckOut


def submission_documents(body: str) -> list[tuple[str, tuple[str, str]]]:
    links = []
    seen = set()
    for match in re.finditer(r'https://[^\s<>"\[\]]+', body):
        url = match.group().rstrip('),.;!?，。；！？、）】》')
        try:
            reference = document_ref(url)
        except ApiError:
            continue
        if reference not in seen:
            seen.add(reference)
            links.append((url.split('?', 1)[0].split('#', 1)[0], reference))
    return links


def review_document_ai_checks(session, context) -> list[ReviewDocumentAiCheckOut]:
    links = submission_documents(context.version.body)
    if not links:
        return []
    records = session.scalars(select(AISelfCheck).where(
        AISelfCheck.organization_id == context.review.organization_id,
        AISelfCheck.assignment_id == context.assignment.id,
        AISelfCheck.learner_id == context.enrollment.learner_id,
    )).all()
    by_reference = {}
    for row in records:
        by_reference[("docx", row.document_token)] = row
        try:
            by_reference[document_ref(row.document_url)] = row
        except ApiError:
            pass
    results = []
    for url, reference in links:
        row = by_reference.get(reference)
        if row is None:
            results.append(ReviewDocumentAiCheckOut(document_url=url, status="NOT_FOUND"))
            continue
        completed = row.status == "COMPLETED"
        results.append(ReviewDocumentAiCheckOut(
            document_url=url, status=row.status, record_id=row.id,
            result=row.result if completed else None,
            generated_at=row.updated_at if completed else None,
            model=row.model, document_revision=row.document_revision or None,
            comment_id=row.comment_id if completed else None,
            history=[ReviewDocumentAiCheckOut(
                document_url=entry["body"], status="COMPLETED", record_id=entry["id"],
                result=entry["result"], generated_at=entry["generatedAt"], model=entry["model"],
                document_revision=entry.get("documentRevision") or None, comment_id=entry.get("commentId"),
            ) for entry in reversed(row.archived_results or [])],
        ))
    return results
