import { describe, expect, it } from "vitest";
import { EMPTY_EVENT_LOG, cacheKeysForEvent, mergeEvents, parseEventPayload } from "@/lib/events";
import type { ExecutionEvent } from "@/lib/types";

const ev = (seq: number, type = "log"): ExecutionEvent => ({
  seq,
  type,
  agent_id: "orchestrator",
  node: null,
  message: `event ${seq}`,
  data: {},
  created_at: "2026-10-10T16:36:52.478952Z",
});

describe("mergeEvents", () => {
  it("appends new events in seq order", () => {
    const log = mergeEvents(EMPTY_EVENT_LOG, [ev(2), ev(1), ev(3)]);
    expect(log.events.map((e) => e.seq)).toEqual([1, 2, 3]);
    expect(log.lastSeq).toBe(3);
  });

  it("ignores events at or below the last seen seq (reconnect replay)", () => {
    const first = mergeEvents(EMPTY_EVENT_LOG, [ev(1), ev(2), ev(3)]);
    const next = mergeEvents(first, [ev(2), ev(3), ev(4)]);
    expect(next.events.map((e) => e.seq)).toEqual([1, 2, 3, 4]);
    expect(next.lastSeq).toBe(4);
  });

  it("drops duplicates inside one batch", () => {
    const log = mergeEvents(EMPTY_EVENT_LOG, [ev(5), ev(5), ev(6)]);
    expect(log.events.map((e) => e.seq)).toEqual([5, 6]);
  });

  it("returns the same object when nothing is new", () => {
    const log = mergeEvents(EMPTY_EVENT_LOG, [ev(1), ev(2)]);
    expect(mergeEvents(log, [ev(1), ev(2)])).toBe(log);
    expect(mergeEvents(log, [])).toBe(log);
  });

  it("does not mutate the previous log", () => {
    const log = mergeEvents(EMPTY_EVENT_LOG, [ev(1)]);
    mergeEvents(log, [ev(2)]);
    expect(log.events).toHaveLength(1);
    expect(EMPTY_EVENT_LOG.events).toHaveLength(0);
  });
});

describe("parseEventPayload", () => {
  it("parses a valid payload", () => {
    const parsed = parseEventPayload(
      JSON.stringify({ seq: 7, type: "agent.started", agent_id: "verifier", node: "run_tests", message: "m", data: { a: 1 }, created_at: "x" }),
    );
    expect(parsed).toMatchObject({ seq: 7, type: "agent.started", node: "run_tests", data: { a: 1 } });
  });

  it("rejects malformed payloads", () => {
    expect(parseEventPayload("not json")).toBeNull();
    expect(parseEventPayload(JSON.stringify({ status: "succeeded" }))).toBeNull();
    expect(parseEventPayload("null")).toBeNull();
  });

  it("fills defaults for missing optional fields", () => {
    expect(parseEventPayload(JSON.stringify({ seq: 1, type: "log" }))).toEqual({
      seq: 1,
      type: "log",
      agent_id: null,
      node: null,
      message: "",
      data: {},
      created_at: "",
    });
  });
});

describe("cacheKeysForEvent", () => {
  it("refreshes execution detail and lists on terminal events", () => {
    const keys = cacheKeysForEvent("workflow.completed", "exec_1");
    expect(keys).toContainEqual(["execution", "exec_1"]);
    expect(keys).toContainEqual(["executions"]);
    expect(keys).toContainEqual(["metrics"]);
  });

  it("refreshes the diff when a patch is applied", () => {
    expect(cacheKeysForEvent("patch.applied", "exec_1")).toContainEqual(["diff", "exec_1"]);
  });

  it("ignores tool chatter", () => {
    expect(cacheKeysForEvent("tool.started", "exec_1")).toEqual([]);
  });
});
