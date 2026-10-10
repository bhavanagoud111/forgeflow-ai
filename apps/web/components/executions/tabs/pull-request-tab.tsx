import { ExternalLink, GitBranch } from "lucide-react";
import { SectionTitle } from "@/components/common/page-header";
import { CodeBlock } from "@/components/common/code-block";
import { EmptyState } from "@/components/common/states";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { ExecutionReport } from "@/lib/types";

export function PullRequestTab({ report }: { report: ExecutionReport | null }) {
  const draft = report?.pr_draft;
  const pr = report?.pr;
  const approval = report?.approval;
  if (!draft && !pr) {
    return <EmptyState title="No pull request yet" description="A draft is prepared after verification passes." />;
  }
  return (
    <div className="space-y-4">
      <Card className="space-y-2 p-4">
        <div className="flex flex-wrap items-center gap-2">
          {pr ? (
            pr.published ? (
              <Badge variant="success">Published</Badge>
            ) : (
              <Badge variant="neutral">Prepared locally, not published</Badge>
            )
          ) : (
            <Badge variant="warning">Draft awaiting approval</Badge>
          )}
          {(pr?.branch ?? draft?.branch) && (
            <span className="flex items-center gap-1 font-mono text-xs text-muted-foreground">
              <GitBranch className="size-3" aria-hidden="true" />
              {draft?.base ? `${draft.base} ← ` : ""}
              {pr?.branch ?? draft?.branch}
            </span>
          )}
          {pr?.commit && <span className="font-mono text-xs text-muted-foreground">{pr.commit.slice(0, 12)}</span>}
        </div>
        {pr?.url ? (
          <a
            href={pr.url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 text-sm text-accent hover:underline"
          >
            {pr.url}
            <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
        ) : (
          pr?.note && <p className="text-sm text-muted-foreground">{pr.note}</p>
        )}
        {approval?.decision && (
          <p className="text-xs text-muted-foreground">
            {approval.decision === "approved" ? "Approved" : "Rejected"} by {approval.by ?? "unknown"}
            {approval.comment ? `: “${approval.comment}”` : ""}
          </p>
        )}
      </Card>

      {draft && (
        <div className="space-y-2">
          <SectionTitle>Title</SectionTitle>
          <p className="text-sm font-medium">{draft.title}</p>
          <SectionTitle className="pt-2">Body (Markdown)</SectionTitle>
          <CodeBlock maxHeight="32rem" className="font-mono whitespace-pre-wrap">
            {draft.body}
          </CodeBlock>
        </div>
      )}
    </div>
  );
}
