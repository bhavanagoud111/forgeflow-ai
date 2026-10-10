"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type BuiltInEdge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Check, CircleDashed, Loader2, PauseCircle, X } from "lucide-react";
import { memo, useMemo } from "react";
import { edgeKey, layoutGraph } from "@/lib/graph-layout";
import type { NodeStatus } from "@/lib/node-status";
import type { WorkflowGraph as Graph } from "@/lib/types";
import { cn } from "@/lib/utils";

const NODE_WIDTH = 188;
const NODE_HEIGHT = 52;

type StepData = {
  label: string;
  status: NodeStatus;
  agent: string | null;
  runs: number;
  selected: boolean;
};

type StepNodeType = Node<StepData, "step">;

const STATUS_STYLE: Record<NodeStatus, string> = {
  pending: "border-border text-muted-foreground",
  active: "border-accent text-foreground animate-node-pulse",
  waiting: "border-warning text-foreground",
  completed: "border-success/60 text-foreground",
  failed: "border-danger text-foreground",
  skipped: "border-dashed border-border text-muted-foreground opacity-60",
};

function StatusIcon({ status }: { status: NodeStatus }) {
  const cls = "size-3.5 shrink-0";
  switch (status) {
    case "active":
      return <Loader2 className={cn(cls, "animate-spin text-accent")} />;
    case "waiting":
      return <PauseCircle className={cn(cls, "text-warning")} />;
    case "completed":
      return <Check className={cn(cls, "text-success")} />;
    case "failed":
      return <X className={cn(cls, "text-danger")} />;
    default:
      return <CircleDashed className={cn(cls, "text-muted-foreground")} />;
  }
}

const StepNode = memo(function StepNode({ data }: NodeProps<StepNodeType>) {
  return (
    <div
      className={cn(
        "flex cursor-pointer flex-col justify-center rounded-md border bg-card px-3 transition-colors hover:bg-muted",
        STATUS_STYLE[data.status],
        data.selected && "ring-2 ring-ring ring-offset-1 ring-offset-background",
      )}
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
      title={`${data.label}: ${data.status}`}
    >
      <Handle type="target" position={Position.Top} id="top" isConnectable={false} />
      <Handle type="source" position={Position.Bottom} id="bottom" isConnectable={false} />
      <Handle type="source" position={Position.Right} id="loop-out" isConnectable={false} />
      <Handle type="target" position={Position.Right} id="loop-in" isConnectable={false} />
      <div className="flex items-center gap-1.5">
        <StatusIcon status={data.status} />
        <span className="truncate font-mono text-xs font-medium">{data.label}</span>
      </div>
      <span className="truncate pl-5 text-[11px] text-muted-foreground">
        {data.agent ?? data.status}
        {data.runs > 1 ? ` · ${data.runs} runs` : ""}
      </span>
    </div>
  );
});

const nodeTypes = { step: StepNode };

export interface WorkflowGraphProps {
  graph: Graph;
  statuses: Record<string, NodeStatus>;
  agents: Record<string, string>;
  runCounts: Record<string, number>;
  selected: string | null;
  onSelect: (node: string | null) => void;
}

export function WorkflowGraph({ graph, statuses, agents, runCounts, selected, onSelect }: WorkflowGraphProps) {
  const layout = useMemo(() => layoutGraph(graph, { nodeWidth: NODE_WIDTH, nodeHeight: NODE_HEIGHT }), [graph]);

  const nodes: StepNodeType[] = useMemo(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: "step",
        position: layout.positions[n.id] ?? { x: 0, y: 0 },
        data: {
          label: n.id,
          status: statuses[n.id] ?? "pending",
          agent: agents[n.id] ?? null,
          runs: runCounts[n.id] ?? 0,
          selected: selected === n.id,
        },
        draggable: false,
        connectable: false,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      })),
    [graph.nodes, layout, statuses, agents, runCounts, selected],
  );

  const edges: BuiltInEdge[] = useMemo(
    () =>
      graph.edges.map((e) => {
        const back = layout.backEdges.has(edgeKey(e.source, e.target));
        const s = statuses[e.source];
        const t = statuses[e.target];
        const traversed =
          (s === "completed" || s === "failed") &&
          (t === "completed" || t === "active" || t === "failed" || t === "waiting");
        const color = traversed ? "var(--accent)" : "var(--muted-foreground)";
        const base = {
          id: edgeKey(e.source, e.target),
          source: e.source,
          target: e.target,
          sourceHandle: back ? "loop-out" : "bottom",
          targetHandle: back ? "loop-in" : "top",
          animated: t === "active" && traversed,
          style: {
            stroke: color,
            strokeWidth: traversed ? 1.6 : 1,
            strokeDasharray: e.conditional ? "4 3" : undefined,
            opacity: traversed ? 0.95 : 0.45,
          },
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color },
          focusable: false,
        };
        return back
          ? { ...base, type: "smoothstep" as const, pathOptions: { offset: 28, borderRadius: 8 } }
          : { ...base, type: "default" as const };
      }),
    [graph.edges, layout, statuses],
  );

  return (
    <div className="h-[640px] w-full" aria-label="Workflow graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.06 }}
        minZoom={0.3}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => onSelect(node.id === selected ? null : node.id)}
        onPaneClick={() => onSelect(null)}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--graph-dot)" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}

export function GraphLegend() {
  const items: { status: NodeStatus; label: string }[] = [
    { status: "active", label: "Running" },
    { status: "waiting", label: "Waiting" },
    { status: "completed", label: "Completed" },
    { status: "failed", label: "Failed" },
    { status: "pending", label: "Pending" },
    { status: "skipped", label: "Skipped" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
      {items.map((i) => (
        <span key={i.status} className="flex items-center gap-1">
          <StatusIcon status={i.status} />
          {i.label}
        </span>
      ))}
      <span className="flex items-center gap-1">
        <svg width="18" height="6" aria-hidden="true">
          <line x1="0" y1="3" x2="18" y2="3" stroke="currentColor" strokeDasharray="4 3" />
        </svg>
        Conditional
      </span>
    </div>
  );
}
