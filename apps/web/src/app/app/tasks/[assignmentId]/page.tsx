import { redirect } from "next/navigation";
import { learnerPageRequest } from "@/lib/server/api";
import ProjectExperience from "@/app/project29/App";
import CompanyLoginNotice from "@/app/project-ui/CompanyLoginNotice";
import { loadLearnerProfile, loadProjectExperience } from "@/app/project-ui/experience-data";

import { localVillagePreviewEnabled } from "@/lib/server/local-preview";

export const dynamic = "force-dynamic";

export default async function TaskPage({
  params,
  searchParams,
}: {
  params: Promise<{ assignmentId: string }>;
  searchParams: Promise<{ view?: string }>;
}) {
  const [{ assignmentId }, query] = await Promise.all([params, searchParams]);
  const destination = await learnerPageRequest<{
    module: "exploration" | "village" | "legacy";
    taskId: string | null;
  }>(`/api/v1/me/assignments/${encodeURIComponent(assignmentId)}/destination`);
  if (destination.module === "exploration" && destination.taskId) {
    redirect(`/app?view=tasks&task=${encodeURIComponent(destination.taskId)}${query.view === "review" ? "&feedback=1" : ""}`);
  }
  if (destination.module === "village") {
    const profile = await loadLearnerProfile();
    if (profile.exploration_only !== false) return <CompanyLoginNotice />;
    if (destination.taskId) {
      redirect(`/app?view=village&task=${encodeURIComponent(destination.taskId)}`);
    }
  }
  const { learnerName, experience, explorationOnly } = await loadProjectExperience(assignmentId);
  const screen = query.view === "evidence" || query.view === "review" ? "view" : "detail";
  return (
    <ProjectExperience
      key={`${assignmentId}:${screen}`}
      initialScreen={screen}
      joinPhase="invite"
      joinError=""
      learnerName={learnerName}
      explorationOnly={explorationOnly}
      experience={experience}
      configurableExploration={false}
      localVillagePreview={localVillagePreviewEnabled()}
    />
  );
}
