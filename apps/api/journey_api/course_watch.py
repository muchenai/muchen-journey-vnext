"""Only credit playback time supported by server timestamps and the active session."""

import math
import uuid
from copy import deepcopy

from journey_api.academy_routes import fail, now
from journey_api.course_learning import settle, study_record
from journey_api.course_workspace_models import CourseStudyRecord


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def watch(session, actor, row, material_id, revision, command):
    if row.live["learningRevision"] != revision:
        fail("课程内容已更新，请重新打开。", 409)
    media = next((m for m in row.live["materials"] if m["id"] == material_id and m["kind"] == "video"), None)
    if not media:
        fail("视频材料不存在。", 404)
    duration = media["durationSeconds"]
    record = (
        session.get(CourseStudyRecord, (row.id, actor.id, revision))
        if command is None
        else study_record(session, actor, row)
    )
    state = deepcopy(record.state) if record else {"watches": {}}
    entry = state["watches"].get(
        material_id,
        dict(
            durationSeconds=duration,
            watchedSeconds=0,
            positionSeconds=0,
            completed=False,
            updatedAt=None,
            session=None,
        ),
    )
    if command is None:
        return {k: v for k, v in entry.items() if k != "session"}
    position, action = command.get("position"), command.get("action")
    if not finite(position) or not 0 <= position <= duration + 1:
        fail("播放位置无效。")
    at = min(position, duration)
    stamp = now()
    clock = stamp.timestamp()
    if action == "start":
        reported = command.get("duration")
        if not finite(reported) or abs(reported - duration) > 1:
            fail("视频时长发生变化，请联系管理员。", 409)
        if at > entry["watchedSeconds"] + 0.15:
            fail("只能从已学过的位置播放。", 409)
        entry["session"] = dict(
            id=str(uuid.uuid4()), last=clock, start=clock, frontier=entry["watchedSeconds"], position=at
        )
    elif action in ("progress", "pause", "complete"):
        active = entry["session"]
        if not active or active["id"] != command.get("sessionId"):
            fail("播放会话已结束，请重新开始。", 409)
        elapsed, whole = clock - active["last"], clock - active["start"]
        if (
            elapsed > 15
            or at > max(active["position"], entry["watchedSeconds"]) + elapsed + 0.65
            or at > active["frontier"] + whole * 1.01 + 0.4
        ):
            fail("播放连接中断或进度跳跃，请从已保存位置继续。", 409)
        earned = min(at, active["frontier"] + max(0, whole) * 1.005)
        entry["watchedSeconds"] = max(earned, entry["watchedSeconds"])
        if action == "complete":
            if at < duration - 0.1 or entry["watchedSeconds"] < duration - min(0.25, duration * 0.02):
                fail("视频尚未播放到结尾。", 409)
            entry.update(completed=True, watchedSeconds=duration)
        active.update(position=at, last=clock)
        if action != "progress":
            entry["session"] = None
    else:
        fail("进度指令无效。")
    entry["positionSeconds"] = min(at, entry["watchedSeconds"])
    state["updatedAt"] = entry["updatedAt"] = stamp.isoformat()
    state["watches"][material_id] = entry
    record.state = state
    settle(session, actor, row, state)
    session.commit()
    return {
        **{k: v for k, v in entry.items() if k != "session"},
        "sessionId": entry["session"]["id"] if entry["session"] else None,
    }
