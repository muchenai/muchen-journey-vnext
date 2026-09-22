"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useWriteCooldown() {
  const deadline = useRef(0);
  const [remaining, setRemaining] = useState(0);
  const wait = useCallback((seconds: number) => {
    deadline.current = Date.now() + seconds * 1000;
    setRemaining(Math.ceil(seconds));
  }, []);
  const active = remaining > 0;
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      setRemaining(Math.max(0, Math.ceil((deadline.current - Date.now()) / 1000)));
    }, 250);
    return () => window.clearInterval(timer);
  }, [active]);
  const isWaiting = useCallback(() => Date.now() < deadline.current, []);
  return { remaining, wait, isWaiting };
}
