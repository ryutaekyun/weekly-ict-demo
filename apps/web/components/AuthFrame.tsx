"use client";

export default function AuthFrame({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24, background: "var(--bg)" }}>
      <div className="panel" style={{ width: 400, maxWidth: "100%", padding: "32px 32px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
          <span aria-hidden style={{ width: 32, height: 32, borderRadius: 9, background: "var(--navy)", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 800 }}>T</span>
          <div style={{ fontWeight: 700, fontSize: 15 }}>TNP AI Platform<div style={{ fontSize: 11.5, fontWeight: 400, color: "var(--ink-muted)" }}>ICT 정보조사·연구관리</div></div>
        </div>
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: "0 0 4px" }}>{title}</h1>
        <p style={{ color: "var(--ink-muted)", fontSize: 13, margin: "0 0 20px" }}>{subtitle}</p>
        {children}
        <div style={{ marginTop: 22, fontSize: 11.5, color: "var(--ink-muted)", textAlign: "center" }}>(주)테크노베이션파트너스</div>
      </div>
    </div>
  );
}
