import { redirect } from "next/navigation";
import { apiRequest } from "@/lib/server/api";
import ProjectExperience from "@/app/project29/App";
import { loadProjectExperience } from "@/app/project-ui/experience-data";


export const dynamic = "force-dynamic";

export default async function TaskPage({
  params,
  searchParams,
}: {
  params: Promise<{ assignmentId: string }>;
  searchParams: Promise<{ view?: string }>;
}) {
  const [{ assignmentId }, query] = await Promise.all([params, searchParams]);
  {
    let taskId: string | null = null;
    try { taskId = (await apiRequest<{taskId:string|null}>(`/api/v1/me/novice/assignments/${assignmentId}`, "LEARNER")).taskId; } catch { /* Existing page handles authentication errors. */ }
    if (taskId) redirect(`/app?view=village&task=${encodeURIComponent(taskId)}`);
  }
  const { learnerName, experience } = await loadProjectExperience(assignmentId);
  const screen = query.view === "evidence" || query.view === "review" ? "view" : "detail";
  return (
    <ProjectExperience
      key={`${assignmentId}:${screen}`}
      initialScreen={screen}
      joinPhase="invite"
      joinError=""
      learnerName={learnerName}
      experience={experience}
    />
  );
}
