"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, type CurrentUser } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  useEffect(() => {
    apiFetch<CurrentUser>("/auth/me")
      .then(() => router.replace("/candidates"))
      .catch(() => router.replace("/login"));
  }, [router]);
  return null;
}
