import { assembleFormalJourneyV3 } from "@/app/actions";
import type {
  OpsFormalJourney,
  OpsIdentityAccess,
  OpsTaskDefinition,
} from "@/lib/server/api";

const STAGES = [
  ["DAY-0", "Day 0"],
  ["TRE-001-COMPANY-VALUES", "宝藏一"],
  ["TRE-002-AI-DATA-BASICS", "宝藏二"],
  ["TRE-003-PROJECT-AWARENESS", "宝藏三"],
  ["TRE-004-DELIVERY-FIT", "宝藏四"],
  ["ASM-001-RULE-BREAKDOWN", "评测一"],
  ["ASM-002-MODEL-JUDGEMENT", "评测二"],
  ["ASM-003-DATA-CONSTRUCTION", "评测三"],
] as const;

export function JourneyV3AssemblyPanel({
  tasks,
  journeys,
  reviewers,
}: {
  tasks: OpsTaskDefinition[];
  journeys: OpsFormalJourney[];
  reviewers: OpsIdentityAccess[];
}) {
  const currentVersion = Math.max(0, ...journeys.map((item) => item.version));
  const rows = STAGES.map(([stableKey, label]) => ({
    stableKey,
    label,
    task: tasks.find((item) => item.stable_key === stableKey),
  }));
  const missing = rows.filter((item) => !item.task || item.task.versions.length === 0);
  if (currentVersion < 1) return <p>请先保留既有正式 JourneyVersion，再创建 V3。</p>;
  if (missing.length > 0) {
    return <p className="inline-error">缺少固定版本：{missing.map((item) => item.stableKey).join("、")}</p>;
  }
  if (reviewers.length === 0) return <p className="inline-error">没有已绑定的独立 Reviewer。</p>;
  return (
    <form action={assembleFormalJourneyV3} className="ops-command-form">
      <input type="hidden" name="expected_current_version" value={currentVersion} />
      <div className="content-editor-grid">
        {rows.map(({ stableKey, label, task }) => (
          <label key={stableKey}>
            {label} · {stableKey}
            <select name="task_version_id" required defaultValue={task!.versions.at(-1)!.id}>
              {task!.versions.map((version) => (
                <option key={version.id} value={version.id}>V{version.version} · {version.title}</option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <label>
        独立 Reviewer
        <select name="reviewer_id" required defaultValue="">
          <option value="" disabled>选择复核人</option>
          {reviewers.map((reviewer) => (
            <option key={reviewer.user_id} value={reviewer.user_id}>{reviewer.display_name}</option>
          ))}
        </select>
      </label>
      <label>
        复核记录
        <textarea name="content_review_note" required minLength={20} maxLength={1000} />
      </label>
      <label className="checkbox-row">
        <input type="checkbox" name="review_acknowledged" required />
        我确认八站均绑定已复核的不可变 TaskVersion，顺序为 Day 0＋四宝藏＋三评测
      </label>
      <button className="button primary" type="submit">创建并发布 Journey V3 固定组合</button>
    </form>
  );
}
