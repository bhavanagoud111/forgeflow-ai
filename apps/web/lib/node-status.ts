import type { ExecutionEvent, ExecutionStatus } from "./types";

export type NodeStatus = "pending" | "active" | "waiting" | "completed" | "failed" | "skipped";

const TERMINAL: ReadonlySet<string> = new Set(["succeeded", "failed", "blocked", "rejected", "cancelled"]);

export function isTerminalStatus(status: string): boolean {
  return TERMINAL.has(status);
}

/** Events for parallel task generation use `generate:TASK-001`; the graph node is `generate_task`. */
export function graphNodeFor(eventNode: string | null | undefined): string | null {
  if (!eventNode) return null;
  if (eventNode.startsWith("generate:")) return "generate_task";
  return eventNode;
}

/**
 * Derive a display status for every graph node from the event stream.
 *
 * Agent lifecycle events drive the status of each event node (`agent.started` ->
 * active, `agent.completed` -> completed, `agent.failed` -> failed). Parallel
 * sub-nodes (`generate:TASK-*`) are combined: any active wins, then any failed,
 * then completed. Nodes that only emit non-agent events are treated as completed
 * once seen. When the execution has finished, nodes that never ran are "skipped"
 * and nodes still marked active take the final outcome.
 */
export function deriveNodeStatuses(
  nodeIds: readonly string[],
  events: readonly ExecutionEvent[],
  execution: { status: ExecutionStatus | string; current_node: string | null } | null,
): Record<string, NodeStatus> {
  const perEventNode = new Map<string, NodeStatus>();
  for (const e of events) {
    if (!e.node) continue;
    const prev = perEventNode.get(e.node);
    if (e.type === "agent.started") perEventNode.set(e.node, "active");
    else if (e.type === "agent.completed") perEventNode.set(e.node, "completed");
    else if (e.type === "agent.failed") perEventNode.set(e.node, "failed");
    else if (e.type === "approval.required") perEventNode.set(e.node, prev === "active" ? "active" : "waiting");
    else if (!prev) perEventNode.set(e.node, "completed");
  }
  // Approval nodes stop waiting once a decision is recorded.
  if (events.some((e) => e.type === "approval.decided")) {
    for (const [node, s] of perEventNode) if (s === "waiting") perEventNode.set(node, "completed");
  }

  const combined = new Map<string, NodeStatus[]>();
  for (const [node, s] of perEventNode) {
    const g = graphNodeFor(node);
    if (!g) continue;
    const list = combined.get(g) ?? [];
    list.push(s);
    combined.set(g, list);
  }

  const status = execution?.status ?? "running";
  const terminal = isTerminalStatus(status);
  const result: Record<string, NodeStatus> = {};
  for (const id of nodeIds) {
    const list = combined.get(id);
    let s: NodeStatus;
    if (!list || list.length === 0) s = terminal ? "skipped" : "pending";
    else if (list.includes("active")) s = "active";
    else if (list.includes("waiting")) s = "waiting";
    else if (list.includes("failed")) s = "failed";
    else s = "completed";

    if (terminal && (s === "active" || s === "waiting")) {
      s = status === "succeeded" ? "completed" : "failed";
    }
    result[id] = s;
  }

  const current = graphNodeFor(execution?.current_node);
  if (current && current in result && !terminal) {
    if (status === "awaiting_approval") result[current] = "waiting";
    else if (result[current] === "pending") result[current] = "active";
  }
  return result;
}
