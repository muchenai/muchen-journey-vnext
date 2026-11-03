import type { BadgeArtworkLevel } from "./badgeArtwork";

// The original frame's circle is centered at (120,109) in a 240×260 viewBox.
export function BadgeArtworkImage({ path, level, large = false }: {
  path: string;
  level: BadgeArtworkLevel;
  large?: boolean;
}) {
  return <div className={`badge-medal badge-medal-centered${large ? " badge-medal-large" : ""}`} data-level={level} aria-hidden="true">
    <div className="badge-medal-composition">
      <img className="badge-medal-frame" src={`/assets/journey-badges/frames/${level === 0 ? "locked" : `level-${level}`}.svg`} alt="" draggable={false} />
      <div className="badge-medal-symbol-box"><img className="badge-medal-symbol" src={`/assets/journey-badges/centered-icons/${path}.webp`} loading="lazy" decoding="async" alt="" draggable={false} /></div>
    </div>
  </div>;
}
