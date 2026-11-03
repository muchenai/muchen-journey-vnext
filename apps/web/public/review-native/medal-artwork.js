// Explicit project36 shop bindings, not inferred from names or point types.
export const shopArtworkPaths = {
  'product-1': 'points/product/product-1',
  'tech-1': 'points/tech/tech-1',
  'data-3': 'points/data/data-3',
  'pmo-2': 'points/pmo/pmo-2',
  'ai-evaluation-2': 'points/ai-evaluation/ai-evaluation-2',
  'quality-1': 'points/quality/quality-1',
};
export function medalArtwork(medal) {
  const path = Object.hasOwn(shopArtworkPaths, medal.artworkId || '') && shopArtworkPaths[medal.artworkId];
  if (medal.image || !path) return null;
  const level = medal.style === 'gold' ? 3 : medal.style === 'purple' ? 2 : 1;
  return {
    frame: `/assets/journey-badges/frames/level-${level}.svg`,
    symbol: `/assets/journey-badges/centered-icons/${path}.webp`,
  };
}
