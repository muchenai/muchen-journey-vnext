"""Persistent search snapshot with an independent, single-flight sync worker."""
import hashlib
import logging
from datetime import UTC, datetime, timedelta, timezone
from threading import Event, Thread
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from journey_api.db import SessionLocal, engine
from journey_api.directory_cache_models import DirectoryMember, DirectorySync
from journey_api.errors import ApiError

INTERVAL = 24 * 60 * 60
SYNC_ZONE = timezone(timedelta(hours=8))  # Asia/Shanghai; independent of server timezone.
SYNC_HOUR = 3
RETRY = 60
MANUAL_COOLDOWN = 30
logger = logging.getLogger(__name__)
_wake = Event()


def now():
    return datetime.now(UTC)


def key(settings):
    return (settings.feishu_learner_organization_id, settings.feishu_app_id)


def filters(model, settings):
    return (model.organization_id == key(settings)[0], model.app_id == key(settings)[1])


def ensure_state(session, settings):
    session.execute(insert(DirectorySync).values(organization_id=key(settings)[0],
        app_id=key(settings)[1], member_count=0).on_conflict_do_nothing())


def view(state):
    stamp = now()
    syncing = bool(state and state.last_attempt and
        (not state.finished_at or state.last_attempt > state.finished_at) and
        (stamp - state.last_attempt).total_seconds() < 1800)
    pending = bool(state and state.requested_at and
        (not state.last_attempt or state.requested_at > state.last_attempt))
    return {'ready': bool(state and state.last_success), 'syncing': syncing or pending,
        'last_updated_at': state.last_success.isoformat() if state and state.last_success else None,
        'error_code': state.error_code if state else None,
        'member_count': state.member_count if state else 0, 'interval_seconds': INTERVAL}


def status(settings):
    with SessionLocal() as session:
        return view(session.get(DirectorySync, key(settings)))


def search(settings, query):
    # This path never calls Feishu or waits for a synchronization lock.
    with SessionLocal() as session:
        state = session.get(DirectorySync, key(settings))
        info = view(state)
        if info['error_code'] == 'DIRECTORY_PERMISSION_REQUIRED':
            raise ApiError(503, 'DIRECTORY_PERMISSION_REQUIRED', '飞书通讯录权限已变化，请核实权限后刷新通讯录。')
        if not info['ready']:
            _wake.set()
            return {'items': [], 'has_more': False, 'directory': info}
        term = query.strip().casefold()
        employee_no = func.lower(DirectoryMember.profile['employee_no'].as_string())
        rows = session.scalars(select(DirectoryMember).where(*filters(DirectoryMember, settings),
            or_(DirectoryMember.search_name.contains(term, autoescape=True),
                employee_no.contains(term, autoescape=True)))
            .order_by(DirectoryMember.search_name, DirectoryMember.open_id).limit(31)).all()
        return {'items': [r.profile for r in rows[:30]], 'has_more': len(rows) > 30, 'directory': info}


def request_refresh(settings):
    with SessionLocal.begin() as session:
        ensure_state(session, settings)
        state = session.scalar(select(DirectorySync).where(*filters(DirectorySync, settings)).with_for_update())
        info = view(state)
        latest = max((s for s in (state.last_attempt, state.requested_at) if s), default=None)
        if not info['syncing'] and (not latest or (now() - latest).total_seconds() >= MANUAL_COOLDOWN):
            state.requested_at = now()
            info = view(state)
        elif not info['syncing']:
            info['retry_after_seconds'] = max(1, MANUAL_COOLDOWN - int((now() - latest).total_seconds()))
    _wake.set()
    return info


