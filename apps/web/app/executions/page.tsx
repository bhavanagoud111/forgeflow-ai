import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/common/states";
import { ExecutionsList } from "@/components/executions/executions-list";

export const metadata: Metadata = { title: "Executions" };

export default function ExecutionsPage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <ExecutionsList />
    </Suspense>
  );
}
