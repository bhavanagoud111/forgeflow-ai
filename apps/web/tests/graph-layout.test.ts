import { describe, expect, it } from "vitest";
import { edgeKey, layoutGraph } from "@/lib/graph-layout";
import type { WorkflowGraph } from "@/lib/types";

const graph: WorkflowGraph = {
  nodes: ["prepare", "analyze", "plan", "generate", "apply", "test", "debug", "review", "report"].map((id) => ({ id })),
  edges: [
    { source: "prepare", target: "analyze", conditional: false },
    { source: "analyze", target: "plan", conditional: false },
    { source: "plan", target: "generate", conditional: true },
    { source: "plan", target: "test", conditional: true },
    { source: "generate", target: "apply", conditional: false },
    { source: "apply", target: "generate", conditional: true },
    { source: "apply", target: "test", conditional: true },
    { source: "test", target: "debug", conditional: true },
    { source: "debug", target: "test", conditional: true },
    { source: "test", target: "review", conditional: true },
    { source: "review", target: "report", conditional: false },
    { source: "debug", target: "report", conditional: true },
  ],
};

describe("layoutGraph", () => {
  const result = layoutGraph(graph);

  it("marks retry loops as back edges", () => {
    expect([...result.backEdges].sort()).toEqual([edgeKey("apply", "generate"), edgeKey("debug", "test")].sort());
  });

  it("ranks nodes by longest path from the entry", () => {
    expect(result.ranks).toMatchObject({ prepare: 0, analyze: 1, plan: 2, generate: 3, apply: 4, test: 5, debug: 6 });
    expect(result.ranks.report).toBe(7);
  });

  it("places every forward edge downward", () => {
    for (const e of graph.edges) {
      if (result.backEdges.has(edgeKey(e.source, e.target))) continue;
      expect(result.positions[e.target]!.y).toBeGreaterThan(result.positions[e.source]!.y);
    }
  });

  it("does not overlap nodes within a layer", () => {
    const byRow = new Map<number, number[]>();
    for (const p of Object.values(result.positions)) byRow.set(p.y, [...(byRow.get(p.y) ?? []), p.x]);
    for (const xs of byRow.values()) expect(new Set(xs).size).toBe(xs.length);
  });

  it("ignores edges to unknown nodes", () => {
    const r = layoutGraph({ nodes: [{ id: "a" }], edges: [{ source: "a", target: "zzz", conditional: false }] });
    expect(Object.keys(r.positions)).toEqual(["a"]);
  });
});
