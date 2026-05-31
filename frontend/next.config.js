/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Backend URL passed at build/runtime via env
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
};

module.exports = nextConfig;
