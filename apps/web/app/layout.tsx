import "./globals.css";

export const metadata = {
  title: "TNP AI Platform",
  description: "ICT 정보조사·분석·집필·검수·발간 운영 시스템",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
