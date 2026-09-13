import type { NextConfig } from "next";

/**
 * The backend is reached through a rewrite rather than by calling it directly from the browser.
 *
 * One origin means no CORS configuration on the FastAPI side and no preflight on every request, and
 * it means the API base never appears in client bundles. When this deploys behind a single domain the
 * rewrite target changes and nothing in the application code does.
 *
 * Compression is left on, and the chat's stream stays out of it by sending `no-transform` rather
 * than by turning it off here. Next gzips proxied responses too, and gzip holds bytes back until it
 * has a block worth compressing, so the whole reply used to reach the browser in one flush and the
 * words appeared at once instead of forming. `compress: false` fixed that and cost the bundles their
 * gzip, which is too much to give up for one route. Setting `Content-Encoding` on the FastAPI side
 * does not work either - it is overwritten on the way through. What does work is `Cache-Control:
 * no-transform` on the streaming response, which is the standard way to tell any compressing proxy
 * to pass a body along untouched, so it keeps working in front of a CDN as well.
 */
const backendOrigin = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendOrigin}/api/v1/:path*`,
      },
      {
        source: "/health",
        destination: `${backendOrigin}/health`,
      },
    ];
  },
};

export default nextConfig;
