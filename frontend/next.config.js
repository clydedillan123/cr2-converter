/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Proxy /convert → Python backend (same container, port 8000)
  async rewrites() {
    return [
      {
        source: "/convert",
        destination: "http://localhost:8000/convert",
      },
    ];
  },
};

module.exports = nextConfig;
