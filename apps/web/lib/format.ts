/** Parse an API timestamp. Timestamps are UTC; some omit the trailing "Z". */
export function parseTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null;
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value);
  const d = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  if (m < 60) return rem ? `${m}m ${rem}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

export function formatRelative(value: string | null | undefined, now: Date = new Date()): string {
  const d = parseTimestamp(value);
  if (!d) return "—";
  const diff = Math.round((now.getTime() - d.getTime()) / 1000);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function formatDateTime(value: string | null | undefined): string {
  const d = parseTimestamp(value);
  if (!d) return "—";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatTime(value: string | null | undefined): string {
  const d = parseTimestamp(value);
  if (!d) return "—";
  const base = d.toLocaleTimeString(undefined, { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return `${base}.${String(d.getMilliseconds()).padStart(3, "0")}`;
}

export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat().format(n);
}

export function formatCost(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `$${n.toFixed(n > 0 && n < 0.01 ? 4 : 2)}`;
}

export function humanize(id: string | null | undefined): string {
  if (!id) return "—";
  const s = id.replace(/[_.]/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const WORKFLOW_LABELS: Record<string, string> = {
  feature: "Feature",
  bug_investigation: "Bug investigation",
  code_review: "Code review",
  repo_onboarding: "Repository onboarding",
  test_generation: "Test generation",
};

export function workflowLabel(id: string): string {
  return WORKFLOW_LABELS[id] ?? humanize(id);
}

export function shortId(id: string): string {
  const i = id.indexOf("_");
  return i >= 0 ? id.slice(i + 1, i + 9) : id.slice(0, 8);
}
