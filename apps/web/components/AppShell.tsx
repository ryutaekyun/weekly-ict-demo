"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getCurrentUser, logout, UnauthorizedError, type CurrentUser } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/labels";

const NAV_ITEMS: { href: string; label: string; disabled?: boolean }[] = [
  { href: "/dashboard", label: "통합 대시보드" },
  { href: "/documents", label: "ICT 정보 수집" },
  { href: "/issues", label: "핵심 이슈 분석" },
  { href: "/candidates", label: "후보주제 선정·검토" },
  { href: "/manuscripts", label: "연구·집필 작업실" },
  { href: "/reports", label: "보고서·요약본 제작" },
  { href: "/card-news", label: "카드뉴스 제작" },
  { href: "/followups", label: "후속 규정 알림" },
  { href: "/journal", label: "주간기술동향지 편집" },
  { href: "/sources", label: "출처·수집 관리" },
  { href: "/settings", label: "사용자 및 운영 설정" },
  { href: "/publications", label: "발간·배포 관리 (추후 개발)", disabled: true },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [checking, setChecking] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch((err) => {
        if (err instanceof UnauthorizedError) {
          router.replace(`/login?next=${encodeURIComponent(pathname ?? "/dashboard")}`);
          return;
        }
      })
      .finally(() => setChecking(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = search.trim();
    router.push(q ? `/documents?q=${encodeURIComponent(q)}` : "/documents");
  }

  if (checking) {
    return <div style={{ padding: 32, color: "var(--ink-muted)" }}>세션 확인 중...</div>;
  }
  if (!user) {
    return null; // 리다이렉트 중
  }
  const external = user.role === "author" || user.role === "ext_reviewer";
  const internalReviewer = user.role === "reviewer";
  const navItems = external ? [{ href: "/portal", label: "원고 포털" }]
    : internalReviewer ? [{ href: "/portal", label: "내 검토 배정" }, ...NAV_ITEMS.filter((i) => !i.href.startsWith("/journal"))]
    : NAV_ITEMS;

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <aside
        style={{
          width: 230,
          flexShrink: 0,
          background: "var(--navy)",
          color: "#fff",
          padding: "20px 14px",
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 15, padding: "0 10px 18px" }}>TNP AI Platform</div>
        {navItems.map((item) => {
          const active = pathname?.startsWith(item.href);
          if (item.disabled) {
            return (
              <div
                key={item.href}
                title="다음 단계(Phase 3)에서 개발 예정입니다"
                style={{
                  padding: "9px 10px",
                  borderRadius: 8,
                  fontSize: 13,
                  color: "rgba(255,255,255,0.38)",
                  cursor: "not-allowed",
                }}
              >
                {item.label}
              </div>
            );
          }
          return (
            <Link
              key={item.href}
              href={item.href}
              style={{
                padding: "9px 10px",
                borderRadius: 8,
                fontSize: 13.5,
                fontWeight: active ? 700 : 500,
                color: "#fff",
                textDecoration: "none",
                background: active ? "rgba(255,255,255,0.14)" : "transparent",
              }}
            >
              {item.label}
            </Link>
          );
        })}
      </aside>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            padding: "12px 24px",
            borderBottom: "1px solid var(--border)",
            background: "var(--panel)",
          }}
        >
          {external ? <div style={{ flex: 1 }} /> : <form onSubmit={handleSearch} style={{ display: "flex", gap: 8, flex: 1, maxWidth: 420 }}>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="제목 키워드로 수집자료 검색"
              style={{ flex: 1, padding: "8px 11px", borderRadius: 8, border: "1px solid var(--border)", fontSize: 13 }}
            />
            <button type="submit" className="tbtn">
              검색
            </button>
          </form>}
          <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 13 }}>
            <span style={{ color: "var(--ink-muted)" }}>
              {user.display_name} · {ROLE_LABELS[user.role] ?? user.role}
            </span>
            <button className="tbtn" onClick={handleLogout}>
              로그아웃
            </button>
          </div>
        </header>
        <main style={{ flex: 1, padding: 24, maxWidth: 1180, width: "100%", margin: "0 auto" }}>{children}</main>
      </div>
    </div>
  );
}

export function useRequireRole(user: CurrentUser | null, roles: string[]): boolean {
  if (!user) return false;
  return roles.includes(user.role);
}
