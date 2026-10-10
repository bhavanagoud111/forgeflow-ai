import { describe, expect, it } from "vitest";
import { diffTotals, parseUnifiedDiff, toSideBySide } from "@/lib/diff";

const GIT_DIFF = `diff --git a/taskboard/auth.py b/taskboard/auth.py
new file mode 100644
index 0000000..4a1d2dd
--- /dev/null
+++ b/taskboard/auth.py
@@ -0,0 +1,3 @@
+"""Auth."""
+
+import os
diff --git a/taskboard/main.py b/taskboard/main.py
index 1111111..2222222 100644
--- a/taskboard/main.py
+++ b/taskboard/main.py
@@ -1,5 +1,6 @@ def app():
 from fastapi import FastAPI
-from taskboard.store import TaskStore
+from taskboard.auth import require_user
+from taskboard.store import TaskStore
 
 app = FastAPI()
 store = TaskStore()
@@ -20,2 +21,2 @@
-    return 1
+    return 2
 # end
\\ No newline at end of file
diff --git a/old.txt b/old.txt
deleted file mode 100644
index 3333333..0000000
--- a/old.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-one
-two
`;

describe("parseUnifiedDiff", () => {
  const files = parseUnifiedDiff(GIT_DIFF);

  it("splits files and detects status", () => {
    expect(files.map((f) => [f.path, f.status])).toEqual([
      ["taskboard/auth.py", "added"],
      ["taskboard/main.py", "modified"],
      ["old.txt", "deleted"],
    ]);
  });

  it("counts additions and deletions", () => {
    expect(files.map((f) => [f.additions, f.deletions])).toEqual([
      [3, 0],
      [3, 2],
      [0, 2],
    ]);
    expect(diffTotals(files)).toEqual({ additions: 6, deletions: 4 });
  });

  it("numbers old and new lines", () => {
    const hunk = files[1]!.hunks[0]!;
    expect(hunk.oldStart).toBe(1);
    expect(hunk.newStart).toBe(1);
    expect(hunk.section).toBe("def app():");
    expect(hunk.lines.map((l) => [l.type, l.oldNumber, l.newNumber])).toEqual([
      ["context", 1, 1],
      ["del", 2, null],
      ["add", null, 2],
      ["add", null, 3],
      ["context", 3, 4],
      ["context", 4, 5],
      ["context", 5, 6],
    ]);
  });

  it("keeps no-newline markers as notes", () => {
    const hunk = files[1]!.hunks[1]!;
    expect(hunk.lines.at(-1)).toMatchObject({ type: "note", content: "No newline at end of file" });
    expect(hunk.lines.filter((l) => l.type === "context")[0]).toMatchObject({ oldNumber: 21, newNumber: 22 });
  });

  it("parses plain unified diffs without git headers", () => {
    const plain = `--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n--- a/y.py\n+++ b/y.py\n@@ -1 +1,2 @@\n a\n+c\n`;
    const parsed = parseUnifiedDiff(plain);
    expect(parsed.map((f) => f.path)).toEqual(["x.py", "y.py"]);
    expect(parsed[1]!.hunks[0]!.newLines).toBe(2);
  });

  it("detects renames", () => {
    const parsed = parseUnifiedDiff(
      `diff --git a/a.txt b/b.txt\nsimilarity index 100%\nrename from a.txt\nrename to b.txt\n`,
    );
    expect(parsed[0]).toMatchObject({ status: "renamed", oldPath: "a.txt", newPath: "b.txt", path: "b.txt" });
  });

  it("handles empty input", () => {
    expect(parseUnifiedDiff("")).toEqual([]);
    expect(parseUnifiedDiff("  \n")).toEqual([]);
  });

  it("does not treat a removed line starting with dashes as a file header", () => {
    const parsed = parseUnifiedDiff(`--- a/x.md\n+++ b/x.md\n@@ -1,2 +1,1 @@\n--- heading\n keep\n`);
    expect(parsed).toHaveLength(1);
    expect(parsed[0]!.hunks[0]!.lines[0]).toMatchObject({ type: "del", content: "-- heading" });
  });
});

describe("toSideBySide", () => {
  it("aligns deletion runs with the following additions", () => {
    const hunk = parseUnifiedDiff(GIT_DIFF)[1]!.hunks[0]!;
    const rows = toSideBySide(hunk);
    expect(rows.map((r) => [r.left?.oldNumber ?? null, r.right?.newNumber ?? null])).toEqual([
      [1, 1],
      [2, 2],
      [null, 3],
      [3, 4],
      [4, 5],
      [5, 6],
    ]);
  });
});
