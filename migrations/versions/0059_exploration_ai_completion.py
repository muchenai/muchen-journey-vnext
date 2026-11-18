"""Allow narrowly scoped immutable dynamic exploration AI completion evidence.

The existing advisory disclosure shape and all human Evaluation restrictions
remain intact. Only a matching, server-scored dynamic exploration attempt can
create the separate AI completion shape on an immutable submission version.
"""
from alembic import op
import sqlalchemy as sa

revision = "0059_exploration_ai_completion"
down_revision = "0058_exploration_ai_details"
branch_labels = None
depends_on = None

# Kept identical to 0020, including the five-key allowlist and advisory flag.
LEGACY_AI_PROVENANCE_CHECK = """
jsonb_typeof(ai_use) = 'object'
AND ai_use ?& ARRAY[
    'used', 'purpose', 'model_version', 'prompt_version',
    'output_is_advisory_only'
]
AND (ai_use - ARRAY[
    'used', 'purpose', 'model_version', 'prompt_version',
    'output_is_advisory_only'
]) = '{}'::jsonb
AND jsonb_typeof(ai_use -> 'used') = 'boolean'
AND jsonb_typeof(ai_use -> 'output_is_advisory_only') = 'boolean'
AND (ai_use ->> 'output_is_advisory_only')::boolean = TRUE
AND (
    (
        (ai_use ->> 'used')::boolean = FALSE
        AND ai_use -> 'purpose' = 'null'::jsonb
        AND ai_use -> 'model_version' = 'null'::jsonb
        AND ai_use -> 'prompt_version' = 'null'::jsonb
    )
    OR
    (
        (ai_use ->> 'used')::boolean = TRUE
        AND jsonb_typeof(ai_use -> 'purpose') = 'string'
        AND length(ai_use ->> 'purpose') BETWEEN 3 AND 200
        AND jsonb_typeof(ai_use -> 'model_version') = 'string'
        AND length(ai_use ->> 'model_version') BETWEEN 1 AND 200
        AND jsonb_typeof(ai_use -> 'prompt_version') = 'string'
        AND length(ai_use ->> 'prompt_version') BETWEEN 1 AND 200
    )
)
"""

AI_COMPLETION_SHAPE = """
jsonb_typeof(ai_use) = 'object'
AND ai_use ?& ARRAY['used', 'purpose', 'model_version', 'prompt_version',
    'output_is_advisory_only', 'exploration_ai_evaluation']
AND (ai_use - ARRAY['used', 'purpose', 'model_version', 'prompt_version',
    'output_is_advisory_only', 'exploration_ai_evaluation']) = '{}'::jsonb
AND ai_use -> 'used' = 'true'::jsonb
AND ai_use ->> 'purpose' = 'DYNAMIC_EXPLORATION_AI_ASSESSMENT'
AND ai_use -> 'output_is_advisory_only' = 'false'::jsonb
AND jsonb_typeof(ai_use -> 'model_version') = 'string'
AND length(ai_use ->> 'model_version') BETWEEN 1 AND 200
AND jsonb_typeof(ai_use -> 'prompt_version') = 'string'
AND length(ai_use ->> 'prompt_version') BETWEEN 1 AND 200
AND jsonb_typeof(ai_use -> 'exploration_ai_evaluation') = 'object'
"""

