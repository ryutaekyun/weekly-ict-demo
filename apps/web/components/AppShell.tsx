"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getCurrentUser, logout, UnauthorizedError, type CurrentUser } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/labels";

type NavItem = { href: string; label: string; roles?: string[] };
type NavGroup = { title: string; items: NavItem[] };

// 연구원이 매일 쓰는 순서: 오늘 할 일 → 자료 조사 → 집필·발간 → 관리
const NAV_GROUPS: NavGroup[] = [
  { title: "업무", items: [{ href: "/dashboard", label: "통합 대시보드" }] },
  {
    title: "조사",
    items: [
      { href: "/documents", label: "ICT 정보 수집" },
      { href: "/issues", label: "핵심 이슈 분석" },
      { href: "/candidates", label: "후보주제 선정·검토" },
    ],
  },
  {
    title: "집필·발간",
    items: [
      { href: "/manuscripts", label: "연구·집필 작업실" },
      { href: "/reports", label: "보고서·요약본 제작" },
      { href: "/card-news", label: "카드뉴스 제작" },
      { href: "/followups", label: "후속 규정 알림" },
      { href: "/journal", label: "주간기술동향지 편집" },
    ],
  },
  {
    title: "관리",
    items: [
      { href: "/sources", label: "출처·수집 관리" },
      { href: "/admin/users", label: "사용자 관리", roles: ["admin"] },
      { href: "/settings", label: "사용자 및 운영 설정" },
      { href: "/guide", label: "서비스 소개" },
    ],
  },
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

  if (checking) return <div style={{ padding: 32, color: "var(--ink-muted)" }} role="status">세션 확인 중...</div>;
  if (!user) return null; // 로그인 화면으로 이동 중

  const external = user.role === "author" || user.role === "ext_reviewer";
  const internalReviewer = user.role === "reviewer";
  const groups: NavGroup[] = external
    ? [{ title: "원고", items: [{ href: "/portal", label: "원고 포털" }] }]
    : NAV_GROUPS.map((g) => ({
        ...g,
        items: g.items.filter((i) => (!i.roles || i.roles.includes(user.role)) && !(internalReviewer && i.href.startsWith("/journal"))),
      })).concat(internalReviewer ? [{ title: "검토", items: [{ href: "/portal", label: "내 검토 배정" }] }] : []);

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <aside style={{ width: 236, flexShrink: 0, background: "var(--navy)", color: "#fff", padding: "20px 12px", display: "flex", flexDirection: "column" }} aria-label="주 메뉴">
        <Link href="/dashboard" style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 10px 14px", color: "#fff", textDecoration: "none" }}>
          <span aria-hidden style={{ width: 28, height: 28, borderRadius: 8, background: "var(--accent)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 13, color: "var(--navy)" }}>T</span>
          <span style={{ fontWeight: 700, fontSize: 15, lineHeight: 1.2 }}>TNP AI Platform<br /><span style={{ fontSize: 11, fontWeight: 400, opacity: 0.7 }}>ICT 정보조사·연구관리</span></span>
        </Link>
        <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {groups.map((g) => (
            <div key={g.title}>
              <div className="app-nav-group">{g.title}</div>
              {g.items.map((item) => {
                const active = pathname === item.href || pathname?.startsWith(item.href + "/");
                return (
                  <Link key={item.href} href={item.href} className={`app-nav-link${active ? " active" : ""}`} aria-current={active ? "page" : undefined}>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, padding: "12px 28px", borderBottom: "1px solid var(--border)", background: "var(--panel)" }}>
          {external ? <div style={{ flex: 1 }} /> : (
            <form onSubmit={handleSearch} role="search" style={{ display: "flex", gap: 8, flex: 1, maxWidth: 480 }}>
              <input aria-label="수집자료 통합 검색" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="제목 키워드로 수집자료 검색"
                style={{ flex: 1, padding: "9px 12px", borderRadius: 8, border: "1px solid var(--border)", fontSize: 13.5, background: "var(--panel-2)" }} />
              <button type="submit" className="tbtn">검색</button>
            </form>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 13 }}>
            <Link href="/account" style={{ color: "var(--ink)", textDecoration: "none" }} title="내 정보">
              <b>{user.display_name}</b> <span className="badge">{ROLE_LABELS[user.role] ?? user.role}</span>
            </Link>
            <button className="tbtn" onClick={handleLogout}>로그아웃</button>
          </div>
        </header>
        <main style={{ flex: 1, padding: "28px 32px", maxWidth: 1240, width: "100%", margin: "0 auto" }}>{children}</main>
      </div>
    </div>
  );
}

export function useRequireRole(user: CurrentUser | null, roles: string[]): boolean {
  if (!user) return false;
  return roles.includes(user.role);
}
