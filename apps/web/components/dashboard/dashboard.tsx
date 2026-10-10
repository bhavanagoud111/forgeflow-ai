"use client";

import { Activity, CheckCircle2, Clock, FolderGit2, PauseCircle, XCircle, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/common/page-header";
import { SimulatedBadge } from "@/components/common/simulated-badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/common/states";
import { ExecutionListItem } from "@/components/executions/execution-row";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDuration, formatNumber, formatRelative, humanize } from "@/lib/format";
import { useAudit, useExecutions, useHealth, useMetrics } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { ExecutionsChart } from "./executions-chart";

function StatCard({
  label,
  value,
  icon: Icon,
  href,
  tone,
  loading,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  href?: string;
  tone?: "accent" | "success" | "danger" | "warning";
  loading?: boolean;
}) {
  const body = (
    <Card className={cn("h-full p-4 transition-colors", href && "hover:border-muted-foreground/40")}>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <Icon
          className={cn(
            "size-4",
            tone === "accent" && "text-accent",
            tone === "success" && "text-success",
            tone === "danger" && "text-danger",
            tone === "warning" && "text-warning",
          )}
          aria-hidden="true"
        />
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-7 w-16" />
      ) : (
        <p className="mt-1.5 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
      )}
    </Card>
  );
  return href ? (
    <Link href={href} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

export function Dashboard() {
  const metrics = useMetrics();
  const health = useHealth();
  const recent = useExecutions({ limit: 8 });
  const audit = useAudit(12);
  const m = metrics.data;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Execution activity across connected repositories."
        actions={
          <>
            {health.data?.simulated_llm && <SimulatedBadge />}
            <Button asChild size="sm">
              <Link href="/executions?new=1">New execution</Link>
            </Button>
          </>
        }
      />

      {metrics.isError && <ErrorState error={metrics.error} className="mb-4" />}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard
          label="Active executions"
          value={formatNumber(m?.executions.active)}
          icon={Activity}
          tone="accent"
          href="/executions?status=running"
          loading={metrics.isPending}
        />
        <StatCard
          label="Completed"
          value={formatNumber(m?.executions.completed)}
          icon={CheckCircle2}
          tone="success"
          href="/executions?status=succeeded"
          loading={metrics.isPending}
        />
        <StatCard
          label="Failed"
          value={formatNumber(m?.executions.failed)}
          icon={XCircle}
          tone="danger"
          href="/executions?status=failed"
          loading={metrics.isPending}
        />
        <StatCard
          label="Pending approvals"
          value={formatNumber(m?.pending_approvals)}
          icon={PauseCircle}
          tone="warning"
          href="/approvals"
          loading={metrics.isPending}
        />
        <StatCard
          label="Connected repositories"
          value={formatNumber(m?.repositories)}
          icon={FolderGit2}
          href="/repositories"
          loading={metrics.isPending}
        />
        <StatCard
          label="Avg. execution time"
          value={m?.avg_duration_ms ? formatDuration(m.avg_duration_ms) : "—"}
          icon={Clock}
          loading={metrics.isPending}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Executions per day</CardTitle>
            <CardDescription>
              {m ? `${formatNumber(m.executions.total)} total · ${formatNumber(m.usage.agent_runs)} agent runs` : " "}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {metrics.isPending ? (
              <Skeleton className="h-56 w-full" />
            ) : m && m.daily.length > 0 ? (
              <ExecutionsChart daily={m.daily} />
            ) : (
              <EmptyState title="No executions yet" description="Daily counts appear once executions run." />
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Recent executions</CardTitle>
            <Link href="/executions" className="text-xs text-muted-foreground hover:text-foreground">
              View all
            </Link>
          </CardHeader>
          <CardContent className="px-2">
            {recent.isError ? (
              <ErrorState error={recent.error} className="mx-2" />
            ) : recent.isPending ? (
              <div className="space-y-2 px-2">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : recent.data.items.length === 0 ? (
              <EmptyState title="No executions yet" className="mx-2" />
            ) : (
              <div className="space-y-0.5">
                {recent.data.items.map((e) => (
                  <ExecutionListItem key={e.id} execution={e} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
            <CardDescription>Audit log of actions taken through the API, Slack and agents.</CardDescription>
          </CardHeader>
          <CardContent>
            {audit.isError ? (
              <ErrorState error={audit.error} />
            ) : audit.isPending ? (
              <Skeleton className="h-24 w-full" />
            ) : audit.data.items.length === 0 ? (
              <EmptyState title="No activity recorded" />
            ) : (
              <ol className="space-y-2.5">
                {audit.data.items.map((a, i) => {
                  const target = a.target ?? "";
                  const href = target.startsWith("exec_")
                    ? `/executions/${target}`
                    : target.startsWith("repo_")
                      ? `/repositories/${target}`
                      : target.startsWith("appr_")
                        ? "/approvals"
                        : null;
                  return (
                    <li key={`${a.created_at}-${i}`} className="flex items-start gap-3 text-sm">
                      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate">
                          <span className="font-medium">{humanize(a.action)}</span>
                          {target && (
                            <>
                              {" · "}
                              {href ? (
                                <Link href={href} className="font-mono text-xs text-accent hover:underline">
                                  {target}
                                </Link>
                              ) : (
                                <span className="font-mono text-xs">{target}</span>
                              )}
                            </>
                          )}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {a.actor} · {formatRelative(a.created_at)}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Usage</CardTitle>
            <CardDescription>Totals reported by the API.</CardDescription>
          </CardHeader>
          <CardContent>
            {m ? (
              <dl className="divide-y divide-border">
                {[
                  ["Agent runs", formatNumber(m.usage.agent_runs)],
                  ["Input tokens", formatNumber(m.usage.input_tokens)],
                  ["Output tokens", formatNumber(m.usage.output_tokens)],
                  ["Model cost", `$${m.usage.cost_usd.toFixed(2)}`],
                  ["Tool errors", formatNumber(m.usage.tool_errors)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between py-1.5 text-sm">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="font-medium tabular-nums">{v}</dd>
                  </div>
                ))}
                {Object.entries(m.executions.by_workflow).map(([wf, n]) => (
                  <div key={wf} className="flex justify-between py-1.5 text-sm">
                    <dt className="text-muted-foreground">{humanize(wf)} executions</dt>
                    <dd className="font-medium tabular-nums">{formatNumber(n)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <Skeleton className="h-32 w-full" />
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
