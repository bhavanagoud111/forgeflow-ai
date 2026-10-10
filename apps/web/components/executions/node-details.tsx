"use client";

import { X } from "lucide-react";
import { SectionTitle } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatDuration, formatNumber, formatTime } from "@/lib/format";
import { graphNodeFor, type NodeStatus } from "@/lib/node-status";
import type { ExecutionEvent, Trace } from "@/lib/types";
import { cn } from "@/lib/utils";

export function NodeDetails({
  node,
  status,
  events,
  trace,
  onClose,
  onOpenConsole,
}: {
  node: string;
  status: NodeStatus;
  events: ExecutionEvent[];
  trace: Trace | undefined;
  onClose: () => void;
  onOpenConsole: (node: string) => void;
}) {
  const runs = (trace?.runs ?? []).filter((r) => graphNodeFor(r.node) === node);
  const runIds = new Set(runs.map((r) => r.id));
  const tools = (trace?.tool_calls ?? []).filter((t) => t.agent_run_id && runIds.has(t.agent_run_id));
  const nodeEvents = events.filter((e) => graphNodeFor(e.node) === node);
  const outputs = nodeEvents.filter(
    (e) => !e.type.startsWith("tool.") && e.type !== "agent.started" && e.type !== "agent.completed",
  );

  return (
    <Card className="flex max-h-[640px] flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <p className="truncate font-mono text-sm font-medium">{node}</p>
          <div className="mt-1">
            <StatusBadge status={status} />
          </div>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close node details">
          <X />
        </Button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3">
        <div>
          <SectionTitle>Agent runs ({runs.length})</SectionTitle>
          {runs.length === 0 ? (
            <p className="text-xs text-muted-foreground">No runs recorded for this node.</p>
          ) : (
            <ul className="space-y-2">
              {runs.map((r) => (
                <li key={r.id} className="rounded-md border border-border p-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{r.agent_id}</span>
                    <StatusBadge status={r.status} />
                  </div>
                  <p className="mt-1 text-muted-foreground">
                    {r.node !== node && <span className="font-mono">{r.node} · </span>}
                    attempt {r.attempt} · {formatDuration(r.duration_ms)}
                    {r.model ? ` · ${r.provider}/${r.model}` : ""} ·{" "}
                    {formatNumber(r.input_tokens + r.output_tokens)} tokens
                  </p>
                  {r.error && <p className="mt-1 text-danger">{r.error}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <SectionTitle>Tool calls ({tools.length})</SectionTitle>
          {tools.length === 0 ? (
            <p className="text-xs text-muted-foreground">No tool calls.</p>
          ) : (
            <ul className="space-y-1.5 text-xs">
              {tools.map((t) => (
                <li key={t.id}>
                  <span className={cn("font-mono", t.status !== "succeeded" && "text-danger")}>{t.tool}</span>{" "}
                  <span className="text-muted-foreground">{formatDuration(t.duration_ms)}</span>
                  <p className={cn("break-words", t.error ? "text-danger" : "text-muted-foreground")}>
                    {t.error ?? t.result_summary}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <SectionTitle>Outputs</SectionTitle>
          {outputs.length === 0 ? (
            <p className="text-xs text-muted-foreground">No output events.</p>
          ) : (
            <ul className="space-y-1 text-xs">
              {outputs.map((e) => (
                <li key={e.seq}>
                  <span className="font-mono text-muted-foreground">{e.type}</span>{" "}
                  <span className={cn(e.type.endsWith(".failed") && "text-danger")}>{e.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between">
            <SectionTitle>Events ({nodeEvents.length})</SectionTitle>
            {nodeEvents.length > 0 && (
              <Button variant="link" size="sm" className="mb-2 text-xs" onClick={() => onOpenConsole(node)}>
                Open in console
              </Button>
            )}
          </div>
          <ul className="space-y-0.5 font-mono text-[11px]">
            {nodeEvents.slice(-25).map((e) => (
              <li key={e.seq} className="truncate text-muted-foreground" title={e.message}>
                {formatTime(e.created_at)} {e.type}
              </li>
            ))}
          </ul>
          {nodeEvents.length > 25 && (
            <p className="mt-1 text-[11px] text-muted-foreground">Showing the last 25.</p>
          )}
        </div>
      </div>
    </Card>
  );
}
