import type { Metadata } from "next";
import { AgentControlCenter } from "@/components/agents/agent-control-center";

export const metadata: Metadata = { title: "Agents" };

export default function AgentsPage() {
  return <AgentControlCenter />;
}
