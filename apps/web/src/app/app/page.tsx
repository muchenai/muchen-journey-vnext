import ProjectExperience from "@/app/project9/App";
import { loadProjectExperience } from "@/app/project-ui/experience-data";

export const dynamic = "force-dynamic";

export default async function LearnerHome({ searchParams }: { searchParams: Promise<{ view?: string; notice?: string }> }) {
  const query = await searchParams;
  const { learnerName, experience } = await loadProjectExperience();
  return (
    <ProjectExperience
      initialScreen={query.view === "tasks" ? "tasks" : query.view === "dashboard" ? "dashboard" : "welcome"}
      joinPhase="invite"
      joinError=""
      initialNotice={query.notice === "module-designing" ? "该功能正在设计" : undefined}
      learnerName={learnerName}
      experience={experience}
    />
  );
}
