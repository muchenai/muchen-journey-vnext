import { createContext, useContext, type ReactNode } from "react";
import type { DashboardTaskEntry } from "./DashboardTaskGrid";

const DashboardSearchContext = createContext({ query: "", onClearSearch: () => {} });

export function DashboardSearchProvider({ query, onClearSearch, children }: {
  query: string;
  onClearSearch: () => void;
  children: ReactNode;
}) {
  return <DashboardSearchContext.Provider value={{ query, onClearSearch }}>{children}</DashboardSearchContext.Provider>;
}

export function useDashboardSearch() {
  return useContext(DashboardSearchContext);
}

export function filterDashboardTasks(entries: DashboardTaskEntry[], query: string) {
  const keyword = query.trim().toLowerCase();
  if (!keyword) return entries;
  return entries.filter(({ task }) => [task.title, task.name, task.description]
    .some(value => value.toLowerCase().includes(keyword)));
}
