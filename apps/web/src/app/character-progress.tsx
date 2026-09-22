"use client";

import { effectiveCharacterCount } from "@/lib/text-length";

export function CharacterProgress({
  id,
  value,
  minimum,
  maximum,
  optional = false,
}: {
  id: string;
  value: string;
  minimum: number;
  maximum: number;
  optional?: boolean;
}) {
  const count = effectiveCharacterCount(value);
  const underMinimum = !optional && count < minimum;
  const overMaximum = count > maximum;
  const nearMaximum = !overMaximum && count >= Math.ceil(maximum * 0.9);
  const detail = underMinimum
    ? `｜还差 ${minimum - count} 个`
    : overMaximum
      ? `｜已超出 ${count - maximum} 个`
      : nearMaximum
        ? `｜还可输入 ${maximum - count} 个`
        : "";
  const requirement = optional
    ? `选填，最多 ${maximum}`
    : `要求 ${minimum}–${maximum}`;
  const state = overMaximum || underMinimum
    ? "invalid"
    : nearMaximum
      ? "warning"
      : "valid";

  return (
    <p
      id={id}
      className={`character-progress ${state}`}
      role="status"
      aria-live="polite"
    >
      已输入 {count} 个有效字符｜{requirement}{detail}
    </p>
  );
}
