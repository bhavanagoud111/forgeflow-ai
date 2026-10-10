"use client";

import { Check, FileDiff, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader, SectionTitle } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/common/states";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime, formatRelative, humanize } from "@/lib/format";
import { useLocationHash } from "@/lib/hooks/use-location-hash";
import { useApprovals, useDecideApproval } from "@/lib/queries";
import type { Approval } from "@/lib/types";
import { cn } from "@/lib/utils";

const FILE_VARIANT: Record<string, BadgeVariant> = {
  added: "success",
  deleted: "danger",
  modified: "info",
  renamed: "warning",
};

function PendingApproval({ approval, highlighted }: { approval: Approval; highlighted: boolean }) {
  const decide = useDecideApproval();
  const [comment, setComment] = useState("");
  const d = approval.details;
  const files = d.files ?? [];

  const submit = (decision: "approve" | "reject") => {
    if (decision === "reject" && !window.confirm("Reject this request? The execution will end without a pull request.")) {
      return;
    }
    decide.mutate({ id: approval.id, decision, comment });
  };

  return (
    <Card id={approval.id} className={cn("scroll-mt-6 overflow-hidden", highlighted && "border-accent")}>
      <div className="flex flex-col gap-2 border-b border-border px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={approval.status} />
            <Badge variant="outline">{humanize(approval.action)}</Badge>
            <span className="text-xs text-muted-foreground">requested {formatRelative(approval.created_at)}</span>
          </div>
          <h3 className="mt-1.5 font-medium">{approval.title}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {d.repository}
            {d.branch && (
              <>
                {" · "}
                <span className="font-mono">
                  {d.base ? `${d.base} ← ` : ""}
                  {d.branch}
                </span>
              </>
            )}
            {" · "}
            <Link href={`/executions/${approval.execution_id}`} className="font-mono text-accent hover:underline">
              {approval.execution_id}
            </Link>
          </p>
        </div>
        <Button asChild variant="secondary" size="sm">
          <Link href={`/executions/${approval.execution_id}#changes`}>
            <FileDiff />
            View diff
          </Link>
        </Button>
      </div>

      <div className="grid gap-4 px-4 py-3 lg:grid-cols-2">
        <div className="space-y-3">
          <div>
            <SectionTitle>Files ({files.length})</SectionTitle>
            {files.length === 0 ? (
              <p className="text-xs text-muted-foreground">No file list provided.</p>
            ) : (
              <ul className="space-y-1">
                {files.map((f) => (
                  <li key={f.path} className="flex items-center gap-2 text-xs">
                    <Badge variant={FILE_VARIANT[f.status] ?? "neutral"} className="w-16 justify-center">
                      {f.status}
                    </Badge>
                    <span className="truncate font-mono">{f.path}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <div className="space-y-3">
          <div>
            <SectionTitle>Verification</SectionTitle>
            <p className="text-sm">{d.verification ?? "No verification summary."}</p>
          </div>
          {d.review_summary && (
            <div>
              <SectionTitle>Review</SectionTitle>
              <p className="text-sm">{d.review_summary}</p>
            </div>
          )}
          <div>
            <SectionTitle>Requested permissions</SectionTitle>
            {approval.requested_permissions.length === 0 ? (
              <p className="text-xs text-muted-foreground">None</p>
            ) : (
              <ul className="list-disc space-y-0.5 pl-4 text-sm">
                {approval.requested_permissions.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}
            {d.publish === false && (
              <p className="mt-1 text-xs text-muted-foreground">
                Approving prepares the pull request locally; nothing is pushed to a remote.
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-2 border-t border-border bg-muted/30 px-4 py-3">
        <Label htmlFor={`comment-${approval.id}`}>Comment (optional)</Label>
        <Textarea
          id={`comment-${approval.id}`}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          maxLength={2000}
          rows={2}
          placeholder="Recorded with your decision"
        />
        {decide.isError && <ErrorState error={decide.error} />}
        <div className="flex justify-end gap-2">
          <Button variant="destructive" onClick={() => submit("reject")} disabled={decide.isPending}>
            <X />
            Reject
          </Button>
          <Button onClick={() => submit("approve")} disabled={decide.isPending}>
            <Check />
            Approve
          </Button>
        </div>
      </div>
    </Card>
  );
}

export function ApprovalsView() {
  const approvals = useApprovals();
  const hash = useLocationHash();

  const items = approvals.data?.items ?? [];
  const pending = items.filter((a) => a.status === "pending");
  const history = items.filter((a) => a.status !== "pending");

  useEffect(() => {
    if (hash && approvals.data) document.getElementById(hash)?.scrollIntoView({ behavior: "smooth" });
  }, [hash, approvals.data]);

  return (
    <>
      <PageHeader title="Approvals" description="Human review before agents publish changes." />
      {approvals.isError ? (
        <ErrorState error={approvals.error} />
      ) : approvals.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <div className="space-y-8">
          <section>
            <SectionTitle>Pending ({pending.length})</SectionTitle>
            {pending.length === 0 ? (
              <EmptyState title="No pending approvals" description="Requests appear here when an execution needs a decision." />
            ) : (
              <div className="space-y-4">
                {pending.map((a) => (
                  <PendingApproval key={a.id} approval={a} highlighted={hash === a.id} />
                ))}
              </div>
            )}
          </section>

          <section>
            <SectionTitle>History ({history.length})</SectionTitle>
            {history.length === 0 ? (
              <EmptyState title="No decisions yet" />
            ) : (
              <Card>
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Request</TableHead>
                      <TableHead>Execution</TableHead>
                      <TableHead>Decision</TableHead>
                      <TableHead>By</TableHead>
                      <TableHead>Comment</TableHead>
                      <TableHead className="text-right">Decided</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {history.map((a) => (
                      <TableRow key={a.id} id={a.id}>
                        <TableCell className="max-w-xs">
                          <p className="truncate">{a.title}</p>
                          <p className="text-xs text-muted-foreground">{humanize(a.action)}</p>
                        </TableCell>
                        <TableCell>
                          <Link
                            href={`/executions/${a.execution_id}`}
                            className="font-mono text-xs text-accent hover:underline"
                          >
                            {a.execution_id}
                          </Link>
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={a.status} />
                        </TableCell>
                        <TableCell className="text-xs">{a.decided_by ?? "—"}</TableCell>
                        <TableCell className="max-w-xs text-xs text-muted-foreground">
                          {a.decision_comment ?? "—"}
                        </TableCell>
                        <TableCell className="text-right text-xs whitespace-nowrap text-muted-foreground">
                          {formatDateTime(a.decided_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            )}
          </section>
        </div>
      )}
    </>
  );
}
