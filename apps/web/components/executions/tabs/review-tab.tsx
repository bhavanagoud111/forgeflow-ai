import { EmptyState } from "@/components/common/states";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { Review, ReviewFinding } from "@/lib/types";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];
const SEVERITY_VARIANT: Record<string, BadgeVariant> = {
  critical: "danger",
  high: "danger",
  medium: "warning",
  low: "info",
  info: "neutral",
};

export function ReviewTab({ review }: { review: Review | null | undefined }) {
  if (!review) return <EmptyState title="No review yet" description="The code reviewer has not run." />;
  const findings = review.findings ?? [];
  const groups = new Map<string, ReviewFinding[]>();
  for (const f of findings) {
    const key = (f.severity || "info").toLowerCase();
    groups.set(key, [...(groups.get(key) ?? []), f]);
  }
  const ordered = [...groups.keys()].sort(
    (a, b) =>
      (SEVERITY_ORDER.indexOf(a) === -1 ? 99 : SEVERITY_ORDER.indexOf(a)) -
      (SEVERITY_ORDER.indexOf(b) === -1 ? 99 : SEVERITY_ORDER.indexOf(b)),
  );
  const bySource = findings.reduce<Record<string, number>>((acc, f) => {
    const s = f.source ?? "unknown";
    acc[s] = (acc[s] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      {review.summary && <p className="text-sm">{review.summary}</p>}
      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>{findings.length} findings</span>
        {Object.entries(bySource).map(([s, n]) => (
          <span key={s}>
            · {n} from {s === "static" ? "static analysis" : s === "model" ? "model review" : s}
          </span>
        ))}
      </div>
      {findings.length === 0 ? (
        <EmptyState title="No findings" description="The review did not report any issues." />
      ) : (
        ordered.map((sev) => (
          <section key={sev} className="space-y-2">
            <h3 className="flex items-center gap-2 text-sm font-medium capitalize">
              <Badge variant={SEVERITY_VARIANT[sev] ?? "neutral"}>{sev}</Badge>
              <span className="text-muted-foreground">{groups.get(sev)?.length}</span>
            </h3>
            {groups.get(sev)?.map((f, i) => (
              <Card key={i} className="p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{f.title}</span>
                  <Badge variant={f.source === "static" ? "outline" : "info"}>
                    {f.source === "static" ? "static" : f.source === "model" ? "model" : (f.source ?? "unknown")}
                  </Badge>
                  {f.category && <Badge variant="neutral">{f.category}</Badge>}
                </div>
                {f.file && (
                  <p className="mt-1 font-mono text-xs text-muted-foreground">
                    {f.file}
                    {f.line ? `:${f.line}` : ""}
                  </p>
                )}
                {f.detail && <p className="mt-1.5 text-sm text-muted-foreground">{f.detail}</p>}
              </Card>
            ))}
          </section>
        ))
      )}
    </div>
  );
}
