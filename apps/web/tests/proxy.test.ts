import { describe, expect, it } from "vitest";
import { FORWARDED_REQUEST_HEADERS, buildUpstreamPath, upstreamBaseUrl } from "@/lib/proxy";

describe("buildUpstreamPath", () => {
  it("allows paths under api/", () => {
    expect(buildUpstreamPath(["api", "health"])).toBe("/api/health");
    expect(buildUpstreamPath(["api", "executions", "exec_1", "events"])).toBe("/api/executions/exec_1/events");
  });

  it("rejects paths outside api/", () => {
    expect(buildUpstreamPath(["docs"])).toBeNull();
    expect(buildUpstreamPath(["openapi.json"])).toBeNull();
    expect(buildUpstreamPath(["api"])).toBeNull();
    expect(buildUpstreamPath([])).toBeNull();
    expect(buildUpstreamPath(undefined)).toBeNull();
  });

  it("rejects traversal and encoded separators", () => {
    expect(buildUpstreamPath(["api", "..", "admin"])).toBeNull();
    expect(buildUpstreamPath(["api", "%2e%2e", "x"])).toBeNull();
    expect(buildUpstreamPath(["api", "a%2Fb"])).toBeNull();
    expect(buildUpstreamPath(["api", ""])).toBeNull();
    expect(buildUpstreamPath(["api", "a b"])).toBeNull();
  });
});

describe("proxy configuration", () => {
  it("never forwards cookies or browser authorization", () => {
    expect(FORWARDED_REQUEST_HEADERS).not.toContain("cookie");
    expect(FORWARDED_REQUEST_HEADERS).not.toContain("authorization");
    expect(FORWARDED_REQUEST_HEADERS).toContain("last-event-id");
  });

  it("normalizes the upstream base URL", () => {
    expect(upstreamBaseUrl(undefined)).toBe("http://localhost:8000");
    expect(upstreamBaseUrl("http://api:8000/")).toBe("http://api:8000");
  });
});
