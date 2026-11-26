import ProjectExperience from "@/app/project29/App";
import CompanyLoginNotice from "@/app/project-ui/CompanyLoginNotice";
import { loadLearnerProfile, loadProjectExperience } from "@/app/project-ui/experience-data";
import { explorationOnlyMessage, isCompanyModule } from "@/lib/learner-module-access";

import { localVillagePreviewEnabled } from "@/lib/server/local-preview";

export const dynamic = "force-dynamic";

export default async function LearnerHome({ searchParams }: { searchParams: Promise<{ view?: string; notice?: string; task?: string; feedback?: string; course?: string; section?: string; q?: string }> }) {
  const query = await searchParams;
  const legacyTasks = query.view === "legacy-tasks";
  const profile = isCompanyModule(query.view) ? await loadLearnerProfile() : undefined;
  if (profile && profile.exploration_only !== false) return <CompanyLoginNotice />;
  const initialScreen = isCompanyModule(query.view) ? query.view : query.view === "tasks" || legacyTasks ? "tasks" : query.view === "dashboard" ? "dashboard" : "welcome";
  // The introduction precedes nickname setup; the dashboard shows the required
  // modal after the learner clicks 开启旅程. Task deep links remain gated.
  const { learnerName, experience, needsNickname, explorationOnly } = await loadProjectExperience(undefined, initialScreen !== "tasks", profile);
  return (
    <ProjectExperience
      initialScreen={initialScreen}
      academyEntry={initialScreen === "academy" || initialScreen === "village" ? {
        courseId: typeof query.course === "string" ? query.course : undefined,
        section: typeof query.section === "string" ? query.section : undefined,
        query: typeof query.q === "string" ? query.q : undefined,
      } : undefined}
      joinPhase={needsNickname ? "nickname" : "invite"}
      joinError=""
      initialNotice={explorationOnly && query.notice === "exploration-only" ? explorationOnlyMessage : query.notice === "module-designing" ? "该功能正在设计" : undefined}
      learnerName={learnerName}
      explorationOnly={explorationOnly}
      experience={experience}
      configurableExploration={!legacyTasks}
      explorationTaskId={!legacyTasks && initialScreen === "tasks" && typeof query.task === "string" ? query.task : undefined}
      explorationOpenFeedback={!legacyTasks && initialScreen === "tasks" && !!query.task && query.feedback === "1"}
      localVillagePreview={localVillagePreviewEnabled()}
    />
  );
}
