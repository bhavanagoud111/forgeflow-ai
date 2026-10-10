import { SectionTitle } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { AppliedPatch, Plan } from "@/lib/types";

export function PlanTab({
  plan,
  batches,
  applied,
}: {
  plan: Plan | null | undefined;
  batches: string[][] | null | undefined;
  applied: AppliedPatch[] | null | undefined;
}) {
  const tasks = plan?.tasks ?? [];
  if (!plan || tasks.length === 0) {
    return <EmptyState title="No plan" description="This execution has not produced a task plan." />;
  }
  const batchOf = new Map<string, number>();
  (batches ?? []).forEach((b, i) => b.forEach((t) => batchOf.set(t, i + 1)));
  const appliedBy = new Map((applied ?? []).map((a) => [a.task_id, a]));

  return (
    <div className="space-y-5">
      {plan.summary && <p className="text-sm">{plan.summary}</p>}

      {batches && batches.length > 0 && (
        <div>
          <SectionTitle>Execution batches</SectionTitle>
          <ol className="flex flex-wrap items-center gap-2 text-xs">
            {batches.map((b, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className="rounded-md border border-border bg-muted/50 px-2 py-1">
                  <span className="mr-1.5 text-muted-foreground">Batch {i + 1}</span>
                  <span className="font-mono">{b.join(", ")}</span>
                </span>
                {i < batches.length - 1 && <span className="text-muted-foreground">→</span>}
              </li>
            ))}
          </ol>
          <p className="mt-1 text-xs text-muted-foreground">Tasks in the same batch run in parallel.</p>
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {tasks.map((t) => {
          const patch = appliedBy.get(t.task_id);
          return (
            <Card key={t.task_id} className="p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">{t.task_id}</span>
                {batchOf.has(t.task_id) && <Badge variant="outline">Batch {batchOf.get(t.task_id)}</Badge>}
                {t.priority && (
                  <Badge variant={t.priority === "high" ? "warning" : "neutral"}>{t.priority} priority</Badge>
                )}
                {t.complexity && <Badge variant="neutral">Size {t.complexity}</Badge>}
                {t.kind && <Badge variant="neutral">{t.kind}</Badge>}
                {patch && <Badge variant="success">Applied</Badge>}
              </div>
              <h4 className="mt-2 text-sm font-medium">{t.title}</h4>
              {t.description && <p className="mt-1 text-sm text-muted-foreground">{t.description}</p>}
              <dl className="mt-3 space-y-2 text-xs">
                <div>
                  <dt className="text-muted-foreground">Depends on</dt>
                  <dd className="font-mono">{t.dependencies?.length ? t.dependencies.join(", ") : "none"}</dd>
                </div>
                {t.target_files && t.target_files.length > 0 && (
                  <div>
                    <dt className="text-muted-foreground">Target files</dt>
                    <dd className="font-mono">{t.target_files.join(", ")}</dd>
                  </div>
                )}
                {t.acceptance_criteria && t.acceptance_criteria.length > 0 && (
                  <div>
                    <dt className="text-muted-foreground">Acceptance criteria</dt>
                    <dd>
                      <ul className="mt-1 list-disc space-y-0.5 pl-4">
                        {t.acceptance_criteria.map((c) => (
                          <li key={c}>{c}</li>
                        ))}
                      </ul>
                    </dd>
                  </div>
                )}
                {patch?.summary && (
                  <div>
                    <dt className="text-muted-foreground">Patch</dt>
                    <dd>{patch.summary}</dd>
                  </div>
                )}
              </dl>
            </Card>
          );
        })}
      </div>

      {((plan.risks?.length ?? 0) > 0 || (plan.out_of_scope?.length ?? 0) > 0) && (
        <div className="grid gap-4 md:grid-cols-2">
          {plan.risks && plan.risks.length > 0 && (
            <div>
              <SectionTitle>Risks</SectionTitle>
              <ul className="list-disc space-y-1 pl-4 text-sm">
                {plan.risks.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}
          {plan.out_of_scope && plan.out_of_scope.length > 0 && (
            <div>
              <SectionTitle>Out of scope</SectionTitle>
              <ul className="list-disc space-y-1 pl-4 text-sm">
                {plan.out_of_scope.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
