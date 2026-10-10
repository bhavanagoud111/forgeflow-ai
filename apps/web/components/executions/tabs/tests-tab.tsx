import { SectionTitle } from "@/components/common/page-header";
import { CodeBlock } from "@/components/common/code-block";
import { EmptyState } from "@/components/common/states";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatTime } from "@/lib/format";
import type { CommandResult, Diagnosis, ExecutionEvent, ExecutionReport } from "@/lib/types";
import { CommandResultView } from "../command-result";

interface TestRunView {
  seq: number;
  node: string | null;
  passed: boolean;
  attempt: number | null;
  message: string;
  failedTests: string[];
  commands: CommandResult[];
  at: string;
}

function runsFromEvents(events: ExecutionEvent[]): TestRunView[] {
  return events
    .filter((e) => e.type === "test.passed" || e.type === "test.failed")
    .map((e) => ({
      seq: e.seq,
      node: e.node,
      passed: e.type === "test.passed",
      attempt: typeof e.data.attempt === "number" ? e.data.attempt : null,
      message: e.message,
      failedTests: Array.isArray(e.data.failed_tests) ? (e.data.failed_tests as string[]) : [],
      commands: Array.isArray(e.data.commands) ? (e.data.commands as CommandResult[]) : [],
      at: e.created_at,
    }));
}

function DiagnosisCard({ d }: { d: Diagnosis }) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="info">Debug attempt {d.attempt ?? "?"}</Badge>
        {typeof d.confidence === "number" && (
          <span className="text-xs text-muted-foreground">confidence {Math.round(d.confidence * 100)}%</span>
        )}
        {d.give_up && <Badge variant="danger">Gave up</Badge>}
      </div>
      {d.root_cause && (
        <div className="mt-3">
          <SectionTitle>Root cause</SectionTitle>
          <p className="text-sm">{d.root_cause}</p>
        </div>
      )}
      {d.fix?.summary && (
        <div className="mt-3">
          <SectionTitle>Fix</SectionTitle>
          <p className="text-sm">{d.fix.summary}</p>
          {d.applied_files && d.applied_files.length > 0 && (
            <p className="mt-1 font-mono text-xs text-muted-foreground">{d.applied_files.join(", ")}</p>
          )}
        </div>
      )}
      {d.evidence && d.evidence.length > 0 && (
        <div className="mt-3">
          <SectionTitle>Evidence</SectionTitle>
          <CodeBlock maxHeight="12rem">{d.evidence.join("\n")}</CodeBlock>
        </div>
      )}
    </Card>
  );
}

export function TestsTab({ events, report }: { events: ExecutionEvent[]; report: ExecutionReport | null }) {
  const runs = runsFromEvents(events);
  const diagnoses = report?.diagnoses ?? [];
  const latest = report?.test_run;

  if (runs.length === 0 && !latest && diagnoses.length === 0) {
    return <EmptyState title="No test runs" description="Tests have not been run for this execution." />;
  }

  return (
    <div className="space-y-5">
      {report?.reproduction?.summary && (
        <Card className="p-4">
          <SectionTitle>Reproduction</SectionTitle>
          <p className="text-sm">{report.reproduction.summary}</p>
          {report.reproduction.files && (
            <p className="mt-1 font-mono text-xs text-muted-foreground">{report.reproduction.files.join(", ")}</p>
          )}
        </Card>
      )}

      {runs.length === 0 && latest ? (
        <Card className="space-y-3 p-4">
          <div className="flex items-center gap-2">
            <Badge variant={latest.passed ? "success" : "danger"}>{latest.passed ? "Passed" : "Failed"}</Badge>
            <span className="text-sm">{latest.summary}</span>
          </div>
          {(latest.commands ?? []).map((c, i) => (
            <CommandResultView key={i} command={c} />
          ))}
        </Card>
      ) : (
        <div className="space-y-3">
          <SectionTitle>Test runs ({runs.length})</SectionTitle>
          {runs.map((r) => (
            <Card key={r.seq} className="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={r.passed ? "success" : "danger"}>{r.passed ? "Passed" : "Failed"}</Badge>
                {r.attempt !== null && <Badge variant="outline">Attempt {r.attempt}</Badge>}
                {r.node && <span className="font-mono text-xs text-muted-foreground">{r.node}</span>}
                <span className="text-sm">{r.message}</span>
                <span className="ml-auto text-xs text-muted-foreground">{formatTime(r.at)}</span>
              </div>
              {r.failedTests.length > 0 && (
                <details>
                  <summary className="cursor-pointer text-xs text-danger">
                    {r.failedTests.length} failing test{r.failedTests.length === 1 ? "" : "s"}
                  </summary>
                  <ul className="mt-1 space-y-0.5 font-mono text-xs">
                    {r.failedTests.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </details>
              )}
              {r.commands.map((c, i) => (
                <CommandResultView key={i} command={c} />
              ))}
            </Card>
          ))}
        </div>
      )}

      {diagnoses.length > 0 && (
        <div className="space-y-3">
          <SectionTitle>Debug diagnoses ({diagnoses.length})</SectionTitle>
          {diagnoses.map((d, i) => (
            <DiagnosisCard key={i} d={d} />
          ))}
        </div>
      )}
    </div>
  );
}
