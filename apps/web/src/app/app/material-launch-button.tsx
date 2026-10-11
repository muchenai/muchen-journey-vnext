"use client";

export function MaterialLaunchButton({
  href,
  children,
}: {
  href: string | null;
  children: React.ReactNode;
}) {
  return (
    <button
      className="camp-action-button camp-action-primary"
      type="submit"
      onClick={() => {
        if (href) window.open(href, "_blank", "noopener,noreferrer");
      }}
    >
      <span aria-hidden="true">▶</span>
      {children}
    </button>
  );
}
