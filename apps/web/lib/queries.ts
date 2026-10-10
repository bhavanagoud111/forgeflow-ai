"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "./api";
import type {
  Agent,
  Approval,
  AuditEntry,
  DiffResponse,
  Execution,
  ExecutionDetail,
  GitHubBranch,
  GitHubIssue,
  GitHubPull,
  Health,
  ListWithNote,
  Me,
  Metrics,
  Page,
  Repository,
  RepositoryDetail,
  RepositoryFile,
  RepositoryTree,
  Settings,
  Trace,
  WorkflowDefinition,
  WorkflowId,
} from "./types";
import { isTerminalStatus } from "./node-status";

const LIVE_INTERVAL = 5000;

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: () => apiGet<Health>("/api/health"), refetchInterval: 30000 });

export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => apiGet<Me>("/api/me"), staleTime: 60000 });

export const useMetrics = () =>
  useQuery({ queryKey: ["metrics"], queryFn: () => apiGet<Metrics>("/api/metrics"), refetchInterval: LIVE_INTERVAL });

export const useAgents = () =>
  useQuery({ queryKey: ["agents"], queryFn: () => apiGet<Agent[]>("/api/agents"), refetchInterval: LIVE_INTERVAL });

export const useWorkflows = () =>
  useQuery({
    queryKey: ["workflows"],
    queryFn: () => apiGet<WorkflowDefinition[]>("/api/workflows"),
    staleTime: 5 * 60000,
  });

export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: () => apiGet<Settings>("/api/settings") });

export const useAudit = (limit = 15) =>
  useQuery({
    queryKey: ["audit", limit],
    queryFn: () => apiGet<Page<AuditEntry>>("/api/audit", { limit }),
    refetchInterval: LIVE_INTERVAL * 2,
  });

export interface ExecutionFilters {
  status?: string;
  repository_id?: string;
  limit?: number;
  offset?: number;
}

export const useExecutions = (filters: ExecutionFilters = {}) =>
  useQuery({
    queryKey: ["executions", filters],
    queryFn: () => apiGet<Page<Execution>>("/api/executions", { ...filters }),
    refetchInterval: (q) =>
      q.state.data?.items.some((e) => !isTerminalStatus(e.status)) ? LIVE_INTERVAL / 2 : LIVE_INTERVAL * 2,
  });

export const useExecution = (id: string) =>
  useQuery({
    queryKey: ["execution", id],
    queryFn: () => apiGet<ExecutionDetail>(`/api/executions/${encodeURIComponent(id)}`),
    // Live updates arrive over SSE; polling is a slow safety net while running.
    refetchInterval: (q) => (q.state.data && !isTerminalStatus(q.state.data.status) ? 10000 : false),
  });

export const useTrace = (id: string) =>
  useQuery({
    queryKey: ["trace", id],
    queryFn: () => apiGet<Trace>(`/api/executions/${encodeURIComponent(id)}/trace`),
  });

export const useDiff = (id: string, enabled = true) =>
  useQuery({
    queryKey: ["diff", id],
    queryFn: () => apiGet<DiffResponse>(`/api/executions/${encodeURIComponent(id)}/diff`),
    enabled,
  });

export const useRepositories = () =>
  useQuery({
    queryKey: ["repositories"],
    queryFn: () => apiGet<Page<Repository>>("/api/repositories", { limit: 100 }),
  });

export const useRepository = (id: string) =>
  useQuery({
    queryKey: ["repository", id],
    queryFn: () => apiGet<RepositoryDetail>(`/api/repositories/${encodeURIComponent(id)}`),
  });

export const useRepositoryTree = (id: string) =>
  useQuery({
    queryKey: ["repository", id, "tree"],
    queryFn: () => apiGet<RepositoryTree>(`/api/repositories/${encodeURIComponent(id)}/tree`),
  });

export const useRepositoryFile = (id: string, path: string | null) =>
  useQuery({
    queryKey: ["repository", id, "file", path],
    queryFn: () => apiGet<RepositoryFile>(`/api/repositories/${encodeURIComponent(id)}/files`, { path }),
    enabled: !!path,
  });

export const useRepositoryList = <T,>(id: string, kind: "issues" | "pulls" | "branches") =>
  useQuery({
    queryKey: ["repository", id, kind],
    queryFn: () => apiGet<ListWithNote<T>>(`/api/repositories/${encodeURIComponent(id)}/${kind}`),
    retry: false,
  });

export const useIssues = (id: string) => useRepositoryList<GitHubIssue>(id, "issues");
export const usePulls = (id: string) => useRepositoryList<GitHubPull>(id, "pulls");
export const useBranches = (id: string) => useRepositoryList<GitHubBranch>(id, "branches");

export const useApprovals = (status?: string) =>
  useQuery({
    queryKey: ["approvals", status ?? "all"],
    queryFn: () => apiGet<Page<Approval>>("/api/approvals", { status, limit: 100 }),
    refetchInterval: LIVE_INTERVAL,
  });

// ---- mutations ----

export interface CreateExecutionInput {
  repository_id: string;
  workflow: WorkflowId;
  request: string;
  params: Record<string, unknown>;
}

export function useCreateExecution() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateExecutionInput) => apiPost<Execution>("/api/executions", input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["executions"] });
      void qc.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}

export function useExecutionAction(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: "cancel" | "retry") =>
      apiPost<Execution>(`/api/executions/${encodeURIComponent(id)}/${action}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["execution", id] });
      void qc.invalidateQueries({ queryKey: ["executions"] });
      void qc.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}

export function useConnectRepository() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { provider: "github" | "local"; full_name?: string; path?: string }) =>
      apiPost<Repository>("/api/repositories/connect", input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["repositories"] });
      void qc.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}

export function useAnalyzeRepository(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<unknown>(`/api/repositories/${encodeURIComponent(id)}/analyze`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["repository", id] });
      void qc.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export function useDecideApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; decision: "approve" | "reject"; comment: string }) =>
      apiPost<Approval>(`/api/approvals/${encodeURIComponent(input.id)}/${input.decision}`, {
        comment: input.comment.trim() || null,
      }),
    onSuccess: (approval) => {
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["metrics"] });
      void qc.invalidateQueries({ queryKey: ["executions"] });
      if (approval?.execution_id) void qc.invalidateQueries({ queryKey: ["execution", approval.execution_id] });
    },
  });
}
