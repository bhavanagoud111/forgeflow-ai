"use client";

import { useQueries } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, ChevronRight, ExternalLink, File, Folder, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { CodeBlock } from "@/components/common/code-block";
import { PageHeader, SectionTitle } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { NewExecutionDialog } from "@/components/executions/new-execution-dialog";
import { ExecutionListItem } from "@/components/executions/execution-row";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiGet } from "@/lib/api";
import { buildFileTree, type TreeNode } from "@/lib/file-tree";
import { formatDateTime, formatNumber, formatRelative, humanize, workflowLabel } from "@/lib/format";
import {
  useAnalyzeRepository,
  useExecutions,
  useIssues,
  usePulls,
  useRepository,
  useRepositoryFile,
  useRepositoryTree,
} from "@/lib/queries";
import type { ExecutionDetail, RepositoryDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

function ChipList({ items, mono }: { items?: string[] | null; mono?: boolean }) {
  if (!items || items.length === 0) return <p className="text-xs text-muted-foreground">None detected</p>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((i) => (
        <Badge key={i} variant="neutral" className={cn("font-normal", mono && "font-mono")}>
          {i}
        </Badge>
      ))}
    </div>
  );
}

function profileToStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((v) => (Array.isArray(v) ? v.join(" ") : String(v)));
}

