"use client";

import { useFormStatus } from "react-dom";

export function JoinSubmitButton({
  idleLabel,
  pendingLabel,
}: {
  idleLabel: string;
  pendingLabel: string;
}) {
  const { pending } = useFormStatus();

  return (
    <button className="button primary" type="submit" disabled={pending}>
      <span aria-hidden="true" className="join-button-mark">▶</span>
      <span>{pending ? pendingLabel : idleLabel}</span>
      <span aria-hidden="true" className="join-button-arrow">→</span>
    </button>
  );
}
