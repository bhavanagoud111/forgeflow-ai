"use client";

import { ArrowLeft, Ban, RotateCcw, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { SimulatedBadge } from "@/components/common/simulated-badge";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { useExecutionEvents } from "@/lib/hooks/use-execution-events";
import { useLocationHash } from "@/lib/hooks/use-location-hash";
import { formatDateTime, formatDuration, formatRelative, workflowLabel } from "@/lib/format";
import { deriveNodeStatuses, graphNodeFor, isTerminalStatus } from "@/lib/node-status";
import { useExecution, useExecutionAction, useTrace, useWorkflows } from "@/lib/queries";
import type { ExecutionDetail, ExecutionReport } from "@/lib/types";
import { NodeDetails } from "./node-details";
import { ChangesTab } from "./tabs/changes-tab";
import { ConsoleTab } from "./tabs/console-tab";
import { PlanTab } from "./tabs/plan-tab";
import { PullRequestTab } from "./tabs/pull-request-tab";
import { ReviewTab } from "./tabs/review-tab";
import { TestsTab } from "./tabs/tests-tab";
import { TraceTab } from "./tabs/trace-tab";
import { VerificationTab } from "./tabs/verification-tab";
import { GraphLegend, WorkflowGraph } from "./workflow-graph";

const TAB_IDS = ["console", "plan", "changes", "tests", "review", "verification", "pr", "trace"];

function Header({ execution }: { execution: ExecutionDetail }) {
  const action = useExecutionAction(execution.id);
  const terminal = isTerminalStatus(execution.status);
  const canRetry = execution.status === "failed" && !execution.report;

  return (
    <div className="mb-5 space-y-3">
      <Link
        href="/executions"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" />
        Executions
      </Link>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={execution.status} />
            <span className="text-xs text-muted-foreground">{workflowLabel(execution.workflow)}</span>
            <span className="font-mono text-xs text-muted-foreground">{execution.id}</span>
            {execution.simulated && <SimulatedBadge />}
          </div>
          <h1 className="text-lg font-semibold tracking-tight break-words">
            {execution.request || workflowLabel(execution.workflow)}
          </h1>
          <p className="text-xs text-muted-foreground">
            <Link href={`/repositories/${execution.repository_id}`} className="hover:text-foreground hover:underline">
              {execution.repository_name ?? execution.repository_id}
            </Link>
            {" · "}created {formatRelative(execution.created_at)} by {execution.created_by ?? "unknown"} via{" "}
            {execution.source ?? "api"}
            {execution.started_at && ` · started ${formatDateTime(execution.started_at)}`}
            {execution.duration_ms !== null && ` · ${formatDuration(execution.duration_ms)}`}
            {!terminal && execution.current_node && (
              <>
                {" · "}at <span className="font-mono">{execution.current_node}</span>
              </>
            )}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {execution.pending_approval_id && (
            <Button asChild size="sm">
              <Link href={`/approvals#${execution.pending_approval_id}`}>
                <ShieldCheck />
                Review approval
              </Link>
            </Button>
          )}
          {canRetry && (
            <Button size="sm" variant="secondary" disabled={action.isPending} onClick={() => action.mutate("retry")}>
              <RotateCcw />
              Retry
            </Button>
          )}
          {!terminal && (
            <Button
              size="sm"
              variant="destructive"
              disabled={action.isPending}
              onClick={() => {
                if (window.confirm("Cancel this execution?")) action.mutate("cancel");
              }}
            >
              <Ban />
              Cancel
            </Button>
          )}
        </div>
      </div>
      {action.isError && <ErrorState error={action.error} />}
      {(execution.summary || execution.error) && (
        <div
          className={
            execution.error
              ? "rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger"
              : "rounded-md border border-border bg-muted/40 px-3 py-2 text-sm"
          }
        >
          {execution.error ?? execution.summary}
        </div>
      )}
    </div>
  );
}

export function ExecutionDetailView({ id }: { id: string }) {
  const execution = useExecution(id);
  const workflows = useWorkflows();
  const trace = useTrace(id);
  const stream = useExecutionEvents(execution.isError ? null : id);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const hash = useLocationHash();
  const [chosenTab, setTab] = useState<string | null>(null);
  const tab = chosenTab ?? (TAB_IDS.includes(hash) ? hash : "console");
  const [consoleNode, setConsoleNode] = useState<string | null>(null);

  const ex = execution.data;
  const definition = workflows.data?.find((w) => w.id === ex?.workflow);
  const report: ExecutionReport | null = ex?.report ?? ex?.state ?? null;

  const statuses = useMemo(
    () => deriveNodeStatuses(definition?.graph.nodes.map((n) => n.id) ?? [], stream.events, ex ?? null),
    [definition, stream.events, ex],
  );

  // Which agent handled each node, and how many runs it took, from the event stream.
  const { agents, runCounts } = useMemo(() => {
    const a: Record<string, string> = {};
    const c: Record<string, number> = {};
    for (const e of stream.events) {
      const n = graphNodeFor(e.node);
      if (!n) continue;
      if (e.agent_id && !a[n] && e.type === "agent.started") a[n] = e.agent_id;
      if (e.type === "agent.started") c[n] = (c[n] ?? 0) + 1;
    }
    return { agents: a, runCounts: c };
  }, [stream.events]);

  if (execution.isPending) return <LoadingState label="Loading execution…" />;
  if (execution.isError) {
    const notFound = execution.error instanceof ApiError && execution.error.status === 404;
    return notFound ? (
      <EmptyState title="Execution not found" description={`No execution with id ${id}.`}>
        <Button asChild variant="secondary" size="sm" className="mt-2">
          <Link href="/executions">All executions</Link>
        </Button>
      </EmptyState>
    ) : (
      <ErrorState error={execution.error} />
    );
  }
  if (!ex) return null;

  const counts = {
    tasks: report?.plan?.tasks?.length ?? 0,
    files: report?.changed?.length ?? 0,
    findings: report?.review?.findings?.length ?? 0,
    tests: stream.events.filter((e) => e.type === "test.passed" || e.type === "test.failed").length,
  };

  const openConsole = (node: string) => {
    setConsoleNode(node);
    setTab("console");
  };

  return (
    <>
      <Header execution={ex} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
            <h2 className="text-sm font-semibold">{definition?.title ?? workflowLabel(ex.workflow)} workflow</h2>
            <GraphLegend />
          </div>
          {workflows.isError ? (
            <ErrorState error={workflows.error} className="m-4" />
          ) : !definition ? (
            <LoadingState label="Loading workflow graph…" className="px-4" />
          ) : (
            <WorkflowGraph
              graph={definition.graph}
              statuses={statuses}
              agents={agents}
              runCounts={runCounts}
              selected={selectedNode}
              onSelect={setSelectedNode}
            />
          )}
        </Card>
        {selectedNode ? (
          <NodeDetails
            node={selectedNode}
            status={statuses[selectedNode] ?? "pending"}
            events={stream.events}
            trace={trace.data}
            onClose={() => setSelectedNode(null)}
            onOpenConsole={openConsole}
          />
        ) : (
          <Card className="hidden p-4 text-sm text-muted-foreground xl:block">
            <p className="font-medium text-foreground">Node details</p>
            <p className="mt-1">
              Select a node in the graph to see its agent runs, tool calls, events and outputs.
            </p>
            {ex.status === "awaiting_approval" && (
              <p className="mt-3 text-warning">Paused at {ex.current_node ?? "approval"} until a reviewer decides.</p>
            )}
          </Card>
        )}
      </div>

      <Tabs value={tab} onValueChange={setTab} className="mt-6">
        <TabsList>
          <TabsTrigger value="console">Console</TabsTrigger>
          <TabsTrigger value="plan">Plan{counts.tasks ? ` (${counts.tasks})` : ""}</TabsTrigger>
          <TabsTrigger value="changes">Changes{counts.files ? ` (${counts.files})` : ""}</TabsTrigger>
          <TabsTrigger value="tests">Tests{counts.tests ? ` (${counts.tests})` : ""}</TabsTrigger>
          <TabsTrigger value="review">Review{counts.findings ? ` (${counts.findings})` : ""}</TabsTrigger>
          <TabsTrigger value="verification">Verification</TabsTrigger>
          <TabsTrigger value="pr">Pull request</TabsTrigger>
          <TabsTrigger value="trace">Trace</TabsTrigger>
        </TabsList>
        <TabsContent value="console">
          <ConsoleTab
            key={consoleNode ?? "all"}
            events={stream.events}
            streamStatus={stream.status}
            initialNode={consoleNode}
          />
        </TabsContent>
        <TabsContent value="plan">
          <PlanTab plan={report?.plan} batches={report?.batches} applied={report?.applied} />
        </TabsContent>
        <TabsContent value="changes">
          <ChangesTab executionId={ex.id} />
        </TabsContent>
        <TabsContent value="tests">
          <TestsTab events={stream.events} report={report} />
        </TabsContent>
        <TabsContent value="review">
          <ReviewTab review={report?.review} />
        </TabsContent>
        <TabsContent value="verification">
          <VerificationTab verification={report?.verification} />
        </TabsContent>
        <TabsContent value="pr">
          <PullRequestTab report={report} />
        </TabsContent>
        <TabsContent value="trace">
          <TraceTab executionId={ex.id} />
        </TabsContent>
      </Tabs>
    </>
  );
}
