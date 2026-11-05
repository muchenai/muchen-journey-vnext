import type { NextConfig } from "next";
import preloadAssets from "./src/app/project29/preloadAssets.json";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  experimental: {
    serverActions: { bodySizeLimit: "6mb" },
  },
  async headers() {
    return [
      ...preloadAssets.filter(source => /^\/world-map\/[a-f0-9]{16}\.webp$/.test(source)).map(source => ({
        source,
        headers: [{key:"Cache-Control", value:"public, max-age=31536000, immutable"}],
      })),
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
        ],
      },
      {
        source: "/api/learner/world-map",
        headers: [{ key: "X-Frame-Options", value: "SAMEORIGIN" }],
      },
    ];
  },
};

export default nextConfig;
