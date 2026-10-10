import type { Metadata } from "next";
import { ExecutionDetailView } from "@/components/executions/execution-detail";

export const metadata: Metadata = { title: "Execution" };

export default async function ExecutionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ExecutionDetailView key={id} id={decodeURIComponent(id)} />;
}
