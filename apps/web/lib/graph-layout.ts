import type { WorkflowGraph } from "./types";

export interface LayoutOptions {
  nodeWidth: number;
  nodeHeight: number;
  gapX: number;
  gapY: number;
}

export interface LayoutResult {
  positions: Record<string, { x: number; y: number }>;
  ranks: Record<string, number>;
  /** Edges that close a cycle (retry loops); drawn differently. Keyed "source->target". */
  backEdges: Set<string>;
  width: number;
  height: number;
}

export const edgeKey = (source: string, target: string) => `${source}->${target}`;

const DEFAULTS: LayoutOptions = { nodeWidth: 188, nodeHeight: 52, gapX: 32, gapY: 28 };

/**
 * Small layered layout for workflow graphs (top-to-bottom).
 *
 * 1. Depth-first search from the entry nodes (nodes with no incoming edges, in
 *    declaration order) marks edges that point back to an ancestor as back edges.
 * 2. Remaining edges form a DAG; each node's rank is its longest-path distance from
 *    an entry node.
 * 3. Nodes within a rank are ordered by the average position of their parents
 *    (barycenter heuristic) and centered horizontally.
 */
export function layoutGraph(graph: WorkflowGraph, options: Partial<LayoutOptions> = {}): LayoutResult {
  const opts = { ...DEFAULTS, ...options };
  const ids = graph.nodes.map((n) => n.id);
  const known = new Set(ids);
  const edges = graph.edges.filter((e) => known.has(e.source) && known.has(e.target));

  const outgoing = new Map<string, string[]>(ids.map((id) => [id, []]));
  const indegree = new Map<string, number>(ids.map((id) => [id, 0]));
  for (const e of edges) {
    outgoing.get(e.source)?.push(e.target);
    indegree.set(e.target, (indegree.get(e.target) ?? 0) + 1);
  }

  // Prefer declaration order when walking children, so the "main path" comes first.
  const order = new Map(ids.map((id, i) => [id, i]));
  for (const list of outgoing.values()) list.sort((a, b) => (order.get(a) ?? 0) - (order.get(b) ?? 0));

  const backEdges = new Set<string>();
  const state = new Map<string, 0 | 1 | 2>(); // 0 unvisited, 1 on stack, 2 done
  const visit = (id: string) => {
    state.set(id, 1);
    for (const next of outgoing.get(id) ?? []) {
      const s = state.get(next) ?? 0;
      if (s === 1) backEdges.add(edgeKey(id, next));
      else if (s === 0) visit(next);
    }
    state.set(id, 2);
  };
  const roots = ids.filter((id) => (indegree.get(id) ?? 0) === 0);
  for (const id of roots.length > 0 ? roots : ids.slice(0, 1)) if (!state.get(id)) visit(id);
  for (const id of ids) if (!state.get(id)) visit(id); // disconnected or cycle-only parts

  // Longest-path ranking over forward edges (Kahn's algorithm).
  const forward = edges.filter((e) => !backEdges.has(edgeKey(e.source, e.target)));
  const fIn = new Map<string, number>(ids.map((id) => [id, 0]));
  const fOut = new Map<string, string[]>(ids.map((id) => [id, []]));
  const parents = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of forward) {
    fIn.set(e.target, (fIn.get(e.target) ?? 0) + 1);
    fOut.get(e.source)?.push(e.target);
    parents.get(e.target)?.push(e.source);
  }
  const ranks: Record<string, number> = Object.fromEntries(ids.map((id) => [id, 0]));
  const queue = ids.filter((id) => (fIn.get(id) ?? 0) === 0);
  while (queue.length > 0) {
    const id = queue.shift() as string;
    for (const next of fOut.get(id) ?? []) {
      ranks[next] = Math.max(ranks[next] ?? 0, (ranks[id] ?? 0) + 1);
      const remaining = (fIn.get(next) ?? 0) - 1;
      fIn.set(next, remaining);
      if (remaining === 0) queue.push(next);
    }
  }

  // Group by rank and order using parent barycenters.
  const layers: string[][] = [];
  for (const id of ids) {
    const r = ranks[id] ?? 0;
    (layers[r] ??= []).push(id);
  }
  const indexInLayer = new Map<string, number>();
  layers.forEach((layer, r) => {
    if (r > 0) {
      const score = (id: string) => {
        const ps = parents.get(id) ?? [];
        if (ps.length === 0) return order.get(id) ?? 0;
        return ps.reduce((sum, p) => sum + (indexInLayer.get(p) ?? 0), 0) / ps.length;
      };
      layer.sort((a, b) => score(a) - score(b) || (order.get(a) ?? 0) - (order.get(b) ?? 0));
    }
    layer.forEach((id, i) => indexInLayer.set(id, i));
  });

  const widest = Math.max(1, ...layers.map((l) => l?.length ?? 0));
  const width = widest * opts.nodeWidth + (widest - 1) * opts.gapX;
  const positions: LayoutResult["positions"] = {};
  layers.forEach((layer, r) => {
    const rowWidth = layer.length * opts.nodeWidth + (layer.length - 1) * opts.gapX;
    const offset = (width - rowWidth) / 2;
    layer.forEach((id, i) => {
      positions[id] = {
        x: offset + i * (opts.nodeWidth + opts.gapX),
        y: r * (opts.nodeHeight + opts.gapY),
      };
    });
  });

  return {
    positions,
    ranks,
    backEdges,
    width,
    height: layers.length * opts.nodeHeight + Math.max(0, layers.length - 1) * opts.gapY,
  };
}
