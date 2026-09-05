import type { NextConfig } from "next";

/**
 * The backend is reached through a rewrite rather than by calling it directly from the browser.
 *
 * One origin means no CORS configuration on the FastAPI side and no preflight on every request, and
 * it means the API base never appears in client bundles. When this deploys behind a single domain the
 * rewrite target changes and nothing in the application code does.
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
