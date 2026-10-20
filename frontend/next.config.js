/** @type {import('next').NextConfig} */
const nextConfig = {
  // App Router включён по умолчанию в Next.js 14
  // standalone — минимальный сервер для Docker-образа (см. frontend/Dockerfile)
  output: 'standalone',
};

module.exports = nextConfig;
