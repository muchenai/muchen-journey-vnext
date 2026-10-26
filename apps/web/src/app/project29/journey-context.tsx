"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { ProjectExperienceData } from "../project-ui/types";

export type JourneyContextValue = {
  learnerName: string;
  experience: ProjectExperienceData | null;
  initialScreen: "login" | "welcome" | "dashboard" | "tasks" | "detail" | "view" | "village" | "academy" | "guild";
  joinPhase: "invite" | "identity" | "feishu" | "nickname";
  joinError: string;
  initialNotice?: string;
};

const Context = createContext<JourneyContextValue | null>(null);

export function JourneyProvider({ value, children }: { value: JourneyContextValue; children: ReactNode }) {
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useJourney() {
  const value = useContext(Context);
  if (!value) throw new Error("Journey context is unavailable");
  return value;
}

export function useTaskStatus() {
  const { experience } = useJourney();
  return (index: number): "completed" | "pending" | "revision" | "active" | "locked" => {
    const node = experience?.journeyTasks.find(item => item.position === index + 1);
    if (!node && experience?.journeyTasks.length === 0) return index === 0 ? "active" : "locked";
    if (!node || node.status === "LOCKED") return "locked";
    if (["SUBMITTED", "IN_REVIEW"].includes(node.assignmentStatus ?? "")) return "pending";
    if (node.assignmentStatus === "NEEDS_REVISION") return "revision";
    if (node.isRevising) return "active";
    return node.status === "COMPLETED" ? "completed" : "active";
  };
}