def bulk_snapshot(settings, *, include_people=True):
    # Read members and ancestry from one MVCC snapshot, even if a sync commits
    # between the two SELECTs. No Feishu calls and no synchronization lock.
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as session:
            state = session.get(DirectorySync, key(settings))
            info = view(state)
            if info['error_code'] == 'DIRECTORY_PERMISSION_REQUIRED':
                raise ApiError(503, 'DIRECTORY_PERMISSION_REQUIRED', '飞书通讯录权限已变化，请核实后刷新通讯录。')
            if not info['ready'] or state.department_tree is None:
                _wake.set()
                raise ApiError(503, 'DIRECTORY_PREPARING', '部门和人员名单正在同步，请稍后重试。', retryable=True)
            people = session.scalars(select(DirectoryMember.profile).where(*filters(DirectoryMember, settings))).all() if include_people else []
            return {'tree': state.department_tree, 'people': people, 'directory': info}


def due(state, stamp):
    if state is None:
        return True
    if state.department_tree is None and not state.error_code:
        return True  # Upgrade the old name-only snapshot on the next worker tick.
    if state.requested_at and (not state.last_attempt or state.requested_at > state.last_attempt):
        return True
    # Preserve failure recovery separately from the daily successful-sync schedule.
    interrupted = not state.finished_at or (state.last_attempt and state.last_attempt > state.finished_at)
    if state.error_code or not state.last_success or interrupted:
        return not state.last_attempt or (stamp - state.last_attempt).total_seconds() >= RETRY
    scheduled = stamp.astimezone(SYNC_ZONE).replace(hour=SYNC_HOUR, minute=0, second=0, microsecond=0)
    if stamp < scheduled:
        scheduled -= timedelta(days=1)
    # Persisted last_success prevents duplicate runs after restart. If the
    # service missed 03:00 while offline, the next worker tick catches up once.
    return state.last_success < scheduled


def sync_once(directory, *, force=False):
    settings = directory.settings
    lock_id = int.from_bytes(hashlib.sha256((':'.join(map(str, key(settings)))).encode()).digest()[:8], 'big', signed=True)
    # Session advisory lock coordinates manual/periodic work across API processes.
    with engine.connect() as connection:
        acquired = connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': lock_id})
        connection.commit()
        if not acquired:
            return False
        try:
            with SessionLocal.begin() as session:
                ensure_state(session, settings)
                state = session.get(DirectorySync, key(settings))
                if not force and not due(state, now()):
                    return False
                state.last_attempt = now()
            try:
                profiles, tree = directory.read_snapshot()
                # All pages must succeed before replacing anything; one atomic transaction.
                with SessionLocal.begin() as session:
                    session.execute(delete(DirectoryMember).where(*filters(DirectoryMember, settings)))
                    for profile in profiles:
                        session.add(DirectoryMember(organization_id=key(settings)[0], app_id=key(settings)[1],
                            open_id=profile['open_id'], search_name=profile['name'].casefold(), profile=profile))
                    state = session.get(DirectorySync, key(settings))
                    state.last_success = state.finished_at = now()
                    state.member_count = len(profiles)
                    state.department_tree = tree
                    state.error_code = None
                logger.info('directory.sync_success count=%d', len(profiles))
                return True
            except Exception as exc:
                code = exc.code if isinstance(exc, ApiError) else 'DIRECTORY_SYNC_FAILED'
                with SessionLocal.begin() as session:
                    state = session.get(DirectorySync, key(settings))
                    state.finished_at = now()
                    state.error_code = code
                # No provider payloads, names, credentials or URLs in logs.
                logger.warning('directory.sync_failed code=%s', code)
                return False
        finally:
            connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': lock_id})
            connection.commit()


def start_worker(settings):
    stop = Event()
    if settings.app_env == 'test' or not all((settings.feishu_app_id, settings.feishu_app_secret, settings.feishu_learner_organization_id)):
        return lambda: None

    def run():
        from journey_api.feishu_directory import get_directory
        while not stop.is_set():
            try:
                # Avoid lock/row writes while the snapshot remains fresh.
                with SessionLocal() as session:
                    needed = due(session.get(DirectorySync, key(settings)), now())
                if needed:
                    sync_once(get_directory())
            except Exception:
                logger.warning('directory.worker_unavailable')
            _wake.wait(5)
            _wake.clear()

    thread = Thread(target=run, name='directory-sync', daemon=True)
    thread.start()

    def close():
        stop.set()
        _wake.set()
        thread.join(timeout=1)
    return close
