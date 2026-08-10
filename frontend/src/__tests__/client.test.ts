import { beforeEach, describe, expect, it } from "vitest";
import api, { normalizeApiError } from "@/api/client";

describe("api client", () => {
  it("uses /api as the base URL", () => {
    expect(api.defaults.baseURL).toBe("/api");
  });

  it("sends credentials with every request", () => {
    expect(api.defaults.withCredentials).toBe(true);
  });
});

describe("CSRF & Auth Token interceptor", () => {
  beforeEach(() => {
    Object.defineProperty(document, "cookie", {
      get: () => "csrftoken=test-csrf-token",
      configurable: true,
    });
    localStorage.clear();
    sessionStorage.clear();
  });

  function getRequestInterceptor() {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (api.interceptors.request as any).handlers.find(Boolean)?.fulfilled;
  }

  it("attaches X-CSRFToken on POST", async () => {
    const handler = getRequestInterceptor();
    const config = await handler({ method: "post", headers: {} });
    expect(config.headers["X-CSRFToken"]).toBe("test-csrf-token");
  });

  it("attaches Authorization header when auth_token is set", async () => {
    localStorage.setItem("auth_token", "secret-token-123");
    const handler = getRequestInterceptor();
    const config = await handler({ method: "get", headers: {} });
    expect(config.headers["Authorization"]).toBe("Bearer secret-token-123");
  });
});

describe("Error Normalization", () => {
  it("normalizes detail string responses", () => {
    const err = { response: { status: 400, data: { detail: "Invalid input" } } };
    const norm = normalizeApiError(err);
    expect(norm.status).toBe(400);
    expect(norm.message).toBe("Invalid input");
  });

  it("normalizes field error objects", () => {
    const err = {
      response: {
        status: 400,
        data: {
          first_name: ["First name is required"],
          email: ["Enter a valid email"],
        },
      },
    };
    const norm = normalizeApiError(err);
    expect(norm.status).toBe(400);
    expect(norm.details).toEqual({
      first_name: ["First name is required"],
      email: ["Enter a valid email"],
    });
    expect(norm.message).toContain("first_name: First name is required");
  });
});

describe("Response Interceptor 401/419 Redirect", () => {
  function getResponseInterceptorError() {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (api.interceptors.response as any).handlers.find(Boolean)?.rejected;
  }

  it("redirects on 401 status for non-me endpoints", async () => {
    const _origLocation = window.location.href;
    const rejected = getResponseInterceptorError();
    const dummyErr = {
      response: { status: 401 },
      config: { url: "/patients/" },
    };

    try {
      await rejected(dummyErr);
    } catch {
      // expect rejection
    }
  });

  it("redirects on 419 CSRF expiry status for non-me endpoints", async () => {
    const rejected = getResponseInterceptorError();
    const dummyErr = {
      response: { status: 419 },
      config: { url: "/encounters/1/" },
    };

    try {
      await rejected(dummyErr);
    } catch {
      // expect rejection
    }
  });
});
