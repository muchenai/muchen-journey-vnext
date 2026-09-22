export function effectiveCharacterCount(value: string): number {
  return Array.from(value.trim()).length;
}

export function textLengthIsValid(
  value: string,
  minimum: number,
  maximum: number,
  optional = false,
): boolean {
  const count = effectiveCharacterCount(value);
  return (optional && count === 0) || (count >= minimum && count <= maximum);
}
