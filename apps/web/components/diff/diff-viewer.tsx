"use client";

import { Columns2, FileCode2, Rows3 } from "lucide-react";
import { useMemo, useState } from "react";
import { EmptyState } from "@/components/common/states";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  diffTotals,
  parseUnifiedDiff,
  toSideBySide,
  type DiffFile,
  type DiffFileStatus,
  type DiffHunk,
  type DiffLine,
} from "@/lib/diff";
import { cn } from "@/lib/utils";

const STATUS_BADGE: Record<DiffFileStatus, { variant: BadgeVariant; label: string }> = {
  added: { variant: "success", label: "A" },
  deleted: { variant: "danger", label: "D" },
  modified: { variant: "info", label: "M" },
  renamed: { variant: "warning", label: "R" },
};

function FileStatusBadge({ status }: { status: DiffFileStatus }) {
  const cfg = STATUS_BADGE[status];
  return (
    <Badge variant={cfg.variant} className="w-5 justify-center px-0 font-mono" title={status}>
      {cfg.label}
    </Badge>
  );
}

function Counts({ file }: { file: Pick<DiffFile, "additions" | "deletions"> }) {
  return (
    <span className="font-mono text-[11px] tabular-nums">
      <span className="text-success">+{file.additions}</span>{" "}
      <span className="text-danger">−{file.deletions}</span>
    </span>
  );
}

const lineClass = (line: DiffLine | null) =>
  !line ? "bg-muted/40" : line.type === "add" ? "diff-add" : line.type === "del" ? "diff-del" : "";

const sign = (line: DiffLine) => (line.type === "add" ? "+" : line.type === "del" ? "-" : " ");

function Gutter({ value }: { value: number | null }) {
  return (
    <td className="diff-gutter w-10 min-w-10 border-r border-border/60 px-2 text-right align-top text-muted-foreground/80 select-none">
      {value ?? ""}
    </td>
  );
}

function HunkHeader({ hunk, colSpan }: { hunk: DiffHunk; colSpan: number }) {
  return (
    <tr className="bg-info-soft/60">
      <td colSpan={colSpan} className="px-3 py-1 text-info/90">
        {hunk.header}
      </td>
    </tr>
  );
}

function UnifiedHunk({ hunk }: { hunk: DiffHunk }) {
  return (
    <>
      <HunkHeader hunk={hunk} colSpan={3} />
      {hunk.lines.map((line, i) =>
        line.type === "note" ? (
          <tr key={i}>
            <td colSpan={3} className="px-3 text-muted-foreground italic">
              {line.content}
            </td>
          </tr>
        ) : (
          <tr key={i} className={lineClass(line)}>
            <Gutter value={line.oldNumber} />
            <Gutter value={line.newNumber} />
            <td className="px-2 whitespace-pre">
              <span className="mr-2 text-muted-foreground select-none">{sign(line)}</span>
              {line.content}
            </td>
          </tr>
        ),
      )}
    </>
  );
}

function SplitHunk({ hunk }: { hunk: DiffHunk }) {
  const rows = useMemo(() => toSideBySide(hunk), [hunk]);
  return (
    <>
      <HunkHeader hunk={hunk} colSpan={4} />
      {rows.map((row, i) => {
        if (row.right?.type === "note") {
          return (
            <tr key={i}>
              <td colSpan={4} className="px-3 text-muted-foreground italic">
                {row.right.content}
              </td>
            </tr>
          );
        }
        return (
          <tr key={i}>
            <Gutter value={row.left?.oldNumber ?? null} />
            <td className={cn("w-1/2 border-r border-border/60 px-2 whitespace-pre", lineClass(row.left))}>
              {row.left?.content ?? ""}
            </td>
            <Gutter value={row.right?.newNumber ?? null} />
            <td className={cn("w-1/2 px-2 whitespace-pre", lineClass(row.right))}>{row.right?.content ?? ""}</td>
          </tr>
        );
      })}
    </>
  );
}

function FileDiff({ file, mode }: { file: DiffFile; mode: "unified" | "split" }) {
  return (
    <section id={`diff-${encodeURIComponent(file.path)}`} className="overflow-hidden rounded-md border border-border">
      <header className="flex items-center gap-2 border-b border-border bg-muted/50 px-3 py-2">
        <FileStatusBadge status={file.status} />
        <span className="min-w-0 flex-1 truncate font-mono text-xs">
          {file.status === "renamed" && file.oldPath ? `${file.oldPath} → ${file.newPath}` : file.path}
        </span>
        <Counts file={file} />
      </header>
      {file.binary ? (
        <p className="px-3 py-3 text-xs text-muted-foreground">Binary file not shown.</p>
      ) : file.hunks.length === 0 ? (
        <p className="px-3 py-3 text-xs text-muted-foreground">No content changes.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse font-mono text-xs leading-5">
            <tbody>
              {file.hunks.map((h, i) =>
                mode === "unified" ? <UnifiedHunk key={i} hunk={h} /> : <SplitHunk key={i} hunk={h} />,
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function DiffViewer({ diff, emptyMessage = "No changes." }: { diff: string; emptyMessage?: string }) {
  const files = useMemo(() => parseUnifiedDiff(diff), [diff]);
  const totals = useMemo(() => diffTotals(files), [files]);
  const [mode, setMode] = useState<"unified" | "split">("unified");
  const [selected, setSelected] = useState<string | null>(null);

  if (files.length === 0) return <EmptyState title={emptyMessage} />;

  const visible = selected ? files.filter((f) => f.path === selected) : files;

  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <nav aria-label="Changed files" className="lg:sticky lg:top-4 lg:self-start">
        <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {files.length} file{files.length === 1 ? "" : "s"}
          </span>
          <Counts file={totals} />
        </div>
        <ul className="space-y-0.5 rounded-md border border-border p-1">
          <li>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className={cn(
                "flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs",
                selected === null ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60",
              )}
            >
              <FileCode2 className="size-3.5" aria-hidden="true" />
              All files
            </button>
          </li>
          {files.map((f) => (
            <li key={f.path}>
              <button
                type="button"
                onClick={() => setSelected(f.path)}
                title={f.path}
                className={cn(
                  "flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs",
                  selected === f.path ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60",
                )}
              >
                <FileStatusBadge status={f.status} />
                <span className="min-w-0 flex-1 truncate font-mono">
                  {f.path}
                </span>
                <Counts file={f} />
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div className="min-w-0 space-y-3">
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant={mode === "unified" ? "secondary" : "ghost"}
            onClick={() => setMode("unified")}
            aria-pressed={mode === "unified"}
          >
            <Rows3 />
            Unified
          </Button>
          <Button
            size="sm"
            variant={mode === "split" ? "secondary" : "ghost"}
            onClick={() => setMode("split")}
            aria-pressed={mode === "split"}
          >
            <Columns2 />
            Side by side
          </Button>
        </div>
        {visible.map((f) => (
          <FileDiff key={f.path} file={f} mode={mode} />
        ))}
      </div>
    </div>
  );
}
