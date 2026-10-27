/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // E2E 전용 화면 서버는 별도 빌드 폴더를 써서 개발 서버(.next)와 충돌하지 않는다
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

module.exports = nextConfig;
