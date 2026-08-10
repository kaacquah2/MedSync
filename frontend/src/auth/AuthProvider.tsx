/**
 * AuthProvider — global auth context for the SPA.
 *
 * On mount: fetches /api/csrf/ to get CSRF cookie, then /api/me/ via React Query
 * to get the current user. Using useQuery means the user object participates in
 * the Query cache lifecycle (stale detection, background refetch, cache invalidation).
 *
 * Navigation on auth failure: listens for 'auth:redirect' custom events dispatched
 * by the Axios response interceptor (avoids full-page window.location.href reloads).
 *
 * MFA routing: after a successful login, immediately checks MFA status and navigates
 * to /mfa/setup or /mfa/verify if enforcement requires it.
 *
 * On logout: purges React Query cache (`queryClient.clear()`) and wipes browser
 * storage (`localStorage.clear()`, `sessionStorage.clear()`) to guarantee no PHI
 * or stale data leaks between sessions.
 */

import React, { createContext, useContext, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchCsrf,
  fetchMe,
  fetchMfaStatus,
  login as apiLogin,
  logout as apiLogout,
} from "@/api/endpoints";
import type { CurrentUser } from "@/types";

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // User state is managed by React Query so it participates in the cache lifecycle
  const {
    data: user = null,
    isLoading: loading,
    refetch,
  } = useQuery<CurrentUser | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        await fetchCsrf();
        const res = await fetchMe();
        return res.data;
      } catch {
        return null;
      }
    },
    retry: false,
    staleTime: 5 * 60 * 1000,  // 5 minutes — re-validate at most once per shift segment
    gcTime: 10 * 60 * 1000,    // 10 minutes garbage collection
  });

  async function refresh() {
    await refetch();
  }

  // Listen for auth redirect events dispatched by the Axios interceptor
  // (replaces window.location.href = "/spa/login" with SPA navigation)
  useEffect(() => {
    function handleAuthRedirect(event: Event) {
      let path = (event as CustomEvent<{ path: string }>).detail?.path ?? "/login";
      if (path.startsWith("/spa/")) {
        path = path.slice(4);
      }
      navigate(path, { replace: true });
    }
    window.addEventListener("auth:redirect", handleAuthRedirect);
    return () => window.removeEventListener("auth:redirect", handleAuthRedirect);
  }, [navigate]);

  async function login(username: string, password: string) {
    await fetchCsrf();
    const res = await apiLogin(username, password);
    // Seed the query cache so components immediately see the new user
    queryClient.setQueryData<CurrentUser>(["me"], res.data);

    // Immediately check MFA enforcement so the user is routed to setup/verify
    // before the caller navigates to the dashboard.
    try {
      const mfaRes = await fetchMfaStatus();
      const mfa = mfaRes.data;
      if (mfa.mfa_enforced && mfa.role_requires_mfa && !mfa.mfa_verified_this_session) {
        navigate(mfa.mfa_enabled ? "/mfa/verify" : "/mfa/setup", { replace: true });
        return;
      }
    } catch {
      // If MFA status check fails, the axios interceptor handles enforcement
    }

    navigate("/", { replace: true });
  }

  async function logout() {
    try { await apiLogout(); } catch { /* ignore */ }

    // Purge in-memory React Query cache completely
    queryClient.clear();
    queryClient.resetQueries();

    // Clear persistent browser storage (PHI protection)
    localStorage.clear();
    sessionStorage.clear();

    navigate("/login", { replace: true });
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