TRIGGER_SQL = r"""
CREATE FUNCTION enforce_exploration_ai_submission() RETURNS trigger AS $$
DECLARE
    proof jsonb;
    evidence jsonb;
    content jsonb;
    rubric jsonb;
    configured jsonb;
    dimension jsonb;
    row_data record;
    identity text;
    dimension_count integer;
    total numeric := 0;
    score numeric;
    maximum numeric;
    threshold numeric;
BEGIN
    IF NOT (NEW.ai_use ? 'exploration_ai_evaluation') THEN
        RETURN NEW;
    END IF;
    proof := NEW.ai_use -> 'exploration_ai_evaluation';
    IF NOT COALESCE(
        jsonb_typeof(proof) = 'object'
        AND proof ?& ARRAY['kind','source','attemptId','requestHash','taskVersionId',
            'assignmentId','originalInput','completedAt','validated','score','maxScore',
            'passed','dimensions','feedback','rubricHash','evidenceHash','model','promptVersion']
        AND proof ->> 'kind' = 'EXPLORATION_AI' AND proof ->> 'source' = 'AI'
        AND proof -> 'validated' = 'true'::jsonb AND proof -> 'passed' = 'true'::jsonb
        AND jsonb_typeof(proof -> 'score') = 'number' AND proof -> 'maxScore' = '100'::jsonb
        AND jsonb_typeof(proof -> 'dimensions') = 'array'
        AND jsonb_typeof(proof -> 'feedback') = 'string' AND length(proof ->> 'feedback') > 0
        AND proof ->> 'rubricHash' ~ '^[0-9a-f]{64}$'
        AND proof ->> 'evidenceHash' ~ '^[0-9a-f]{64}$'
        AND proof ->> 'requestHash' ~ '^[0-9a-f]{64}$'
        AND proof ->> 'model' = NEW.ai_use ->> 'model_version'
        AND proof ->> 'promptVersion' = NEW.ai_use ->> 'prompt_version', FALSE)
    THEN
        RAISE EXCEPTION 'invalid exploration AI completion evidence' USING ERRCODE = '23514';
    END IF;
    BEGIN
        SELECT sc.details::jsonb AS details, pc.content::jsonb AS content,
            a.revision AS revision, a.status AS assignment_status,
            sc.answer AS answer, sc.result AS feedback, sc.id AS attempt_id,
            a.id AS assignment_id, a.task_version_id AS task_version_id
        INTO row_data
        FROM submissions s
        JOIN assignments a ON a.id = s.assignment_id AND a.organization_id = s.organization_id
        JOIN enrollments e ON e.id = a.enrollment_id AND e.organization_id = a.organization_id
        JOIN exploration_work w ON w.assignment_id = a.id AND w.organization_id = a.organization_id
            AND w.user_id = e.learner_id AND w.task_id = a.task_definition_id
        JOIN published_task_content pc ON pc.task_version_id = a.task_version_id
            AND pc.organization_id = a.organization_id
        JOIN review_admin_tasks p ON p.task_definition_id = a.task_definition_id
            AND p.organization_id = a.organization_id
        JOIN exploration_self_checks sc ON sc.id = (proof ->> 'attemptId')::uuid
            AND sc.organization_id = a.organization_id AND sc.user_id = e.learner_id
            AND sc.assignment_id = a.id AND sc.task_version_id = a.task_version_id
        JOIN users u ON u.id = e.learner_id AND u.organization_id = a.organization_id
        WHERE s.id = NEW.submission_id AND e.learner_id = NEW.created_by
            AND e.novice_task_id = a.task_definition_id AND e.journey_version_id IS NULL
            AND a.journey_stage_version_id IS NULL
            AND a.status IN ('IN_PROGRESS','NEEDS_REVISION','COMPLETED')
            AND e.status IN ('ACTIVE','COMPLETED') AND sc.status = 'COMPLETED'
            AND p.status <> 'deleted' AND p.content ->> 'camp' = 'exploration'
            AND pc.content ->> 'camp' = 'exploration'
            AND pc.content ->> 'reviewMode' = 'ai'
            AND COALESCE(pc.content ->> 'completionMode','assessment') = 'assessment'
            AND u.status = 'ACTIVE'
            AND EXISTS (SELECT 1 FROM role_assignments r WHERE r.user_id = u.id
                AND r.organization_id = a.organization_id AND r.role = 'LEARNER');
        IF NOT FOUND THEN
            RAISE EXCEPTION 'AI completion does not match owned dynamic AI task' USING ERRCODE = '23514';
        END IF;
        evidence := row_data.details;
        content := row_data.content;
        IF NOT COALESCE(
            evidence -> 'analysisCompleted' = 'true'::jsonb
            AND evidence ->> 'requestHash' = proof ->> 'requestHash'
            AND row_data.answer = proof ->> 'originalInput'
            AND row_data.feedback = proof ->> 'feedback'
            AND row_data.assignment_id = (proof ->> 'assignmentId')::uuid
            AND row_data.task_version_id = (proof ->> 'taskVersionId')::uuid
            AND (row_data.revision = (evidence ->> 'assignmentRevision')::integer
                OR row_data.assignment_status = 'COMPLETED'
                AND row_data.revision = (evidence ->> 'assignmentRevision')::integer + 1)
            AND (proof - ARRAY['kind','source','attemptId','requestHash','taskVersionId',
                'assignmentId','originalInput','completedAt','document']) = evidence -> 'grading'
            AND (proof ->> 'completedAt')::timestamptz = NEW.created_at
            AND NEW.body = CASE WHEN evidence ->> 'inputKind' = 'document'
                THEN evidence ->> 'gradingAnswer' ELSE row_data.answer END
            AND (content -> 'aiRubricSnapshot' ->> 'canonical_hash' IS NULL
                OR content -> 'aiRubricSnapshot' ->> 'canonical_hash' = proof ->> 'rubricHash'), FALSE)
        THEN
            RAISE EXCEPTION 'AI completion proof does not match scored attempt' USING ERRCODE = '23514';
        END IF;
        IF evidence ->> 'inputKind' = 'document' THEN
            IF NOT COALESCE(evidence -> 'gradingDocumentValidated' = 'true'::jsonb
                AND proof -> 'document' = evidence -> 'gradingDocument', FALSE)
                OR NOT EXISTS (
                    SELECT 1 FROM ai_self_checks source
                    WHERE source.id = (evidence ->> 'aiSelfCheckId')::uuid
                        AND source.attempt_id = row_data.attempt_id
                        AND source.assignment_id = row_data.assignment_id
                        AND source.learner_id = NEW.created_by
                        AND source.organization_id = (SELECT organization_id FROM submissions WHERE id = NEW.submission_id)
                        AND source.input_hash = proof ->> 'evidenceHash'
                        AND source.document_revision = evidence -> 'gradingDocument' ->> 'revision'
                        AND source.document_hash = evidence -> 'gradingDocument' ->> 'sha256'
                )
            THEN
                RAISE EXCEPTION 'AI answer document was not validated' USING ERRCODE = '23514';
            END IF;
        ELSIF COALESCE(evidence ->> 'inputKind','text') <> 'text' THEN
            RAISE EXCEPTION 'invalid AI answer kind' USING ERRCODE = '23514';
        END IF;
        -- New publications persist the same normalized private policy used by
        -- the scorer. The fallback retains historic publications without it.
        rubric := COALESCE(content -> 'aiRubricSnapshot' -> 'dimensions', content -> 'rubric');
        IF jsonb_typeof(rubric) <> 'array'
            OR jsonb_array_length(rubric) NOT BETWEEN 1 AND 12
            OR jsonb_array_length(proof -> 'dimensions') <> jsonb_array_length(rubric)
        THEN
            RAISE EXCEPTION 'AI scoring dimensions incomplete' USING ERRCODE = '23514';
        END IF;
        FOR configured, dimension_count IN SELECT value, ordinality::integer
            FROM jsonb_array_elements(rubric) WITH ORDINALITY
        LOOP
            identity := COALESCE(NULLIF(configured ->> 'id',''),'dimension-' || dimension_count);
            SELECT count(*) INTO dimension_count
                FROM jsonb_array_elements(proof -> 'dimensions') item WHERE item ->> 'id' = identity;
            SELECT item INTO dimension FROM jsonb_array_elements(proof -> 'dimensions') item
                WHERE item ->> 'id' = identity LIMIT 1;
            IF dimension_count <> 1 OR NOT COALESCE(
                jsonb_typeof(dimension -> 'score') = 'number'
                AND jsonb_typeof(dimension -> 'maxScore') = 'number'
                AND dimension ->> 'name' = btrim(configured ->> 'name',
                    U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000')
                AND jsonb_typeof(dimension -> 'evidence') = 'string'
                AND length(btrim(dimension ->> 'evidence')) > 0
                AND jsonb_typeof(dimension -> 'feedback') = 'string'
                AND length(btrim(dimension ->> 'feedback')) > 0, FALSE)
            THEN
                RAISE EXCEPTION 'AI scoring dimension invalid' USING ERRCODE = '23514';
            END IF;
            score := (dimension ->> 'score')::numeric;
            maximum := (configured ->> 'points')::numeric;
            IF maximum <= 0 OR maximum > 100 OR (dimension ->> 'maxScore')::numeric <> maximum
                OR score < 0 OR score > maximum OR trunc(score * 100) <> score * 100
            THEN
                RAISE EXCEPTION 'AI scoring dimension out of range' USING ERRCODE = '23514';
            END IF;
            total := total + score;
        END LOOP;
        threshold := COALESCE(content ->> 'passScore','60')::numeric;
        IF total <> (proof ->> 'score')::numeric OR total > 100 OR threshold NOT BETWEEN 0 AND 100
            OR total < threshold
        THEN
            RAISE EXCEPTION 'AI score did not satisfy publisher passing score' USING ERRCODE = '23514';
        END IF;
    EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR datetime_field_overflow
        OR invalid_datetime_format THEN
        RAISE EXCEPTION 'invalid exploration AI completion evidence types' USING ERRCODE = '23514';
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_exploration_ai_submission
BEFORE INSERT ON submission_versions
FOR EACH ROW EXECUTE FUNCTION enforce_exploration_ai_submission();
"""


def upgrade():
    op.drop_constraint("ck_submission_versions_ai_provenance", "submission_versions", type_="check")
    op.create_check_constraint("ck_submission_versions_ai_provenance", "submission_versions",
        f"({LEGACY_AI_PROVENANCE_CHECK}) OR COALESCE(({AI_COMPLETION_SHAPE}), FALSE)")
    op.execute(TRIGGER_SQL)


def downgrade():
    if op.get_bind().execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM submission_versions WHERE ai_use ? 'exploration_ai_evaluation')")).scalar():
        raise RuntimeError("Immutable AI completions exist; refusing to discard their provenance contract.")
    op.execute("DROP TRIGGER trg_exploration_ai_submission ON submission_versions")
    op.execute("DROP FUNCTION enforce_exploration_ai_submission()")
    op.drop_constraint("ck_submission_versions_ai_provenance", "submission_versions", type_="check")
    op.create_check_constraint("ck_submission_versions_ai_provenance", "submission_versions", LEGACY_AI_PROVENANCE_CHECK)
