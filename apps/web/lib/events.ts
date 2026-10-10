import type { ExecutionEvent } from "./types";

export interface EventLog {
  events: ExecutionEvent[];
  /** Highest sequence number merged so far (0 when empty). */
  lastSeq: number;
}

export const EMPTY_EVENT_LOG: EventLog = { events: [], lastSeq: 0 };

/**
 * Merge newly received events into the log.
 *
 * Events are ordered by `seq`. Anything with `seq <= lastSeq` was already seen
 * (for example after an SSE reconnect that replays from Last-Event-ID) and is
 * dropped, as are duplicates within the incoming batch. When nothing new arrives
 * the original object is returned so React can skip a re-render.
 */
export function mergeEvents(log: EventLog, incoming: readonly ExecutionEvent[]): EventLog {
  if (incoming.length === 0) return log;
  const fresh = incoming
    .filter((e) => Number.isFinite(e.seq) && e.seq > log.lastSeq)
    .sort((a, b) => a.seq - b.seq);
  if (fresh.length === 0) return log;

  const added: ExecutionEvent[] = [];
  let last = log.lastSeq;
  for (const event of fresh) {
    if (event.seq <= last) continue; // duplicate inside the batch
    added.push(event);
    last = event.seq;
  }
  return { events: [...log.events, ...added], lastSeq: last };
}

/** Parse one SSE `data:` payload into an event, or null if it is not one. */
export function parseEventPayload(raw: string): ExecutionEvent | null {
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    const v = value as Partial<ExecutionEvent>;
    if (typeof v.seq !== "number" || typeof v.type !== "string") return null;
    return {
      seq: v.seq,
      type: v.type,
      agent_id: v.agent_id ?? null,
      node: v.node ?? null,
      message: v.message ?? "",
      data: v.data && typeof v.data === "object" ? v.data : {},
      created_at: v.created_at ?? "",
    };
  } catch {
    return null;
  }
}

export const EVENT_TYPES = [
  "workflow.started",
  "workflow.resumed",
  "workflow.completed",
  "workflow.failed",
  "workflow.cancelled",
  "agent.started",
  "agent.completed",
  "agent.failed",
  "tool.started",
  "tool.completed",
  "tool.failed",
  "plan.created",
  "patch.applied",
  "test.passed",
  "test.failed",
  "review.completed",
  "verification.completed",
  "approval.required",
  "approval.decided",
  "pr.created",
  "log",
] as const;

export const TERMINAL_EVENT_TYPES = new Set([
  "workflow.completed",
  "workflow.failed",
  "workflow.cancelled",
]);

/** Which react-query keys should be refreshed when an event of this type arrives. */
export function cacheKeysForEvent(type: string, executionId: string): string[][] {
  const detail = ["execution", executionId];
  switch (type) {
    case "workflow.started":
    case "workflow.resumed":
      return [detail, ["executions"], ["metrics"], ["agents"]];
    case "workflow.completed":
    case "workflow.failed":
    case "workflow.cancelled":
      return [
        detail,
        ["trace", executionId],
        ["diff", executionId],
        ["executions"],
        ["metrics"],
        ["agents"],
        ["approvals"],
      ];
    case "agent.started":
    case "agent.completed":
    case "agent.failed":
      return [["trace", executionId], ["agents"]];
    case "patch.applied":
      return [detail, ["diff", executionId]];
    case "approval.required":
    case "approval.decided":
      return [detail, ["approvals"], ["metrics"]];
    case "plan.created":
    case "test.passed":
    case "test.failed":
    case "review.completed":
    case "verification.completed":
    case "pr.created":
      return [detail];
    default:
      return [];
  }
}
