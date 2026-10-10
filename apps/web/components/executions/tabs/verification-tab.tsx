import { CheckCircle2, XCircle } from "lucide-react";
import { SectionTitle } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Verification } from "@/lib/types";
import { CommandResultView } from "../command-result";

function Flag({ label, value }: { label: string; value: boolean | undefined }) {
  if (value === undefined) return null;
  return <Badge variant={value ? "success" : "danger"}>{`${label}: ${value ? "yes" : "no"}`}</Badge>;
}

export function VerificationTab({ verification }: { verification: Verification | null | undefined }) {
  if (!verification) {
    return <EmptyState title="Not verified yet" description="The verifier has not completed for this execution." />;
  }
  const criteria = verification.criteria ?? [];
  const met = criteria.filter((c) => c.met).length;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Flag label="Complete" value={verification.complete} />
        <Flag label="Tests passed" value={verification.tests_passed} />
        <Flag label="Lint passed" value={verification.lint_passed} />
        {verification.summary && <span className="text-sm">{verification.summary}</span>}
      </div>

      <div>
        <SectionTitle>
          Acceptance criteria ({met}/{criteria.length} met)
        </SectionTitle>
        {criteria.length === 0 ? (
          <p className="text-sm text-muted-foreground">No criteria were evaluated.</p>
        ) : (
          <div className="rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-10">Met</TableHead>
                  <TableHead>Task</TableHead>
                  <TableHead>Criterion</TableHead>
                  <TableHead>Evidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {criteria.map((c, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      {c.met ? (
                        <CheckCircle2 className="size-4 text-success" aria-label="met" />
                      ) : (
                        <XCircle className="size-4 text-danger" aria-label="not met" />
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs whitespace-nowrap">{c.task_id ?? "—"}</TableCell>
                    <TableCell>{c.criterion}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{c.evidence ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {verification.commands && verification.commands.length > 0 && (
        <div className="space-y-3">
          <SectionTitle>Commands</SectionTitle>
          {verification.commands.map((c, i) => (
            <CommandResultView key={i} command={c} />
          ))}
        </div>
      )}
    </div>
  );
}
