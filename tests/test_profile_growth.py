"""Growth summaries and history project the same scoped, durable reward facts."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.models import (
    Assignment, AssignmentStatus, CompletionCode, Decision, Enrollment, Evaluation,
    Organization, Review, SubmissionVersion, User, UserStatus,
)
from journey_api.review_admin_models import MedalRedemption, NoviceUnlockDebit
from test_guild_certification import account
from test_medal_economy import complete, medal, save
from test_novice_tasks import setup, post, read, claim
from test_reviewer_workbench import client_for
from test_wp09_feishu_identity import assert_ok


def balance(learner):
    return assert_ok(learner[0].get('/api/v1/me/novice/wallet'))


def history(learner, query=''):
    return assert_ok(learner[0].get('/api/v1/me/novice/growth' + query))


def test_growth_zero_draft_pending_and_approved_award(setup):
    staff, learner, task_id, published, content = setup
    empty = balance(learner)
    assert empty['xp'] == empty['availableXp'] == empty['redeemedXp'] == empty['ownedMedalCount'] == 0
    assert history(learner) == dict(items=[], total=0, hasMore=False, nextOffset=None)
    task = claim(learner, task_id, published['versionId'])
    answer = '真实任务成果包括问题分析、材料学习、实施方案、责任分工、验收依据和下一步执行计划。' * 2
    assert_ok(learner[0].put(f'/api/v1/me/assignments/{task["assignmentId"]}/draft',
        headers={'X-CSRF-Token': learner[1], 'Idempotency-Key': str(uuid.uuid4())},
        json={'expected_revision': task['revision'], 'body': answer}))
    assert balance(learner) == empty and history(learner)['items'] == []
    task = read(learner, task_id)
    submitted = assert_ok(post(learner, f'me/assignments/{task["assignmentId"]}/submissions',
        dict(expected_revision=task['revision'], body=answer)))
    assert balance(learner) == empty and history(learner)['items'] == []
    with SessionLocal() as session:
        review_id = session.scalar(select(Review.id).where(
            Review.submission_version_id == uuid.UUID(submitted['submission_version_id'])))
    lease = assert_ok(post(staff, f'review-admin/reviews/{review_id}/claim',
        dict(action='acquire', expected_revision=1)))
    assert_ok(post(staff, f'review-admin/reviews/{review_id}/decision', dict(decision='APPROVE',
        expected_revision=lease['revision'], claim_token=lease['token'], feedback='', reasons=[])))
    actual = balance(learner)
    detail = history(learner)
    assert actual['xp'] == actual['availableXp'] == 50 and actual['redeemedXp'] == 0
    assert actual['ownedMedalCount'] == 0 and detail['total'] == 1
    item = detail['items'][0]
    assert item['title'] == content['title'] and item['taskId'] == task_id
    assert item['kind'] == 'task_reward' and item['method'] == '任务审核通过' and item['module'] == '新手村'
    assert item['xp'] == actual['xp'] and item['badgePoints'] == [{'id': 'project', 'points': 5}]
    with SessionLocal() as session:
        approval = session.scalar(select(Evaluation).where(Evaluation.review_id == review_id))
        assert datetime.fromisoformat(item['occurredAt']) == approval.created_at
    # Repeat reads are projections, not another reward issuance.
    assert balance(learner) == actual and history(learner) == detail


def test_completed_status_without_pass_is_not_an_award(setup):
    _, learner, task_id, published, _ = setup
    task = claim(learner, task_id, published['versionId'])
    with SessionLocal.begin() as session:
        session.get(Assignment, uuid.UUID(task['assignmentId'])).status = AssignmentStatus.COMPLETED
    assert balance(learner)['xp'] == 0 and history(learner)['total'] == 0


def test_duplicate_approval_keeps_one_award_and_original_timestamp(setup):
    staff, learner, task_id, published, _ = setup
    complete(staff, learner, task_id, published['versionId'])
    before, original = balance(learner), history(learner)
    assignment_id = uuid.UUID(read(learner, task_id)['assignmentId'])
    with SessionLocal.begin() as session:
        evaluation = session.scalar(select(Evaluation).where(
            Evaluation.assignment_id == assignment_id, Evaluation.decision == Decision.PASS))
        review = session.get(Review, evaluation.review_id)
        version = session.get(SubmissionVersion, evaluation.submission_version_id)
        later = evaluation.created_at + timedelta(days=1)

        def copy(row, **changes):
            return type(row)(**{**{column.key: getattr(row, column.key)
                for column in row.__table__.columns}, **changes})

        # A legacy duplicate PASS on another submission version is still one
        # completed assignment. No production write endpoint creates this data.
        second_version = copy(version, id=uuid.uuid4(), version_no=version.version_no + 1, created_at=later)
        session.add(second_version)
        session.flush()
        second_review = copy(review, id=uuid.uuid4(), submission_version_id=second_version.id,
                             assigned_at=later, started_at=later, finalized_at=later)
        session.add(second_review)
        session.flush()
        session.add(copy(evaluation, id=uuid.uuid4(), review_id=second_review.id,
                         submission_version_id=second_version.id, created_at=later))
    assert balance(learner) == before
    assert history(learner) == original


def test_redemption_snapshot_count_pagination_and_xp_currency_isolation(setup):
    staff, learner, task_id, published, content = setup
    complete(staff, learner, task_id, published['versionId'])
    task = read(learner, task_id)
    medal_id = str(uuid.uuid4())
    saved = assert_ok(save(staff, medal_id, medal()))
    redeem_path = f'me/novice/medals/{medal_id}/redeem'
    first = assert_ok(post(learner, redeem_path, dict(expected_revision=saved['revision'])))
    assert assert_ok(post(learner, redeem_path, dict(expected_revision=saved['revision'])))['id'] == first['id']
    current = next(item for item in assert_ok(staff[0].get('/api/v1/review-admin/medals'))['medals']
                   if item['id'] == medal_id)
    assert_ok(save(staff, medal_id, {**current, 'name': '不应替换历史名称',
        'costs': [{'badgeId': 'project', 'points': 4}], 'status': 'unpublished'}, current['revision']))
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/archive',
        dict(expected_revision=published['revision'], archived=True)))
    with SessionLocal.begin() as session:
        assignment = session.get(Assignment, uuid.UUID(task['assignmentId']))
        # Historical task-point debits also must not be mistaken for XP spend.
        session.add(NoviceUnlockDebit(enrollment_id=assignment.enrollment_id,
            organization_id=ORGANIZATION_ID,
            user_id=session.get(Enrollment, assignment.enrollment_id).learner_id, amount=1))
    actual = balance(learner)
    full = history(learner)
    assert actual['xp'] == actual['availableXp'] == 50 and actual['redeemedXp'] == 0
    assert actual['ownedMedalCount'] == 1 and actual['badgeBalances']['project'] == 2
    assert full['total'] == 2
    redemption = next(item for item in full['items'] if item['kind'] == 'medal_redemption')
    assert redemption['title'] == redemption['medal']['name'] == '隔离测试徽章'
    assert redemption['medal']['id'] == medal_id and redemption['method'] == '徽章点兑换'
    assert redemption['xp'] == 0 and redemption['badgePoints'] == [{'id': 'project', 'points': -3}]
    assert next(item for item in full['items'] if item['kind'] == 'task_reward')['title'] == content['title']
    assert sum(item['xp'] for item in full['items']) == actual['xp']
    assert sum(point['points'] for item in full['items'] for point in item['badgePoints']) == 2
    one = history(learner, '?offset=0&limit=1')
    two = history(learner, f'?offset={one["nextOffset"]}&limit=1')
    assert one['hasMore'] is True and one['nextOffset'] == 1
    assert two['hasMore'] is False and two['nextOffset'] is None
    assert one['items'] + two['items'] == full['items']
    assert history(learner, '?offset=10&limit=1') == dict(items=[], total=2, hasMore=False, nextOffset=None)
    with SessionLocal() as session:
        row = session.get(MedalRedemption, uuid.UUID(first['id']))
        assert datetime.fromisoformat(redemption['occurredAt']) == row.created_at


def test_growth_is_scoped_and_follows_inherited_learner_owner(setup):
    staff, learner, task_id, published, _ = setup
    complete(staff, learner, task_id, published['versionId'])
    expected_balance, expected_history = balance(learner), history(learner)
    same_org = account(ORGANIZATION_ID)
    outsider = same_org['client'], same_org['csrf']
    assert balance(outsider)['xp'] == 0 and history(outsider)['total'] == 0
    org_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=org_id, name='隔离成长流水组织'))
    foreign = account(org_id)
    foreign_pair = foreign['client'], foreign['csrf']
    assert balance(foreign_pair)['ownedMedalCount'] == 0 and history(foreign_pair)['total'] == 0
    task = read(learner, task_id)
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        assignment = session.get(Assignment, uuid.UUID(task['assignmentId']))
        owner_id = session.get(Enrollment, assignment.enrollment_id).learner_id
        session.add(CompletionCode(id=uuid.uuid4(), organization_id=ORGANIZATION_ID,
            user_id=owner_id, code_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            code_ciphertext='isolated-growth-test', code_hint='test',
            expires_at=now - timedelta(days=1), used_at=now - timedelta(days=2),
            migrated_to_user_id=same_org['id']))
        session.get(User, owner_id).status = UserStatus.DISABLED
    assert balance(outsider) == expected_balance
    assert history(outsider) == expected_history


def test_growth_requires_learner_session_and_valid_page_bounds(setup):
    staff, learner, *_ = setup
    assert client_for('anonymous-growth-' + uuid.uuid4().hex).get('/api/v1/me/novice/growth').status_code == 401
    assert staff[0].get('/api/v1/me/novice/growth').status_code in {401, 403}
    for query in ['?offset=-1', '?offset=2147483648', '?limit=0', '?limit=101', '?limit=1.5', '?offset=invalid']:
        assert learner[0].get('/api/v1/me/novice/growth' + query).status_code == 422
