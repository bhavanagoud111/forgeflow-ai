/**
 * Helpers for the server-side API proxy (app/api/ff/[...path]/route.ts).
 * Kept free of Next.js imports so they can be unit tested.
 */

const SEGMENT_RE = /^[A-Za-z0-9._~:@!$&'()*+,;=-]+$/;

/**
 * Validate the catch-all path segments and build the upstream path.
 * Only paths under `api/` are allowed; traversal and empty segments are rejected.
 * Returns null when the path is not allowed.
 */
export function buildUpstreamPath(segments: readonly string[] | undefined): string | null {
  if (!segments || segments.length < 2) return null;
  if (segments[0] !== "api") return null;
  for (const raw of segments) {
    let seg: string;
    try {
      seg = decodeURIComponent(raw);
    } catch {
      return null;
    }
    if (seg === "" || seg === "." || seg === "..") return null;
    if (seg.includes("/") || seg.includes("\\")) return null;
    if (!SEGMENT_RE.test(seg)) return null;
  }
  return "/" + segments.map((s) => encodeURIComponent(decodeURIComponent(s))).join("/");
}

/** Request headers forwarded to the backend. Cookies and auth from the browser are never forwarded. */
export const FORWARDED_REQUEST_HEADERS = ["accept", "content-type", "last-event-id"] as const;

/** Response headers passed back to the browser. */
export const FORWARDED_RESPONSE_HEADERS = [
  "content-type",
  "cache-control",
  "content-disposition",
  "retry-after",
  "x-request-id",
] as const;

export function upstreamBaseUrl(value: string | undefined): string {
  const base = (value && value.trim()) || "http://localhost:8000";
  return base.replace(/\/+$/, "");
}
