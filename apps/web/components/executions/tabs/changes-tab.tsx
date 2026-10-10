"use client";

import { DiffViewer } from "@/components/diff/diff-viewer";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useDiff } from "@/lib/queries";

export function ChangesTab({ executionId }: { executionId: string }) {
  const diff = useDiff(executionId);
  if (diff.isPending) return <LoadingState label="Loading diff…" />;
  if (diff.isError) return <ErrorState error={diff.error} />;
  return <DiffViewer diff={diff.data.diff ?? ""} emptyMessage="No changes have been made yet." />;
}
