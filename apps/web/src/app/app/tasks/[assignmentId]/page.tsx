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
