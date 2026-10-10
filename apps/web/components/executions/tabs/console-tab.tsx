"use client";

import { ArrowDownToLine } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { EmptyState } from "@/components/common/states";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { StreamStatus } from "@/lib/hooks/use-execution-events";
import { formatDuration, formatTime } from "@/lib/format";
import { graphNodeFor } from "@/lib/node-status";
import type { ExecutionEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

const ALL = "__all";

function eventVariant(type: string): BadgeVariant {
  if (type.endsWith(".failed")) return "danger";
  if (type === "test.passed" || type === "workflow.completed" || type === "pr.created") return "success";
  if (type.startsWith("approval.")) return "warning";
  if (type.startsWith("workflow.")) return "accent";
  if (type.startsWith("tool.")) return "neutral";
  if (type.startsWith("agent.")) return "info";
  return "outline";
}

function compactJson(value: unknown): string {
  try {
    const s = JSON.stringify(value);
    return s.length > 240 ? `${s.slice(0, 240)}…` : s;
  } catch {
    return String(value);
  }
}

export function ConsoleTab({
  events,
  streamStatus,
  initialNode,
}: {
  events: ExecutionEvent[];
  streamStatus: StreamStatus;
  initialNode?: string | null;
}) {
  const [agent, setAgent] = useState(ALL);
  const [node, setNode] = useState(initialNode ?? ALL);
  const [category, setCategory] = useState(ALL);
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());
  const [follow, setFollow] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const options = useMemo(() => {
    const agents = new Set<string>();
    const nodes = new Set<string>();
    const categories = new Set<string>();
    for (const e of events) {
      if (e.agent_id) agents.add(e.agent_id);
      if (e.node) nodes.add(e.node);
      categories.add(e.type.split(".")[0] ?? e.type);
    }
    if (initialNode) nodes.add(initialNode);
    return { agents: [...agents].sort(), nodes: [...nodes], categories: [...categories].sort() };
  }, [events, initialNode]);

  // Arguments from tool.started, looked up when rendering the matching completion.
  const toolArgs = useMemo(() => {
    const map = new Map<string, unknown>();
    for (const e of events) {
      if (e.type === "tool.started" && typeof e.data.call_id === "string") map.set(e.data.call_id, e.data.arguments);
    }
    return map;
  }, [events]);

  const filtered = useMemo(
    () =>
      events.filter(
        (e) =>
          (agent === ALL || e.agent_id === agent) &&
          (node === ALL || e.node === node || graphNodeFor(e.node) === node) &&
          (category === ALL || e.type.startsWith(`${category}.`) || e.type === category),
      ),
    [events, agent, node, category],
  );

  useEffect(() => {
    const el = scrollRef.current;
    if (follow && el) el.scrollTop = el.scrollHeight;
  }, [filtered.length, follow]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    if (atBottom !== follow) setFollow(atBottom);
  };

  const toggle = (seq: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      return next;
    });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={agent} onValueChange={setAgent}>
          <SelectTrigger className="w-44" aria-label="Filter by agent">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All agents</SelectItem>
            {options.agents.map((a) => (
              <SelectItem key={a} value={a}>
                {a}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={node} onValueChange={setNode}>
          <SelectTrigger className="w-48" aria-label="Filter by node">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All nodes</SelectItem>
            {options.nodes.map((n) => (
              <SelectItem key={n} value={n}>
                {n}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="w-40" aria-label="Filter by event type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All event types</SelectItem>
            {options.categories.map((c) => (
              <SelectItem key={c} value={c}>
                {c}.*
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          {filtered.length} of {events.length} events
        </span>
        <span className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <span
            className={cn(
              "size-1.5 rounded-full",
              streamStatus === "open" && "animate-pulse bg-accent",
              streamStatus === "ended" && "bg-muted-foreground",
              (streamStatus === "connecting" || streamStatus === "reconnecting") && "bg-warning",
              streamStatus === "error" && "bg-danger",
            )}
            aria-hidden="true"
          />
          {streamStatus === "open"
            ? "Live"
            : streamStatus === "ended"
              ? "Stream ended"
              : streamStatus === "error"
                ? "Disconnected, retrying"
                : streamStatus === "reconnecting"
                  ? "Reconnecting"
                  : "Connecting"}
          {!follow && (
            <Button variant="ghost" size="sm" onClick={() => setFollow(true)}>
              <ArrowDownToLine />
              Follow
            </Button>
          )}
        </span>
      </div>

      {events.length === 0 ? (
        <EmptyState
          title={streamStatus === "ended" ? "No events recorded" : "Waiting for events"}
          description="Events appear here as agents work."
        />
      ) : (
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="max-h-[560px] overflow-auto rounded-md border border-border bg-muted/30 font-mono text-xs"
          role="log"
          aria-live="polite"
        >
          {filtered.length === 0 ? (
            <p className="p-4 text-muted-foreground">No events match the filters.</p>
          ) : (
            <ul className="divide-y divide-border/60">
              {filtered.map((e) => {
                const callId = typeof e.data.call_id === "string" ? e.data.call_id : null;
                const args =
                  e.type === "tool.started" ? e.data.arguments : callId ? toolArgs.get(callId) : undefined;
                const duration = typeof e.data.duration_ms === "number" ? e.data.duration_ms : null;
                const error = typeof e.data.error === "string" ? e.data.error : null;
                const open = expanded.has(e.seq);
                return (
                  <li key={e.seq}>
                    <button
                      type="button"
                      onClick={() => toggle(e.seq)}
                      aria-expanded={open}
                      className="grid w-full grid-cols-[3rem_6.5rem_1fr] gap-x-3 px-3 py-1.5 text-left hover:bg-muted/60 sm:grid-cols-[3rem_6.5rem_9.5rem_9rem_1fr]"
                    >
                      <span className="text-muted-foreground tabular-nums">#{e.seq}</span>
                      <span className="text-muted-foreground tabular-nums">{formatTime(e.created_at)}</span>
                      <span className="hidden truncate sm:block">
                        <Badge variant={eventVariant(e.type)} className="font-mono">
                          {e.type}
                        </Badge>
                      </span>
                      <span className="hidden truncate text-muted-foreground sm:block" title={e.node ?? ""}>
                        {e.agent_id ?? "—"}
                        {e.node ? ` · ${e.node}` : ""}
                      </span>
                      <span className={cn("min-w-0 font-sans", e.type.endsWith(".failed") && "text-danger")}>
                        <span className="sm:hidden">
                          <Badge variant={eventVariant(e.type)} className="mr-1 font-mono">
                            {e.type}
                          </Badge>
                        </span>
                        {e.message}
                        {duration !== null && (
                          <span className="ml-2 font-mono text-muted-foreground">{formatDuration(duration)}</span>
                        )}
                        {error && <span className="ml-2 text-danger">{error}</span>}
                        {args !== undefined && e.type.startsWith("tool.") && (
                          <span className="mt-0.5 block truncate font-mono text-[11px] text-muted-foreground">
                            args {compactJson(args)}
                          </span>
                        )}
                      </span>
                    </button>
                    {open && (
                      <pre className="overflow-x-auto bg-background/60 px-3 py-2 text-[11px] whitespace-pre-wrap text-muted-foreground">
                        {JSON.stringify(
                          { agent_id: e.agent_id, node: e.node, created_at: e.created_at, data: e.data },
                          null,
                          2,
                        )}
                      </pre>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
