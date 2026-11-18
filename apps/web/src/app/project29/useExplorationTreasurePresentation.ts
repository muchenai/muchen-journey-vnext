"use client";

import { useCallback, useState } from "react";
import type { ExplorationTreasureDrop, ExplorationTreasures } from "@/lib/exploration-treasures";

type Presentation = { active: ExplorationTreasureDrop | null; settled: ReadonlySet<string> };

export function useExplorationTreasurePresentation({ treasures, enabled, busy, collectionOpen }: {
  treasures: ExplorationTreasures;
  enabled: boolean;
  busy: boolean;
  collectionOpen: boolean;
}) {
  const [presentation, setPresentation] = useState<Presentation>(() => ({ active: null, settled: new Set() }));
  const candidate = enabled && !busy && !collectionOpen
    ? treasures.pendingDrops.find(item => !item.acknowledgedAt && !presentation.settled.has(item.id)) ?? null
    : null;
  // Block continuation in the very render that discovers a drop, before effects
  // open its dialog. Hold that drop while its acknowledgment updates the server.
  const drop = presentation.active ?? candidate;
  if (!presentation.active && candidate) {
    setPresentation({ ...presentation, active: candidate });
  }
  const dismiss = useCallback((id: string) => {
    setPresentation(previous => {
      const settled = new Set(previous.settled);
      settled.add(id);
      return { settled, active: previous.active?.id === id ? null : previous.active };
    });
  }, []);
  return { drop, blocking: drop !== null, dismiss };
}
