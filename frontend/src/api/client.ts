/**
 * Axios client configured for Django session + CSRF auth.
 *
 * Every unsafe request (POST/PUT/PATCH/DELETE) automatically includes the
 * X-CSRFToken header read from the Django csrftoken cookie, which DRF's
 * SessionAuthentication validates. Also attaches Bearer token if present.
 *
 * Navigation on auth failure (401/403-MFA) is handled by dispatching a custom
 * 'auth:redirect' DOM event instead of window.location.href, keeping navigation
 * inside the React Router SPA and preserving in-memory state.
 */

import axios from "axios";

export interface NormalizedApiError {
  message: string;
  status: number;
  details?: Record<string, string[]>;
  raw?: unknown;
}

export function normalizeApiError(err: unknown): NormalizedApiError {
  if (!err || typeof err !== "object") {
    return { message: "An unexpected error occurred", status: 500 };
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const axiosErr = err as any;
  const status = axiosErr.response?.status ?? 500;
  const data = axiosErr.response?.data;

  if (typeof data === "string" && data.trim()) {
    return { message: data, status };
  }

  if (data && typeof data === "object") {
    if (typeof data.detail === "string") {
      return { message: data.detail, status, raw: data };
    }
    if (typeof data.error === "string") {
      return { message: data.error, status, raw: data };
    }
    // DRF validation errors like { field: ["Error text"] }
    const details: Record<string, string[]> = {};
    const msgs: string[] = [];
    for (const [k, v] of Object.entries(data)) {
      if (Array.isArray(v)) {
        details[k] = v.map(String);
        msgs.push(`${k}: ${v.join(", ")}`);
      } else if (typeof v === "string") {
        details[k] = [v];
        msgs.push(`${k}: ${v}`);
      }
    }
    if (msgs.length > 0) {
      return { message: msgs.join(" | "), status, details, raw: data };
    }
  }

  return {
    message: axiosErr.message || "An unexpected error occurred",
    status,
    raw: data,
  };
}

/**
 * Dispatch a client-side auth redirect event.
 * AuthProvider listens to 'auth:redirect' and calls React Router's navigate()
 * so the SPA never does a full-page reload on auth failure.
 */
export function dispatchAuthRedirect(path: string): void {
  window.dispatchEvent(new CustomEvent("auth:redirect", { detail: { path } }));
}

function getCookie(name: string): string {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()!.split(";").shift() ?? "";
  return "";
}

const api = axios.create({
  baseURL: "/api",
  withCredentials: true,        // send the session cookie cross-origin in dev
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// CSRF interceptor
api.interceptors.request.use((config) => {
  // Attach X-CSRFToken header for unsafe HTTP methods
  const unsafe = ["post", "put", "patch", "delete"];
  if (config.method && unsafe.includes(config.method.toLowerCase())) {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) {
      config.headers["X-CSRFToken"] = csrfToken;
    }
  }
  return config;
});

// Global response interceptor for 401/419 refresh/redirect & error normalization
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status;
    err.normalized = normalizeApiError(err);

    // 401 / 419 → session expired, CSRF failure, or unauthenticated.
    // Skip the redirect for /api/me/ — AuthProvider handles that 401 by setting
    // user=null and letting React Router navigate to /login client-side.
    if (status === 401 || status === 419) {
      const url = err.config?.url ?? "";
      if (!url.includes("/me/")) {
        // Use SPA navigation instead of full-page reload to preserve React state
        dispatchAuthRedirect("/login");
      }
      return Promise.reject(err);
    }

    // 403 with mfa_required → MFA enforcement middleware blocked the request
    if (status === 403 && err.response?.data?.mfa_required) {
      const dest: string = err.response.data.redirect ?? "/mfa/verify";
      dispatchAuthRedirect(dest);
      return Promise.reject(err);
    }

    return Promise.reject(err);
  }
);

export default api;
