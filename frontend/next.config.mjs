/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  outputFileTracingRoot: new URL(".", import.meta.url).pathname,
  async rewrites() {
    // Only proxy /api → FastAPI during local `next dev`. On Vercel, proxying to
    // 127.0.0.1 breaks (private hostname / no backend on the edge).
    if (process.env.VERCEL || process.env.NODE_ENV !== "development") {
      return [];
    }
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
