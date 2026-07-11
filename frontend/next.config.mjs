/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy API calls to the FastAPI backend so the browser uses same-origin.
    const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${base}/api/:path*` }];
  },
};
export default nextConfig;