function Overview({ repo }: { repo: RepositoryDetail }) {
  const a = repo.analysis;
  const languages = Object.entries(a?.languages ?? {}).sort((x, y) => y[1] - x[1]);
  const totalFiles = languages.reduce((s, [, n]) => s + n, 0);

  if (!a && !repo.summary) {
    return <EmptyState title="Not analyzed yet" description="Run an analysis to index the repository." />;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Architecture</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">{repo.summary?.architecture ?? "No summary available."}</p>
          <div>
            <SectionTitle>Key modules</SectionTitle>
            {repo.summary?.key_modules?.length ? (
              <ul className="space-y-1 font-mono text-xs">
                {repo.summary.key_modules.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">None recorded</p>
            )}
          </div>
          {repo.summary?.risks && repo.summary.risks.length > 0 && (
            <div>
              <SectionTitle>Risks</SectionTitle>
              <ul className="list-disc space-y-1 pl-4 text-sm">
                {repo.summary.risks.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Stack</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <SectionTitle>Languages</SectionTitle>
            {languages.length === 0 ? (
              <p className="text-xs text-muted-foreground">None detected</p>
            ) : (
              <ul className="space-y-1.5">
                {languages.map(([lang, n]) => (
                  <li key={lang} className="text-xs">
                    <div className="flex justify-between">
                      <span>{lang}</span>
                      <span className="text-muted-foreground tabular-nums">
                        {n} file{n === 1 ? "" : "s"}
                      </span>
                    </div>
                    <div className="mt-1 h-1 rounded-full bg-muted">
                      <div
                        className="h-1 rounded-full bg-accent"
                        style={{ width: `${totalFiles ? (n / totalFiles) * 100 : 0}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <SectionTitle>Frameworks</SectionTitle>
            <ChipList items={a?.frameworks} />
          </div>
          <div>
            <SectionTitle>Package managers</SectionTitle>
            <ChipList items={a?.package_managers} />
          </div>
          <div>
            <SectionTitle>Entrypoints</SectionTitle>
            <ChipList items={a?.entrypoints} mono />
          </div>
          <p className="text-xs text-muted-foreground">
            {formatNumber(a?.file_count)} files · {formatNumber(a?.total_lines)} lines
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function TreeItem({
  node,
  depth,
  selected,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  if (node.type === "file") {
    return (
      <li>
        <button
          type="button"
          onClick={() => onSelect(node.path)}
          className={cn(
            "flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left font-mono text-xs",
            selected === node.path ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60",
          )}
          style={{ paddingLeft: depth * 12 + 22 }}
        >
          <File className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate">{node.name}</span>
        </button>
      </li>
    );
  }
  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-1 rounded px-1.5 py-0.5 text-left font-mono text-xs hover:bg-muted/60"
        style={{ paddingLeft: depth * 12 + 6 }}
      >
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <Folder className="size-3.5 text-accent" aria-hidden="true" />
        {node.name}
      </button>
      {open && (
        <ul>
          {node.children.map((c) => (
            <TreeItem key={c.path} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  );
}

function SourceTree({ id }: { id: string }) {
  const tree = useRepositoryTree(id);
  const [selected, setSelected] = useState<string | null>(null);
  const file = useRepositoryFile(id, selected);
  const nodes = useMemo(() => buildFileTree(tree.data?.files ?? []), [tree.data]);

  if (tree.isPending) return <LoadingState label="Loading source tree…" />;
  if (tree.isError) return <ErrorState error={tree.error} />;
  if (nodes.length === 0) return <EmptyState title="No files" description="The repository tree is empty." />;

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <Card className="max-h-[640px] overflow-auto p-2">
        <p className="px-1.5 pb-1 text-[11px] text-muted-foreground">
          {tree.data.files.length} files · source: {tree.data.source}
        </p>
        <ul>
          {nodes.map((n) => (
            <TreeItem key={n.path} node={n} depth={0} selected={selected} onSelect={setSelected} />
          ))}
        </ul>
      </Card>
      <div className="min-w-0">
        {!selected ? (
          <EmptyState title="Select a file" description="Choose a file from the tree to view its contents." />
        ) : file.isPending ? (
          <LoadingState label={`Loading ${selected}…`} />
        ) : file.isError ? (
          <ErrorState error={file.error} />
        ) : (
          <div className="space-y-2">
            <p className="font-mono text-xs text-muted-foreground">{file.data.path}</p>
            <CodeBlock maxHeight="600px">{file.data.content}</CodeBlock>
          </div>
        )}
      </div>
    </div>
  );
}

function IssuesAndPulls({ id }: { id: string }) {
  const issues = useIssues(id);
  const pulls = usePulls(id);
  const section = (
    title: string,
    q: typeof issues | typeof pulls,
    render: (item: { number: number; title: string; state: string; user: string; url: string; updated_at: string }) => React.ReactNode,
  ) => (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {q.isPending ? (
          <LoadingState />
        ) : q.isError ? (
          <ErrorState error={q.error} />
        ) : q.data.note ? (
          <p className="text-sm text-muted-foreground">{q.data.note}</p>
        ) : q.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">None open.</p>
        ) : (
          <ul className="divide-y divide-border">{q.data.items.map((i) => render(i))}</ul>
        )}
      </CardContent>
    </Card>
  );
  const row = (i: { number: number; title: string; state: string; user: string; url: string; updated_at: string }) => (
    <li key={i.number} className="flex items-start gap-2 py-2 text-sm">
      <span className="font-mono text-xs text-muted-foreground">#{i.number}</span>
      <div className="min-w-0 flex-1">
        <a href={i.url} target="_blank" rel="noreferrer noopener" className="hover:underline">
          {i.title}
          <ExternalLink className="ml-1 inline size-3 text-muted-foreground" aria-hidden="true" />
        </a>
        <p className="text-xs text-muted-foreground">
          {i.user} · updated {formatRelative(i.updated_at)}
        </p>
      </div>
      <Badge variant="neutral">{i.state}</Badge>
    </li>
  );
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {section("Open issues", issues, row)}
      {section("Open pull requests", pulls, row)}
    </div>
  );
}

function Memory({ repo }: { repo: RepositoryDetail }) {
  const m = repo.memory;
  if (!m || Object.keys(m).length === 0) {
    return <EmptyState title="No repository memory" description="Memory is written when the repository is analyzed." />;
  }
  const conventions = m.conventions?.items ?? repo.analysis?.conventions ?? [];
  const tests = m.test_structure;
  const imports = Object.entries(m.dependencies?.import_graph ?? {});
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Conventions</CardTitle>
          </CardHeader>
          <CardContent>
            {conventions.length === 0 ? (
              <p className="text-sm text-muted-foreground">None recorded.</p>
            ) : (
              <ul className="list-disc space-y-1 pl-4 text-sm">
                {conventions.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Test structure</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <SectionTitle>Test directories</SectionTitle>
              <ChipList items={tests?.test_dirs} mono />
            </div>
            <div>
              <SectionTitle>Test files</SectionTitle>
              <ChipList items={tests?.test_files} mono />
            </div>
            <div>
              <SectionTitle>Verification commands</SectionTitle>
              <ChipList items={profileToStrings(tests?.verification_profile)} mono />
            </div>
            <div>
              <SectionTitle>Lint commands</SectionTitle>
              <ChipList items={profileToStrings(tests?.lint_profile)} mono />
            </div>
          </CardContent>
        </Card>
      </div>
      {imports.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Internal imports</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 font-mono text-xs">
              {imports.map(([from, to]) => (
                <li key={from}>
                  {from} <span className="text-muted-foreground">→</span> {to.join(", ")}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
      {repo.history.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Historical memory</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {repo.history.map((h, i) => (
                <li key={i} className="text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="neutral">{humanize(h.kind)}</Badge>
                    <span className="font-medium">{h.title}</span>
                    <span className="text-xs text-muted-foreground">{formatDateTime(h.created_at)}</span>
                    {h.execution_id && (
                      <Link
                        href={`/executions/${h.execution_id}`}
                        className="font-mono text-xs text-accent hover:underline"
                      >
                        {h.execution_id}
                      </Link>
                    )}
                  </div>
                  <p className="mt-1 text-xs whitespace-pre-wrap text-muted-foreground">{h.content}</p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function RecentPlans({ id }: { id: string }) {
  const executions = useExecutions({ repository_id: id, limit: 10 });
  const withPlans = (executions.data?.items ?? []).slice(0, 5);
  const details = useQueries({
    queries: withPlans.map((e) => ({
      queryKey: ["execution", e.id],
      queryFn: () => apiGet<ExecutionDetail>(`/api/executions/${encodeURIComponent(e.id)}`),
      staleTime: 30000,
    })),
  });

  if (executions.isPending) return <LoadingState />;
  if (executions.isError) return <ErrorState error={executions.error} />;
  if (executions.data.items.length === 0) {
    return <EmptyState title="No executions for this repository" />;
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Recent executions</CardTitle>
        </CardHeader>
        <CardContent className="px-2">
          {executions.data.items.map((e) => (
            <ExecutionListItem key={e.id} execution={e} />
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recent plans</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {details.every((d) => d.isPending) && <LoadingState />}
          {details.map((d, i) => {
            const ex = d.data;
            const plan = (ex?.report ?? ex?.state)?.plan;
            if (!ex || !plan?.tasks?.length) return null;
            return (
              <div key={withPlans[i]?.id ?? i} className="rounded-md border border-border p-3">
                <div className="flex items-center gap-2">
                  <StatusBadge status={ex.status} />
                  <span className="text-xs text-muted-foreground">{workflowLabel(ex.workflow)}</span>
                  <Link href={`/executions/${ex.id}`} className="ml-auto font-mono text-xs text-accent hover:underline">
                    {ex.id}
                  </Link>
                </div>
                <p className="mt-1.5 text-sm">{plan.summary ?? ex.request}</p>
                <ul className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
                  {plan.tasks.map((t) => (
                    <li key={t.task_id}>
                      <span className="font-mono">{t.task_id}</span> {t.title}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
          {details.length > 0 &&
            details.every((d) => !d.isPending) &&
            details.every((d) => !(d.data?.report ?? d.data?.state)?.plan?.tasks?.length) && (
              <p className="text-sm text-muted-foreground">No plans in the most recent executions.</p>
            )}
        </CardContent>
      </Card>
    </div>
  );
}

export function RepositoryDetailView({ id }: { id: string }) {
  const repo = useRepository(id);
  const analyze = useAnalyzeRepository(id);
  const [newOpen, setNewOpen] = useState(false);

  if (repo.isPending) return <LoadingState label="Loading repository…" />;
  if (repo.isError) {
    return repo.error instanceof ApiError && repo.error.status === 404 ? (
      <EmptyState title="Repository not found" description={`No repository with id ${id}.`} />
    ) : (
      <ErrorState error={repo.error} />
    );
  }
  const r = repo.data;

  return (
    <>
      <Link
        href="/repositories"
        className="mb-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" />
        Repositories
      </Link>
      <PageHeader
        title={r.full_name}
        description={
          <>
            <Badge variant="neutral" className="mr-2">
              {r.provider}
            </Badge>
            {r.default_branch && <span className="font-mono text-xs">{r.default_branch}</span>}
            {" · "}
            {r.analyzed_at ? `analyzed ${formatRelative(r.analyzed_at)}` : "never analyzed"}
            {r.description ? ` · ${r.description}` : ""}
          </>
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => analyze.mutate()} disabled={analyze.isPending}>
              <RefreshCw className={cn(analyze.isPending && "animate-spin")} />
              {analyze.isPending ? "Analyzing…" : "Analyze"}
            </Button>
            <Button onClick={() => setNewOpen(true)}>
              <Plus />
              New execution
            </Button>
          </>
        }
      />
      {analyze.isError && <ErrorState error={analyze.error} className="mb-4" />}

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="source">Source</TabsTrigger>
          <TabsTrigger value="github">Issues &amp; pull requests</TabsTrigger>
          <TabsTrigger value="memory">Memory</TabsTrigger>
          <TabsTrigger value="executions">Executions &amp; plans</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <Overview repo={r} />
        </TabsContent>
        <TabsContent value="source">
          <SourceTree id={r.id} />
        </TabsContent>
        <TabsContent value="github">
          <IssuesAndPulls id={r.id} />
        </TabsContent>
        <TabsContent value="memory">
          <Memory repo={r} />
        </TabsContent>
        <TabsContent value="executions">
          <RecentPlans id={r.id} />
        </TabsContent>
      </Tabs>

      <NewExecutionDialog open={newOpen} onOpenChange={setNewOpen} defaultRepositoryId={r.id} />
    </>
  );
}
