import ProjectExperience from "@/app/project29/App";
import { loadProjectExperience } from "@/app/project-ui/experience-data";

import { localVillagePreviewEnabled } from "@/lib/server/local-preview";

export const dynamic = "force-dynamic";

export default async function LearnerHome({ searchParams }: { searchParams: Promise<{ view?: string; notice?: string; task?: string; feedback?: string }> }) {
  const query = await searchParams;
  const legacyTasks = query.view === "legacy-tasks";
  const initialScreen = query.view === "village" ? "village" : query.view === "tasks" || legacyTasks ? "tasks" : query.view === "dashboard" ? "dashboard" : "welcome";
  // The introduction precedes nickname setup; the dashboard shows the required
  // modal after the learner clicks 开启旅程. Task deep links remain gated.
  const { learnerName, experience, needsNickname } = await loadProjectExperience(undefined, initialScreen !== "tasks");
  return (
    <ProjectExperience
      initialScreen={initialScreen}
      joinPhase={needsNickname ? "nickname" : "invite"}
      joinError=""
      initialNotice={query.notice === "module-designing" ? "该功能正在设计" : undefined}
      learnerName={learnerName}
      experience={experience}
      configurableExploration={!legacyTasks}
      explorationTaskId={!legacyTasks && initialScreen === "tasks" && typeof query.task === "string" ? query.task : undefined}
      explorationOpenFeedback={!legacyTasks && initialScreen === "tasks" && !!query.task && query.feedback === "1"}
      localVillagePreview={localVillagePreviewEnabled()}
    />
  );
}
