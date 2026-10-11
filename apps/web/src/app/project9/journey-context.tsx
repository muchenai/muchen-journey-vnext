"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { ProjectExperienceData } from "../project-ui/types";

export type JourneyContextValue = {
  learnerName: string;
  experience: ProjectExperienceData | null;
  initialScreen: "login" | "welcome" | "dashboard" | "tasks" | "detail" | "view";
  joinPhase: "invite" | "identity" | "feishu";
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
  return (index: number): "completed" | "active" | "locked" => {
    if (experience && experience.journeyTasks.length === 0) {
      return index === 0 ? "active" : "locked";
    }
    const status = experience?.journeyTasks.find(item => item.position === index + 1)?.status;
    return status === "COMPLETED" ? "completed" : status === "CURRENT" ? "active" : "locked";
  };
}
