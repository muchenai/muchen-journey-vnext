import Link from "next/link";
import type { MouseEventHandler, ReactNode } from "react";

type LearnerBackProps = {
  children: ReactNode;
  className?: string;
  title?: string;
  "aria-label"?: string;
} & (
  | { href: string; onClick?: never }
  | { href?: never; onClick: MouseEventHandler<HTMLButtonElement> }
);

export function LearnerBack({ children, className, href, onClick, ...attributes }: LearnerBackProps) {
  const classes = className ? `learner-back-control ${className}` : "learner-back-control";
  if (href !== undefined) {
    return <Link href={href} className={classes} {...attributes}>{children}</Link>;
  }
  return <button type="button" data-page-navigation onClick={onClick} className={classes} {...attributes}>{children}</button>;
}
