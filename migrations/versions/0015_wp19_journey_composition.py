"""Add immutable journey composition and fixed enrollment stage scope.

Revision ID: 0015_wp19_journey_composition
Revises: 0014_wp12_data_lifecycle
"""

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0015_wp19_journey_composition"
down_revision = "0014_wp12_data_lifecycle"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def _content_owner(bind: sa.Connection, organization_id: uuid.UUID) -> uuid.UUID:
    owner = bind.execute(
        sa.text(
            """
            SELECT ra.user_id
            FROM role_assignments AS ra
            JOIN users AS u ON u.id = ra.user_id
            WHERE ra.organization_id = :organization_id
              AND ra.role = 'OPERATOR'
              AND u.status = 'ACTIVE'
            ORDER BY ra.user_id
            LIMIT 1
            """
        ),
        {"organization_id": organization_id},
    ).scalar()
    if owner is None:
        owner = bind.execute(
            sa.text(
                "SELECT id FROM users WHERE organization_id = :organization_id ORDER BY id LIMIT 1"
            ),
            {"organization_id": organization_id},
        ).scalar()
    if owner is None:
        raise RuntimeError("Journey migration requires an organization content owner")
    return owner


def _sequence_version(
    bind: sa.Connection,
    *,
    organization_id: uuid.UUID,
    definition_id: uuid.UUID,
    owner_id: uuid.UUID,
    version: int,
    task_version_ids: tuple[uuid.UUID, ...],
) -> tuple[uuid.UUID, dict[uuid.UUID, uuid.UUID]]:
    journey_version_id = uuid.uuid4()
    bind.execute(
        sa.text(
            """
            INSERT INTO journey_versions
                (id, organization_id, journey_definition_id, version, title,
                 change_summary, published_by, reviewed_by)
            VALUES
                (:id, :organization_id, :definition_id, :version,
                 'Alpha validation journey',
                 'WP-19 migration: preserve the exact existing task sequence.',
                 :owner_id, :owner_id)
            """
        ),
        {
            "id": journey_version_id,
            "organization_id": organization_id,
            "definition_id": definition_id,
            "version": version,
            "owner_id": owner_id,
        },
    )
    stage_by_task: dict[uuid.UUID, uuid.UUID] = {}
    for position, task_version_id in enumerate(task_version_ids, start=1):
        task = bind.execute(
            sa.text(
                """
                SELECT tv.task_definition_id, td.stable_key
                FROM task_versions AS tv
                JOIN task_definitions AS td ON td.id = tv.task_definition_id
                WHERE tv.id = :task_version_id
                  AND tv.organization_id = :organization_id
                """
            ),
            {
                "task_version_id": task_version_id,
                "organization_id": organization_id,
            },
        ).mappings().first()
        if task is None:
            raise RuntimeError("Journey migration found an out-of-scope TaskVersion")
        stage_id = uuid.uuid4()
        stage_by_task[task_version_id] = stage_id
        bind.execute(
            sa.text(
                """
                INSERT INTO journey_stage_versions
                    (id, organization_id, journey_version_id, stable_key, position,
                     stage_kind, completion_policy, task_definition_id, task_version_id)
                VALUES
                    (:id, :organization_id, :journey_version_id, :stable_key, :position,
                     'ASSESSMENT', 'REVIEW_REQUIRED', :task_definition_id, :task_version_id)
                """
            ),
            {
                "id": stage_id,
                "organization_id": organization_id,
                "journey_version_id": journey_version_id,
                "stable_key": f"{task['stable_key']}-{position}",
                "position": position,
                "task_definition_id": task["task_definition_id"],
                "task_version_id": task_version_id,
            },
        )
    return journey_version_id, stage_by_task


