"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDuration, formatRelative, shortId, workflowLabel } from "@/lib/format";
import { useExecutions } from "@/lib/queries";
import { NewExecutionDialog } from "./new-execution-dialog";

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "queued,running,resuming", label: "Active" },
  { value: "awaiting_approval", label: "Awaiting approval" },
  { value: "succeeded", label: "Succeeded" },
  { value: "failed", label: "Failed" },
  { value: "blocked", label: "Blocked" },
  { value: "rejected", label: "Rejected" },
  { value: "cancelled", label: "Cancelled" },
];

const PAGE_SIZE = 25;

export function ExecutionsList() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const rawStatus = params.get("status") ?? "all";
  const status = rawStatus === "running" ? "queued,running,resuming" : rawStatus;
  const offset = Math.max(0, Number(params.get("offset") ?? 0) || 0);
  const dialogOpen = params.get("new") === "1";

  const executions = useExecutions({
    status: status === "all" ? undefined : status,
    limit: PAGE_SIZE,
    offset,
  });

  const setParams = (update: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(update)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const total = executions.data?.total ?? 0;
  const knownFilter = STATUS_FILTERS.some((f) => f.value === status);

  return (
    <>
      <PageHeader
        title="Executions"
        description="Workflow runs across all repositories."
        actions={
          <Button onClick={() => setParams({ new: "1" })}>
            <Plus />
            New execution
          </Button>
        }
      />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          value={knownFilter ? status : "all"}
          onValueChange={(v) => setParams({ status: v === "all" ? null : v, offset: null })}
        >
          <SelectTrigger className="w-48" aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_FILTERS.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {executions.data && (
          <span className="text-xs text-muted-foreground">
            {total} execution{total === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {executions.isError ? (
        <ErrorState error={executions.error} />
      ) : executions.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : executions.data.items.length === 0 ? (
        <EmptyState
          title={status === "all" ? "No executions yet" : "No executions match this filter"}
          description={status === "all" ? "Start one with “New execution”." : undefined}
        />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Execution</TableHead>
                <TableHead>Request</TableHead>
                <TableHead>Workflow</TableHead>
                <TableHead>Repository</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Node</TableHead>
                <TableHead className="text-right">Duration</TableHead>
                <TableHead className="text-right">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {executions.data.items.map((e) => (
                <TableRow key={e.id} className="cursor-pointer" onClick={() => router.push(`/executions/${e.id}`)}>
                  <TableCell>
                    <Link
                      href={`/executions/${e.id}`}
                      className="font-mono text-xs text-accent hover:underline"
                      onClick={(ev) => ev.stopPropagation()}
                    >
                      {shortId(e.id)}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-[22rem]">
                    <p className="truncate">{e.request || "—"}</p>
                    {e.summary && <p className="truncate text-xs text-muted-foreground">{e.summary}</p>}
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{workflowLabel(e.workflow)}</TableCell>
                  <TableCell className="whitespace-nowrap">{e.repository_name ?? e.repository_id}</TableCell>
                  <TableCell>
                    <StatusBadge status={e.status} />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{e.current_node ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatDuration(e.duration_ms)}</TableCell>
                  <TableCell className="text-right whitespace-nowrap text-muted-foreground">
                    {formatRelative(e.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {total > PAGE_SIZE && (
        <div className="mt-3 flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={offset === 0}
            onClick={() => setParams({ offset: String(Math.max(0, offset - PAGE_SIZE)) })}
          >
            Previous
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setParams({ offset: String(offset + PAGE_SIZE) })}
          >
            Next
          </Button>
        </div>
      )}

      <NewExecutionDialog open={dialogOpen} onOpenChange={(o) => setParams({ new: o ? "1" : null })} />
    </>
  );
}
