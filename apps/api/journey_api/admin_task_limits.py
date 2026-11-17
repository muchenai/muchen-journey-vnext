"""Text limits for task configuration in the Review administration UI."""

from journey_api.errors import ApiError


ADMIN_TASK_TITLE_LIMIT = 60
ADMIN_TASK_SUMMARY_LIMIT = 400
_TEXT_LIMITS = {
    "title": (ADMIN_TASK_TITLE_LIMIT, "任务标题"),
    "summary": (ADMIN_TASK_SUMMARY_LIMIT, "任务简述"),
}


def validate_admin_task_text(field: str, value: object) -> object:
    """Match JavaScript string.length, including spaces and surrogate pairs."""
    limit, label = _TEXT_LIMITS[field]
    if isinstance(value, str) and len(value.encode("utf-16-le", errors="surrogatepass")) // 2 > limit:
        raise ApiError(422, "VALIDATION_FAILED", f"{label}不能超过 {limit} 字")
    return value
