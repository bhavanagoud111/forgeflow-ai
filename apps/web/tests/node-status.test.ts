import { describe, expect, it } from "vitest";
import { deriveNodeStatuses, graphNodeFor } from "@/lib/node-status";
import type { ExecutionEvent } from "@/lib/types";

let seq = 0;
const ev = (type: string, node: string | null): ExecutionEvent => ({
  seq: ++seq,
  type,
  agent_id: "x",
  node,
  message: "",
  data: {},
  created_at: "",
});

const nodes = ["prepare_workspace", "analyze", "generate_task", "run_tests", "debug", "request_approval", "report"];

describe("graphNodeFor", () => {
  it("maps parallel generate nodes to generate_task", () => {
    expect(graphNodeFor("generate:TASK-001")).toBe("generate_task");
    expect(graphNodeFor("analyze")).toBe("analyze");
    expect(graphNodeFor(null)).toBeNull();
  });
});

describe("deriveNodeStatuses", () => {
  it("tracks running, completed and pending nodes", () => {
    const events = [
      ev("agent.started", "prepare_workspace"),
      ev("agent.completed", "prepare_workspace"),
      ev("agent.started", "analyze"),
    ];
    const s = deriveNodeStatuses(nodes, events, { status: "running", current_node: "analyze" });
    expect(s.prepare_workspace).toBe("completed");
    expect(s.analyze).toBe("active");
    expect(s.run_tests).toBe("pending");
  });

  it("combines parallel sub-nodes", () => {
    const events = [
      ev("agent.started", "generate:TASK-001"),
      ev("agent.started", "generate:TASK-002"),
      ev("agent.completed", "generate:TASK-001"),
    ];
    expect(deriveNodeStatuses(nodes, events, { status: "running", current_node: null }).generate_task).toBe("active");
    events.push(ev("agent.completed", "generate:TASK-002"));
    expect(deriveNodeStatuses(nodes, events, { status: "running", current_node: null }).generate_task).toBe(
      "completed",
    );
  });

  it("marks failures and a retried node by its latest run", () => {
    const events = [ev("agent.started", "debug"), ev("agent.failed", "debug")];
    expect(deriveNodeStatuses(nodes, events, { status: "running", current_node: null }).debug).toBe("failed");
    events.push(ev("agent.started", "debug"), ev("agent.completed", "debug"));
    expect(deriveNodeStatuses(nodes, events, { status: "running", current_node: null }).debug).toBe("completed");
  });

  it("shows the approval node as waiting while awaiting approval", () => {
    const events = [
      ev("agent.started", "request_approval"),
      ev("approval.required", "request_approval"),
      ev("agent.completed", "request_approval"),
    ];
    const s = deriveNodeStatuses(nodes, events, { status: "awaiting_approval", current_node: "request_approval" });
    expect(s.request_approval).toBe("waiting");
  });

  it("marks nodes that never ran as skipped once finished", () => {
    const events = [ev("agent.started", "analyze"), ev("agent.completed", "analyze")];
    const s = deriveNodeStatuses(nodes, events, { status: "succeeded", current_node: null });
    expect(s.analyze).toBe("completed");
    expect(s.debug).toBe("skipped");
  });

  it("resolves dangling active nodes when the execution fails", () => {
    const events = [ev("agent.started", "run_tests")];
    expect(deriveNodeStatuses(nodes, events, { status: "failed", current_node: null }).run_tests).toBe("failed");
  });
});
