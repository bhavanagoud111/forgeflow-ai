"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { workflowLabel } from "@/lib/format";
import { useCreateExecution, useRepositories, useWorkflows } from "@/lib/queries";
import type { WorkflowId } from "@/lib/types";

const REQUEST_HINTS: Record<WorkflowId, string> = {
  feature: "Describe the feature, e.g. Add JWT authentication to this FastAPI application",
  bug_investigation: "Describe the bug and how it shows up",
  code_review: "Optional: what the review should focus on",
  repo_onboarding: "Optional: what to focus on while onboarding",
  test_generation: "Which code should get tests",
};

export function NewExecutionDialog({
  open,
  onOpenChange,
  defaultRepositoryId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultRepositoryId?: string;
}) {
  const router = useRouter();
  const repos = useRepositories();
  const workflows = useWorkflows();
  const create = useCreateExecution();

  const [repositoryId, setRepositoryId] = useState(defaultRepositoryId ?? "");
  const [workflow, setWorkflow] = useState<WorkflowId>("feature");
  const [request, setRequest] = useState("");
  const [reviewSource, setReviewSource] = useState<"diff" | "pr">("diff");
  const [diff, setDiff] = useState("");
  const [prNumber, setPrNumber] = useState("");
  const [issue, setIssue] = useState("");

  const repoList = repos.data?.items ?? [];
  const selectedRepo = repositoryId || repoList[0]?.id || "";
  const workflowIds: WorkflowId[] = workflows.data?.map((w) => w.id) ?? [
    "feature",
    "bug_investigation",
    "code_review",
    "repo_onboarding",
    "test_generation",
  ];

  const requestRequired = workflow === "feature" || workflow === "bug_investigation";
  const reviewInvalid =
    workflow === "code_review" &&
    (reviewSource === "diff" ? !diff.trim() : !/^\d+$/.test(prNumber.trim()));
  const canSubmit = !!selectedRepo && !create.isPending && !(requestRequired && !request.trim()) && !reviewInvalid;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    const params: Record<string, unknown> = {};
    if (workflow === "code_review") {
      if (reviewSource === "diff") params.diff = diff;
      else params.pr_number = Number(prNumber.trim());
    }
    if (workflow === "bug_investigation" && /^\d+$/.test(issue.trim())) params.issue = Number(issue.trim());
    create.mutate(
      { repository_id: selectedRepo, workflow, request: request.trim(), params },
      {
        // Navigating away unmounts the dialog, so it is not closed explicitly here.
        onSuccess: (execution) => router.push(`/executions/${execution.id}`),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>New execution</DialogTitle>
          <DialogDescription>Agents work on an isolated branch. Pull requests require approval.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="ne-repo">Repository</Label>
              <Select value={selectedRepo} onValueChange={setRepositoryId} disabled={repoList.length === 0}>
                <SelectTrigger id="ne-repo">
                  <SelectValue placeholder={repos.isPending ? "Loading…" : "No repositories connected"} />
                </SelectTrigger>
                <SelectContent>
                  {repoList.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.full_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ne-workflow">Workflow</Label>
              <Select value={workflow} onValueChange={(v) => setWorkflow(v as WorkflowId)}>
                <SelectTrigger id="ne-workflow">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {workflowIds.map((w) => (
                    <SelectItem key={w} value={w}>
                      {workflows.data?.find((d) => d.id === w)?.title ?? workflowLabel(w)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {workflows.data && (
            <p className="text-xs text-muted-foreground">
              {workflows.data.find((w) => w.id === workflow)?.description}
            </p>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="ne-request">Request{requestRequired ? "" : " (optional)"}</Label>
            <Textarea
              id="ne-request"
              value={request}
              onChange={(e) => setRequest(e.target.value)}
              placeholder={REQUEST_HINTS[workflow]}
              maxLength={8000}
              rows={3}
            />
          </div>

          {workflow === "bug_investigation" && (
            <div className="space-y-1.5">
              <Label htmlFor="ne-issue">GitHub issue number (optional)</Label>
              <Input
                id="ne-issue"
                inputMode="numeric"
                value={issue}
                onChange={(e) => setIssue(e.target.value)}
                placeholder="e.g. 42"
              />
            </div>
          )}

          {workflow === "code_review" && (
            <div className="space-y-2">
              <div className="flex gap-1" role="radiogroup" aria-label="Review source">
                {(["diff", "pr"] as const).map((s) => (
                  <Button
                    key={s}
                    type="button"
                    size="sm"
                    variant={reviewSource === s ? "secondary" : "ghost"}
                    role="radio"
                    aria-checked={reviewSource === s}
                    onClick={() => setReviewSource(s)}
                  >
                    {s === "diff" ? "Paste a diff" : "Pull request number"}
                  </Button>
                ))}
              </div>
              {reviewSource === "diff" ? (
                <Textarea
                  aria-label="Unified diff"
                  value={diff}
                  onChange={(e) => setDiff(e.target.value)}
                  placeholder="diff --git a/app.py b/app.py…"
                  className="font-mono text-xs"
                  rows={8}
                />
              ) : (
                <Input
                  aria-label="Pull request number"
                  inputMode="numeric"
                  value={prNumber}
                  onChange={(e) => setPrNumber(e.target.value)}
                  placeholder="e.g. 128 (GitHub repositories only)"
                />
              )}
            </div>
          )}

          {create.isError && <ErrorState error={create.error} />}

          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {create.isPending ? "Starting…" : "Start execution"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
