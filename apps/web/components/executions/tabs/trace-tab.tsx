"use client";

import { ErrorState, LoadingState, EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCost, formatDuration, formatNumber, formatTime } from "@/lib/format";
import { useTrace } from "@/lib/queries";

export function TraceTab({ executionId }: { executionId: string }) {
  const trace = useTrace(executionId);
  if (trace.isPending) return <LoadingState label="Loading trace…" />;
  if (trace.isError) return <ErrorState error={trace.error} />;
  const { runs, totals } = trace.data;
  const totalDuration = runs.reduce((sum, r) => sum + (r.duration_ms ?? 0), 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        {[
          ["Agent runs", formatNumber(totals.runs)],
          ["Failed runs", formatNumber(totals.failed_runs)],
          ["Retries", formatNumber(totals.retries)],
          ["Tool calls", formatNumber(totals.tool_calls)],
          ["Tool errors", formatNumber(totals.tool_errors)],
          ["LLM calls", formatNumber(totals.llm_calls)],
          ["Tokens", formatNumber(totals.input_tokens + totals.output_tokens)],
          ["Cost", formatCost(totals.cost_usd)],
        ].map(([k, v]) => (
          <Card key={k} className="px-3 py-2">
            <p className="text-[11px] text-muted-foreground">{k}</p>
            <p className="text-sm font-semibold tabular-nums">{v}</p>
          </Card>
        ))}
      </div>

      {runs.length === 0 ? (
        <EmptyState title="No agent runs recorded" />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Started</TableHead>
                <TableHead>Agent</TableHead>
                <TableHead>Node</TableHead>
                <TableHead className="text-right">Attempt</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Duration</TableHead>
                <TableHead>Provider / model</TableHead>
                <TableHead className="text-right">LLM calls</TableHead>
                <TableHead className="text-right">Tokens in / out</TableHead>
                <TableHead className="text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs text-muted-foreground">{formatTime(r.started_at)}</TableCell>
                  <TableCell className="whitespace-nowrap">{r.agent_id}</TableCell>
                  <TableCell className="font-mono text-xs">{r.node}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.attempt}</TableCell>
                  <TableCell>
                    <StatusBadge status={r.status} />
                    {r.error && <p className="mt-1 max-w-xs text-xs text-danger">{r.error}</p>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatDuration(r.duration_ms)}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {r.provider || r.model ? `${r.provider ?? "?"} / ${r.model ?? "?"}` : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{r.llm_calls}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatNumber(r.input_tokens)} / {formatNumber(r.output_tokens)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatCost(r.cost_usd)}</TableCell>
                </TableRow>
              ))}
              <TableRow className="bg-muted/40 font-medium hover:bg-muted/40">
                <TableCell colSpan={5}>Totals</TableCell>
                <TableCell className="text-right tabular-nums">{formatDuration(totalDuration)}</TableCell>
                <TableCell />
                <TableCell className="text-right tabular-nums">{totals.llm_calls}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatNumber(totals.input_tokens)} / {formatNumber(totals.output_tokens)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{formatCost(totals.cost_usd)}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      )}
      <p className="text-xs text-muted-foreground">
        Total duration sums agent run time; parallel runs overlap, so it can exceed wall-clock time.
      </p>
    </div>
  );
}
