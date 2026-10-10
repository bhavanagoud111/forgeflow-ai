import { describe, expect, it } from "vitest";
import { buildFileTree } from "@/lib/file-tree";
import { formatDuration, formatRelative, parseTimestamp } from "@/lib/format";

describe("parseTimestamp", () => {
  it("treats timestamps without a zone as UTC", () => {
    expect(parseTimestamp("2026-10-10T16:36:52.478952")?.toISOString()).toBe("2026-10-10T16:36:52.478Z");
    expect(parseTimestamp("2026-10-10T16:36:52Z")?.toISOString()).toBe("2026-10-10T16:36:52.000Z");
    expect(parseTimestamp(null)).toBeNull();
    expect(parseTimestamp("nope")).toBeNull();
  });
});

describe("formatDuration", () => {
  it("formats milliseconds, seconds and minutes", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(15)).toBe("15 ms");
    expect(formatDuration(2500)).toBe("2.5 s");
    expect(formatDuration(22162)).toBe("22 s");
    expect(formatDuration(125000)).toBe("2m 5s");
  });
});

describe("formatRelative", () => {
  it("describes elapsed time", () => {
    const now = new Date("2026-10-10T17:00:00Z");
    expect(formatRelative("2026-10-10T16:59:30Z", now)).toBe("30s ago");
    expect(formatRelative("2026-10-10T15:00:00Z", now)).toBe("2h ago");
  });
});

describe("buildFileTree", () => {
  it("nests paths and sorts directories first", () => {
    const tree = buildFileTree(["README.md", "src/b.py", "src/a.py", "src/pkg/c.py", "docs/x.md"]);
    expect(tree.map((n) => n.name)).toEqual(["docs", "src", "README.md"]);
    const src = tree[1]!;
    expect(src.children.map((n) => `${n.type}:${n.name}`)).toEqual(["dir:pkg", "file:a.py", "file:b.py"]);
    expect(src.children[0]!.children[0]!.path).toBe("src/pkg/c.py");
  });
});
