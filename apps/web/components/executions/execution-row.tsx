import Link from "next/link";
import { StatusBadge } from "@/components/common/status-badge";
import { formatDuration, formatRelative, workflowLabel } from "@/lib/format";
import type { Execution } from "@/lib/types";

/** Compact list item used on the dashboard and repository pages. */
export function ExecutionListItem({ execution }: { execution: Execution }) {
  return (
    <Link
      href={`/executions/${execution.id}`}
      className="flex items-center gap-3 rounded-md px-2 py-2 transition-colors hover:bg-muted/60"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">{execution.request || workflowLabel(execution.workflow)}</p>
        <p className="truncate text-xs text-muted-foreground">
          {workflowLabel(execution.workflow)} · {execution.repository_name ?? execution.repository_id} ·{" "}
          {formatRelative(execution.created_at)}
          {execution.duration_ms !== null && ` · ${formatDuration(execution.duration_ms)}`}
        </p>
      </div>
      <StatusBadge status={execution.status} />
    </Link>
  );
}