def _backfill_existing_alpha(bind: sa.Connection) -> None:
    organizations = bind.execute(
        sa.text(
            """
            SELECT organization_id FROM enrollments
            UNION
            SELECT organization_id FROM invites
            ORDER BY organization_id
            """
        )
    ).scalars().all()
    for organization_id in organizations:
        owner_id = _content_owner(bind, organization_id)
        definition_id = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO journey_definitions
                    (id, organization_id, stable_key, kind, status, revision, created_by)
                VALUES
                    (:id, :organization_id, 'ALPHA-LEGACY', 'ALPHA_VALIDATION',
                     'PUBLISHED', 1, :owner_id)
                """
            ),
            {
                "id": definition_id,
                "organization_id": organization_id,
                "owner_id": owner_id,
            },
        )

        enrollment_ids = bind.execute(
            sa.text(
                "SELECT id FROM enrollments WHERE organization_id = :organization_id ORDER BY id"
            ),
            {"organization_id": organization_id},
        ).scalars().all()
        enrollment_rows = bind.execute(
            sa.text(
                """
                SELECT e.id AS enrollment_id, a.id AS assignment_id,
                       a.task_version_id, a.position
                FROM enrollments AS e
                JOIN assignments AS a ON a.enrollment_id = e.id
                WHERE e.organization_id = :organization_id
                ORDER BY e.id, a.position, a.id
                """
            ),
            {"organization_id": organization_id},
        ).mappings().all()
        enrollment_sequences: dict[uuid.UUID, list[dict[str, object]]] = {
            enrollment_id: [] for enrollment_id in enrollment_ids
        }
        for row in enrollment_rows:
            enrollment_sequences.setdefault(row["enrollment_id"], []).append(dict(row))

        sequence_by_enrollment: dict[uuid.UUID, tuple[uuid.UUID, ...]] = {}
        for enrollment_id, rows in enrollment_sequences.items():
            sequence = tuple(row["task_version_id"] for row in rows)
            if not sequence:
                task_version_id = bind.execute(
                    sa.text(
                        """
                        SELECT i.task_version_id
                        FROM join_contexts AS jc
                        JOIN invites AS i ON i.id = jc.invite_id
                        WHERE jc.enrollment_id = :enrollment_id
                        ORDER BY jc.created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"enrollment_id": enrollment_id},
                ).scalar()
                if task_version_id is None:
                    task_version_id = bind.execute(
                        sa.text(
                            """
                            SELECT id FROM task_versions
                            WHERE organization_id = :organization_id
                            ORDER BY published_at, id
                            LIMIT 1
                            """
                        ),
                        {"organization_id": organization_id},
                    ).scalar()
                if task_version_id is None:
                    raise RuntimeError("Enrollment cannot be migrated without a TaskVersion")
                sequence = (task_version_id,)
            sequence_by_enrollment[enrollment_id] = sequence

        invite_tasks = bind.execute(
            sa.text(
                """
                SELECT DISTINCT task_version_id
                FROM invites
                WHERE organization_id = :organization_id
                ORDER BY task_version_id
                """
            ),
            {"organization_id": organization_id},
        ).scalars().all()
        sequences = set(sequence_by_enrollment.values())
        sequences.update((task_version_id,) for task_version_id in invite_tasks)

        versions: dict[
            tuple[uuid.UUID, ...], tuple[uuid.UUID, dict[uuid.UUID, uuid.UUID]]
        ] = {}
        for version_number, sequence in enumerate(sorted(sequences, key=lambda item: tuple(map(str, item))), start=1):
            if not sequence:
                continue
            versions[sequence] = _sequence_version(
                bind,
                organization_id=organization_id,
                definition_id=definition_id,
                owner_id=owner_id,
                version=version_number,
                task_version_ids=sequence,
            )

        for enrollment_id, rows in enrollment_sequences.items():
            sequence = sequence_by_enrollment[enrollment_id]
            journey_version_id, stage_by_task = versions[sequence]
            bind.execute(
                sa.text(
                    "UPDATE enrollments SET journey_version_id = :journey_version_id WHERE id = :id"
                ),
                {"journey_version_id": journey_version_id, "id": enrollment_id},
            )
            for row in rows:
                bind.execute(
                    sa.text(
                        """
                        UPDATE assignments
                        SET journey_version_id = :journey_version_id,
                            journey_stage_version_id = :stage_id
                        WHERE id = :assignment_id
                        """
                    ),
                    {
                        "journey_version_id": journey_version_id,
                        "stage_id": stage_by_task[row["task_version_id"]],
                        "assignment_id": row["assignment_id"],
                    },
                )

        invites = bind.execute(
            sa.text(
                """
                SELECT id, target_user_id, task_version_id
                FROM invites
                WHERE organization_id = :organization_id
                ORDER BY id
                """
            ),
            {"organization_id": organization_id},
        ).mappings().all()
        for invite in invites:
            journey_version_id = None
            if invite["target_user_id"] is not None:
                journey_version_id = bind.execute(
                    sa.text(
                        """
                        SELECT e.journey_version_id
                        FROM enrollments AS e
                        JOIN assignments AS a ON a.enrollment_id = e.id
                        WHERE e.organization_id = :organization_id
                          AND e.learner_id = :target_user_id
                          AND a.task_version_id = :task_version_id
                        ORDER BY e.id
                        LIMIT 1
                        """
                    ),
                    {
                        "organization_id": organization_id,
                        "target_user_id": invite["target_user_id"],
                        "task_version_id": invite["task_version_id"],
                    },
                ).scalar()
            if journey_version_id is None:
                journey_version_id = versions[(invite["task_version_id"],)][0]
            bind.execute(
                sa.text(
                    "UPDATE invites SET journey_version_id = :journey_version_id WHERE id = :id"
                ),
                {"journey_version_id": journey_version_id, "id": invite["id"]},
            )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_task_versions_id_definition_organization",
        "task_versions",
        ["id", "task_definition_id", "organization_id"],
    )
    op.create_table(
        "journey_definitions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("stable_key", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "stable_key", name="uq_journey_definitions_organization_key"
        ),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_journey_definitions_id_organization"
        ),
        sa.CheckConstraint(
            "kind IN ('ALPHA_VALIDATION', 'FORMAL_EXPLORATION')",
            name="ck_journey_definitions_kind",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'WITHDRAWN')",
            name="ck_journey_definitions_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_journey_definitions_revision"),
    )
    op.create_index(
        "ix_journey_definitions_organization_id", "journey_definitions", ["organization_id"]
    )
    op.create_table(
        "journey_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("journey_definition_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("published_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("published_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["journey_definition_id", "organization_id"],
            ["journey_definitions.id", "journey_definitions.organization_id"],
            name="fk_journey_versions_definition_organization",
        ),
        sa.UniqueConstraint(
            "journey_definition_id", "version", name="uq_journey_versions_definition_version"
        ),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_journey_versions_id_organization"
        ),
        sa.CheckConstraint("version >= 1", name="ck_journey_versions_positive_version"),
    )
    op.create_index("ix_journey_versions_organization_id", "journey_versions", ["organization_id"])
    op.create_index(
        "ix_journey_versions_journey_definition_id",
        "journey_versions",
        ["journey_definition_id"],
    )
    op.create_table(
        "journey_stage_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("journey_version_id", UUID, nullable=False),
        sa.Column("stable_key", sa.String(80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stage_kind", sa.String(16), nullable=False),
        sa.Column("completion_policy", sa.String(24), nullable=False),
        sa.Column("task_definition_id", UUID, nullable=False),
        sa.Column("task_version_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(
            ["journey_version_id", "organization_id"],
            ["journey_versions.id", "journey_versions.organization_id"],
            name="fk_journey_stage_versions_journey_organization",
        ),
        sa.ForeignKeyConstraint(
            ["task_version_id", "task_definition_id", "organization_id"],
            ["task_versions.id", "task_versions.task_definition_id", "task_versions.organization_id"],
            name="fk_journey_stage_versions_task_scope",
        ),
        sa.UniqueConstraint(
            "journey_version_id", "stable_key", name="uq_journey_stage_versions_journey_key"
        ),
        sa.UniqueConstraint(
            "journey_version_id", "position", name="uq_journey_stage_versions_journey_position"
        ),
        sa.UniqueConstraint(
            "id",
            "journey_version_id",
            "organization_id",
            "task_definition_id",
            "task_version_id",
            "position",
            name="uq_journey_stage_versions_assignment_scope",
        ),
        sa.CheckConstraint("position >= 1", name="ck_journey_stage_versions_positive_position"),
        sa.CheckConstraint(
            "stage_kind IN ('ORIENTATION', 'TREASURE', 'ASSESSMENT')",
            name="ck_journey_stage_versions_kind",
        ),
        sa.CheckConstraint(
            "completion_policy IN ('LEARNER_EVIDENCE', 'REVIEW_REQUIRED')",
            name="ck_journey_stage_versions_completion_policy",
        ),
        sa.CheckConstraint(
            "(stage_kind IN ('ORIENTATION', 'TREASURE') AND completion_policy = 'LEARNER_EVIDENCE') "
            "OR (stage_kind = 'ASSESSMENT' AND completion_policy = 'REVIEW_REQUIRED')",
            name="ck_journey_stage_versions_kind_policy",
        ),
    )
    op.create_index(
        "ix_journey_stage_versions_organization_id",
        "journey_stage_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_journey_stage_versions_journey_version_id",
        "journey_stage_versions",
        ["journey_version_id"],
    )

    op.add_column("invites", sa.Column("journey_version_id", UUID, nullable=True))
    op.add_column("enrollments", sa.Column("journey_version_id", UUID, nullable=True))
    op.add_column("assignments", sa.Column("journey_version_id", UUID, nullable=True))
    op.add_column("assignments", sa.Column("journey_stage_version_id", UUID, nullable=True))

    _backfill_existing_alpha(op.get_bind())
    op.execute(
        """
        UPDATE assignments AS later
        SET status = 'LOCKED'
        WHERE later.status = 'AVAILABLE'
          AND EXISTS (
              SELECT 1
              FROM assignments AS earlier
              WHERE earlier.enrollment_id = later.enrollment_id
                AND earlier.position < later.position
                AND earlier.status NOT IN ('COMPLETED', 'CANCELLED')
          )
        """
    )

    op.alter_column("invites", "journey_version_id", nullable=False)
    op.alter_column("invites", "task_version_id", nullable=True)
    op.alter_column("enrollments", "journey_version_id", nullable=False)
    op.alter_column("assignments", "journey_version_id", nullable=False)
    op.alter_column("assignments", "journey_stage_version_id", nullable=False)

    op.create_foreign_key(
        "fk_invites_journey_version_organization",
        "invites",
        "journey_versions",
        ["journey_version_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_enrollments_journey_version_organization",
        "enrollments",
        "journey_versions",
        ["journey_version_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_enrollments_journey_scope",
        "enrollments",
        ["id", "organization_id", "journey_version_id"],
    )
    op.create_foreign_key(
        "fk_assignments_enrollment_journey_scope",
        "assignments",
        "enrollments",
        ["enrollment_id", "organization_id", "journey_version_id"],
        ["id", "organization_id", "journey_version_id"],
    )
    op.create_foreign_key(
        "fk_assignments_journey_stage_scope",
        "assignments",
        "journey_stage_versions",
        [
            "journey_stage_version_id",
            "journey_version_id",
            "organization_id",
            "task_definition_id",
            "task_version_id",
            "position",
        ],
        [
            "id",
            "journey_version_id",
            "organization_id",
            "task_definition_id",
            "task_version_id",
            "position",
        ],
    )
    op.create_index("ix_invites_journey_version_id", "invites", ["journey_version_id"])
    op.create_index("ix_enrollments_journey_version_id", "enrollments", ["journey_version_id"])
    op.create_index("ix_assignments_journey_version_id", "assignments", ["journey_version_id"])
    op.create_index(
        "ix_assignments_journey_stage_version_id",
        "assignments",
        ["journey_stage_version_id"],
    )
    op.drop_constraint("ck_assignments_status", "assignments", type_="check")
    op.create_check_constraint(
        "ck_assignments_status",
        "assignments",
        "status IN ('LOCKED', 'AVAILABLE', 'IN_PROGRESS', 'SUBMITTED', 'IN_REVIEW', "
        "'NEEDS_REVISION', 'COMPLETED', 'CANCELLED')",
    )

    op.execute(
        """
        CREATE FUNCTION reject_journey_version_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Published JourneyVersion rows are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER journey_versions_immutable
        BEFORE UPDATE OR DELETE ON journey_versions
        FOR EACH ROW EXECUTE FUNCTION reject_journey_version_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER journey_stage_versions_immutable
        BEFORE UPDATE OR DELETE ON journey_stage_versions
        FOR EACH ROW EXECUTE FUNCTION reject_journey_version_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS journey_stage_versions_immutable ON journey_stage_versions")
    op.execute("DROP TRIGGER IF EXISTS journey_versions_immutable ON journey_versions")
    op.execute("DROP FUNCTION IF EXISTS reject_journey_version_mutation()")
    op.drop_constraint("ck_assignments_status", "assignments", type_="check")
    op.execute("UPDATE assignments SET status = 'AVAILABLE' WHERE status = 'LOCKED'")
    op.create_check_constraint(
        "ck_assignments_status",
        "assignments",
        "status IN ('AVAILABLE', 'IN_PROGRESS', 'SUBMITTED', 'IN_REVIEW', "
        "'NEEDS_REVISION', 'COMPLETED', 'CANCELLED')",
    )
    op.drop_index("ix_assignments_journey_stage_version_id", table_name="assignments")
    op.drop_index("ix_assignments_journey_version_id", table_name="assignments")
    op.drop_index("ix_enrollments_journey_version_id", table_name="enrollments")
    op.drop_index("ix_invites_journey_version_id", table_name="invites")
    op.drop_constraint("fk_assignments_journey_stage_scope", "assignments", type_="foreignkey")
    op.drop_constraint("fk_assignments_enrollment_journey_scope", "assignments", type_="foreignkey")
    op.drop_constraint("uq_enrollments_journey_scope", "enrollments", type_="unique")
    op.drop_constraint(
        "fk_enrollments_journey_version_organization", "enrollments", type_="foreignkey"
    )
    op.drop_constraint("fk_invites_journey_version_organization", "invites", type_="foreignkey")
    op.drop_column("assignments", "journey_stage_version_id")
    op.drop_column("assignments", "journey_version_id")
    op.drop_column("enrollments", "journey_version_id")
    op.drop_column("invites", "journey_version_id")
    op.alter_column("invites", "task_version_id", nullable=False)
    op.drop_table("journey_stage_versions")
    op.drop_table("journey_versions")
    op.drop_table("journey_definitions")
    op.drop_constraint(
        "uq_task_versions_id_definition_organization", "task_versions", type_="unique"
    )
