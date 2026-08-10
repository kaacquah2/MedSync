import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/api/queryKeys";

describe("React Query Cache Scoping & Purging", () => {
  it("scopes cache keys with hospital_id and user_id", () => {
    const keyA = queryKeys.patients("hosp-A", "user-1", "john", 1);
    const keyB = queryKeys.patients("hosp-B", "user-2", "john", 1);

    expect(keyA).toEqual(["hosp-A", "user-1", "patients", "john", 1]);
    expect(keyB).toEqual(["hosp-B", "user-2", "patients", "john", 1]);
    expect(keyA).not.toEqual(keyB);
  });

  it("clears all cached query data when queryClient.clear() is invoked on logout", () => {
    const queryClient = new QueryClient();

    // Populate cache with Doctor A data
    const keyA = queryKeys.patients("hosp-A", "user-docA", "", 1);
    queryClient.setQueryData(keyA, {
      results: [{ universal_id: "NHID-0001", full_name: "Patient A of Doctor A" }],
      count: 1,
    });

    expect(queryClient.getQueryData(keyA)).toBeDefined();

    // Simulate logout action
    queryClient.clear();
    queryClient.resetQueries();

    // Verify Doctor A's cached data is completely purged
    expect(queryClient.getQueryData(keyA)).toBeUndefined();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });
});
