export function formatApiError(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (!data) return fallback;
  if (typeof data === "string") return data;
  if (typeof data === "object") {
    if ("error" in data && typeof (data as { error: string }).error === "string") {
      return (data as { error: string }).error;
    }
    if ("detail" in data && typeof (data as { detail: string }).detail === "string") {
      return (data as { detail: string }).detail;
    }
    const messages: string[] = [];
    for (const [key, val] of Object.entries(data as Record<string, unknown>)) {
      if (Array.isArray(val)) {
        messages.push(`${key}: ${val.join(", ")}`);
      } else if (typeof val === "string") {
        messages.push(`${key}: ${val}`);
      }
    }
    if (messages.length > 0) return messages.join(" | ");
  }
  return fallback;
}
