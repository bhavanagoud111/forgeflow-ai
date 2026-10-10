export type DiffLineType = "context" | "add" | "del" | "note";

export interface DiffLine {
  type: DiffLineType;
  content: string;
  oldNumber: number | null;
  newNumber: number | null;
}

export interface DiffHunk {
  header: string;
  section: string;
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: DiffLine[];
}

export type DiffFileStatus = "added" | "deleted" | "modified" | "renamed";

export interface DiffFile {
  oldPath: string | null;
  newPath: string | null;
  /** Display path: the new path, or the old one for deletions. */
  path: string;
  status: DiffFileStatus;
  binary: boolean;
  hunks: DiffHunk[];
  additions: number;
  deletions: number;
}

const HUNK_RE = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$/;

function stripPrefix(path: string): string | null {
  const p = path.trim().replace(/\t.*$/, "");
  if (p === "/dev/null") return null;
  if (p.startsWith("a/") || p.startsWith("b/")) return p.slice(2);
  return p;
}

function newFile(): DiffFile {
  return {
    oldPath: null,
    newPath: null,
    path: "",
    status: "modified",
    binary: false,
    hunks: [],
    additions: 0,
    deletions: 0,
  };
}

function finalize(file: DiffFile): DiffFile {
  if (file.status !== "renamed") {
    if (file.oldPath === null && file.newPath !== null) file.status = "added";
    else if (file.newPath === null && file.oldPath !== null) file.status = "deleted";
  }
  file.path = file.newPath ?? file.oldPath ?? "";
  return file;
}

/**
 * Parse a unified diff (git or plain `diff -u` output) into files, hunks and
 * numbered lines. Unknown header lines are ignored rather than rejected.
 */
export function parseUnifiedDiff(text: string): DiffFile[] {
  if (!text || !text.trim()) return [];
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  if (lines[lines.length - 1] === "") lines.pop();

  const files: DiffFile[] = [];
  const cur: {
    file: DiffFile | null;
    hunk: DiffHunk | null;
    oldNo: number;
    newNo: number;
    oldLeft: number;
    newLeft: number;
    gitHeader: boolean;
  } = { file: null, hunk: null, oldNo: 0, newNo: 0, oldLeft: 0, newLeft: 0, gitHeader: false };

  const startFile = (gitHeader: boolean): DiffFile => {
    if (cur.file) files.push(finalize(cur.file));
    const f = newFile();
    cur.file = f;
    cur.hunk = null;
    cur.oldLeft = 0;
    cur.newLeft = 0;
    cur.gitHeader = gitHeader;
    return f;
  };

  const note = (content: string): DiffLine => ({ type: "note", content, oldNumber: null, newNumber: null });

  for (const line of lines) {
    const { file, hunk } = cur;

    if (file && hunk && (cur.oldLeft > 0 || cur.newLeft > 0)) {
      const marker = line[0];
      if (marker === "+") {
        hunk.lines.push({ type: "add", content: line.slice(1), oldNumber: null, newNumber: cur.newNo++ });
        cur.newLeft--;
        file.additions++;
        continue;
      }
      if (marker === "-") {
        hunk.lines.push({ type: "del", content: line.slice(1), oldNumber: cur.oldNo++, newNumber: null });
        cur.oldLeft--;
        file.deletions++;
        continue;
      }
      if (marker === " " || line === "") {
        hunk.lines.push({
          type: "context",
          content: line.slice(1),
          oldNumber: cur.oldNo++,
          newNumber: cur.newNo++,
        });
        cur.oldLeft--;
        cur.newLeft--;
        continue;
      }
      // Any other line ends the hunk early (counts were wrong); parse it as a header.
    }

    if (line.startsWith("\\")) {
      hunk?.lines.push(note(line.slice(1).trim()));
      continue;
    }

    if (line.startsWith("diff --git ")) {
      const f = startFile(true);
      const m = /^diff --git a\/(.+) b\/(.+)$/.exec(line);
      if (m) {
        f.oldPath = m[1] ?? null;
        f.newPath = m[2] ?? null;
      }
      continue;
    }

    if (line.startsWith("--- ")) {
      // Plain unified diffs have no "diff --git" line, so "---" starts a new file.
      const f = file && cur.gitHeader && file.hunks.length === 0 ? file : startFile(false);
      f.oldPath = stripPrefix(line.slice(4));
      continue;
    }

    if (!file) continue;

    if (line.startsWith("+++ ")) {
      file.newPath = stripPrefix(line.slice(4));
      continue;
    }
    if (line.startsWith("new file mode")) {
      file.status = "added";
      file.oldPath = null;
      continue;
    }
    if (line.startsWith("deleted file mode")) {
      file.status = "deleted";
      file.newPath = null;
      continue;
    }
    if (line.startsWith("rename from ")) {
      file.status = "renamed";
      file.oldPath = line.slice("rename from ".length);
      continue;
    }
    if (line.startsWith("rename to ")) {
      file.status = "renamed";
      file.newPath = line.slice("rename to ".length);
      continue;
    }
    if (line.startsWith("Binary files ") || line === "GIT binary patch") {
      file.binary = true;
      continue;
    }
    const m = HUNK_RE.exec(line);
    if (m) {
      const next: DiffHunk = {
        header: line,
        section: m[5] ?? "",
        oldStart: Number(m[1]),
        oldLines: m[2] === undefined ? 1 : Number(m[2]),
        newStart: Number(m[3]),
        newLines: m[4] === undefined ? 1 : Number(m[4]),
        lines: [],
      };
      file.hunks.push(next);
      cur.hunk = next;
      cur.oldNo = next.oldStart;
      cur.newNo = next.newStart;
      cur.oldLeft = next.oldLines;
      cur.newLeft = next.newLines;
    }
  }
  if (cur.file) files.push(finalize(cur.file));
  return files;
}

export interface SideBySideRow {
  left: DiffLine | null;
  right: DiffLine | null;
}

/**
 * Pair a hunk's lines for side-by-side rendering: context lines appear on both
 * sides, and each run of deletions is aligned with the run of additions that
 * immediately follows it.
 */
export function toSideBySide(hunk: DiffHunk): SideBySideRow[] {
  const rows: SideBySideRow[] = [];
  let dels: DiffLine[] = [];
  let adds: DiffLine[] = [];

  const flush = () => {
    const n = Math.max(dels.length, adds.length);
    for (let i = 0; i < n; i++) rows.push({ left: dels[i] ?? null, right: adds[i] ?? null });
    dels = [];
    adds = [];
  };

  for (const line of hunk.lines) {
    if (line.type === "del") {
      if (adds.length > 0) flush();
      dels.push(line);
    } else if (line.type === "add") {
      adds.push(line);
    } else {
      flush();
      rows.push(line.type === "note" ? { left: null, right: line } : { left: line, right: line });
    }
  }
  flush();
  return rows;
}

export function diffTotals(files: readonly DiffFile[]): { additions: number; deletions: number } {
  return files.reduce(
    (acc, f) => ({ additions: acc.additions + f.additions, deletions: acc.deletions + f.deletions }),
    { additions: 0, deletions: 0 },
  );
}
