"use client";

import { Cpu, Wrench } from "lucide-react";
import Link from "next/link";
import { PageHeader, SectionTitle } from "@/components/common/page-header";
import { SimulatedBadge } from "@/components/common/simulated-badge";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/common/states";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatDuration, formatNumber, formatRelative, shortId } from "@/lib/format";
import { useAgents, useHealth } from "@/lib/queries";
import type { Agent } from "@/lib/types";
import { cn } from "@/lib/utils";

function AgentCard({ agent }: { agent: Agent }) {
  const run = agent.last_run;
  const failedTools = agent.recent_tools.filter((t) => t.status !== "succeeded");
  return (
    <Card className={cn("flex flex-col", agent.state === "active" && "border-accent/50")}>
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold">{agent.name}</h3>
            {agent.uses_llm && (
              <Badge variant="outline" title="This agent calls the configured model provider">
                <Cpu />
                LLM
              </Badge>
            )}
          </div>
          <p className="font-mono text-[11px] text-muted-foreground">{agent.id}</p>
        </div>
        <StatusBadge status={agent.state} />
      </div>

      <div className="flex flex-1 flex-col gap-4 px-4 py-3">
        <p className="text-sm text-muted-foreground">{agent.description}</p>

        <div>
          <SectionTitle>Responsibilities</SectionTitle>
          <div className="flex flex-wrap gap-1">
            {agent.responsibilities.map((r) => (
              <Badge key={r} variant="neutral" className="font-normal">
                {r}
              </Badge>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 text-center">
          {[
            ["Runs", formatNumber(agent.runs_total)],
            ["Failures", formatNumber(agent.failures_total)],
            ["Avg. duration", formatDuration(agent.avg_duration_ms)],
          ].map(([k, v]) => (
            <div key={k} className="rounded-md bg-muted/60 px-2 py-1.5">
              <p className="text-[11px] text-muted-foreground">{k}</p>
              <p
                className={cn(
                  "text-sm font-medium tabular-nums",
                  k === "Failures" && agent.failures_total > 0 && "text-danger",
                )}
              >
                {v}
              </p>
            </div>
          ))}
        </div>

        <div>
          <SectionTitle>Active executions</SectionTitle>
          {agent.active_executions.length === 0 ? (
            <p className="text-xs text-muted-foreground">None</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {agent.active_executions.map((id) => (
                <Link key={id} href={`/executions/${id}`} className="font-mono text-xs text-accent hover:underline">
                  {id}
                </Link>
              ))}
            </div>
          )}
        </div>

        <div>
          <SectionTitle>Recent nodes</SectionTitle>
          {agent.recent_nodes.length === 0 ? (
            <p className="text-xs text-muted-foreground">No runs yet</p>
          ) : (
            <div className="flex flex-wrap gap-1">
              {agent.recent_nodes.map((n) => (
                <span key={n} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
                  {n}
                </span>
              ))}
            </div>
          )}
        </div>

        <div>
          <SectionTitle>Last run</SectionTitle>
          {run ? (
            <div className="space-y-1 text-xs">
              <div className="flex items-center gap-2">
                <StatusBadge status={run.status} />
                <Link href={`/executions/${run.execution_id}`} className="font-mono text-accent hover:underline">
                  {shortId(run.execution_id)}
                </Link>
                <span className="text-muted-foreground">
                  {run.node} · attempt {run.attempt}
                </span>
              </div>
              <p className="text-muted-foreground">
                {formatDuration(run.duration_ms)} · {run.model ? `${run.provider}/${run.model}` : "no model call"} ·{" "}
                {formatNumber(run.input_tokens + run.output_tokens)} tokens · {formatRelative(run.ended_at ?? run.started_at)}
              </p>
              {run.error && <p className="text-danger">{run.error}</p>}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">Never run</p>
          )}
        </div>

        <div>
          <SectionTitle>Recent tool activity</SectionTitle>
          {agent.recent_tools.length === 0 ? (
            <p className="text-xs text-muted-foreground">No tool calls yet</p>
          ) : (
            <ul className="space-y-1">
              {agent.recent_tools.map((t) => (
                <li key={t.id} className="flex items-start gap-2 text-xs">
                  <Wrench
                    className={cn("mt-0.5 size-3 shrink-0", t.status === "succeeded" ? "text-muted-foreground" : "text-danger")}
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <span className="font-mono">{t.tool}</span>{" "}
                    <span className="text-muted-foreground">{formatDuration(t.duration_ms)}</span>
                    <p className={cn("truncate", t.error ? "text-danger" : "text-muted-foreground")} title={t.error ?? t.result_summary ?? ""}>
                      {t.error ?? t.result_summary ?? t.status}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {failedTools.length > 0 && (
          <div>
            <SectionTitle>Recent failures</SectionTitle>
            <ul className="space-y-1 text-xs text-danger">
              {failedTools.map((t) => (
                <li key={t.id}>
                  <span className="font-mono">{t.tool}</span>: {t.error ?? t.status}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

export function AgentControlCenter() {
  const agents = useAgents();
  const health = useHealth();
  const list = agents.data ?? [];
  const counts = {
    active: list.filter((a) => a.state === "active").length,
    error: list.filter((a) => a.state === "error").length,
  };

  return (
    <>
      <PageHeader
        title="Agent Control Center"
        description={
          agents.data
            ? `${list.length} agents · ${counts.active} active · ${counts.error} in error`
            : "Specialized agents that plan, implement, test, review and verify changes."
        }
        actions={health.data?.simulated_llm ? <SimulatedBadge /> : undefined}
      />
      {agents.isError ? (
        <ErrorState error={agents.error} />
      ) : agents.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-96 w-full" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <EmptyState title="No agents reported" description="The API returned an empty agent list." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {list.map((a) => (
            <AgentCard key={a.id} agent={a} />
          ))}
        </div>
      )}
    </>
  );
}
