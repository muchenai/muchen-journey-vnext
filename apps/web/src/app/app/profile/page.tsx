import { redirect } from "next/navigation";
import ProjectExperience from "@/app/project29/App";
import { learnerPageRequest } from "@/lib/server/api";
import { loadProjectExperience } from "@/app/project-ui/experience-data";

export const dynamic = "force-dynamic";

export default async function LearnerProfilePage() {
  const profile = await learnerPageRequest<{ needs_nickname: boolean }>("/api/v1/me/learner-profile");
  if (!profile.needs_nickname) redirect("/app");
  const { learnerName, experience } = await loadProjectExperience(undefined, true);
  return <ProjectExperience initialScreen="welcome" joinPhase="nickname" joinError="" learnerName={learnerName} experience={experience} />;
}
