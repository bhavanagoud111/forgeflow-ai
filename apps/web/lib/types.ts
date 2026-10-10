// Types mirror the ForgeFlow API responses. Report/state payloads are produced by
// agents and vary by workflow, so most of their fields are optional.

export type WorkflowId =
  | "feature"
  | "bug_investigation"
  | "code_review"
  | "repo_onboarding"
  | "test_generation";

export type ExecutionStatus =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "resuming"
  | "succeeded"
  | "failed"
  | "blocked"
  | "rejected"
  | "cancelled";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}

export interface Health {
  status: string;
  version: string;
  database: boolean;
  llm_provider: string;
  simulated_llm: boolean;
  sandbox: string;
  github: boolean;
  slack: boolean;
}

export interface Me {
  id: string;
  name: string;
  role: string;
}

export interface Execution {
  id: string;
  workflow: WorkflowId;
  repository_id: string;
  repository_name: string | null;
  request: string;
  params: Record<string, unknown>;
  status: ExecutionStatus;
  current_node: string | null;
  summary: string | null;
  error: string | null;
  created_by: string | null;
  source: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface ExecutionDetail extends Execution {
  report: ExecutionReport | null;
  state: ExecutionReport | null;
  pending_approval_id: string | null;
  simulated: boolean;
}

export interface PlanTask {
  task_id: string;
  title: string;
  description?: string;
  dependencies?: string[];
  priority?: string;
  acceptance_criteria?: string[];
  target_files?: string[];
  complexity?: string;
  kind?: string;
}

export interface Plan {
  summary?: string;
  tasks?: PlanTask[];
  risks?: string[];
  out_of_scope?: string[];
}

export interface CommandResult {
  argv: string[];
  exit_code: number | null;
  duration_ms?: number;
  stdout?: string;
  stderr?: string;
  timed_out?: boolean;
  sandbox?: string;
}

export interface TestRun {
  passed?: boolean;
  commands?: CommandResult[];
  summary?: string;
  failed_tests?: string[];
}

export interface FileEdit {
  path: string;
  operation?: string;
  search?: string | null;
  replacement?: string | null;
  content?: string | null;
}

export interface Diagnosis {
  attempt?: number;
  root_cause?: string;
  evidence?: string[];
  confidence?: number;
  fix?: { task_id?: string; summary?: string; edits?: FileEdit[]; notes?: string[] } | null;
  give_up?: boolean;
  applied_files?: string[];
}

export interface ReviewFinding {
  severity: string;
  category?: string;
  file?: string | null;
  line?: number | null;
  title: string;
  detail?: string;
  source?: string;
}

export interface Review {
  summary?: string;
  findings?: ReviewFinding[];
}

export interface VerificationCriterion {
  task_id?: string;
  criterion: string;
  met: boolean;
  evidence?: string;
}

export interface Verification {
  complete?: boolean;
  tests_passed?: boolean;
  lint_passed?: boolean;
  criteria?: VerificationCriterion[];
  commands?: CommandResult[];
  summary?: string;
}

export interface PullRequestDraft {
  title?: string;
  body?: string;
  branch?: string;
  base?: string;
}

export interface PullRequestResult {
  published?: boolean;
  branch?: string;
  commit?: string | null;
  url?: string | null;
  note?: string | null;
  number?: number | null;
}

export interface ChangedFile {
  status: string;
  path: string;
}

export interface AppliedPatch {
  task_id?: string;
  files?: string[];
  summary?: string;
  notes?: string[];
}

export interface ExecutionReport {
  outcome?: string;
  reason?: string;
  workflow?: string;
  repository?: string;
  branch?: string;
  next?: string | null;
  plan?: Plan | null;
  batches?: string[][] | null;
  applied?: AppliedPatch[] | null;
  changed?: ChangedFile[] | null;
  diff?: string | null;
  test_run?: TestRun | null;
  test_runs?: number;
  debug_attempts?: number;
  diagnoses?: Diagnosis[] | null;
  review?: Review | null;
  verification?: Verification | null;
  pr_draft?: PullRequestDraft | null;
  pr?: PullRequestResult | null;
  approval?: { id?: string; decision?: string; by?: string; comment?: string | null } | null;
  analysis_summary?: RepositorySummary | null;
  reproduction?: { files?: string[]; summary?: string } | null;
  /** Repository summary while running; shape varies by workflow. */
  summary?: unknown;
  simulated?: boolean;
  [key: string]: unknown;
}

export interface ExecutionEvent {
  seq: number;
  type: string;
  agent_id: string | null;
  node: string | null;
  message: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface AgentRun {
  id: string;
  execution_id: string;
  agent_id: string;
  node: string;
  attempt: number;
  status: string;
  provider: string | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  llm_calls: number;
  error: string | null;
  trace_id: string | null;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
}

export interface ToolCall {
  id: string;
  execution_id: string;
  agent_run_id: string | null;
  agent_id: string;
  tool: string;
  arguments: Record<string, unknown>;
  status: string;
  result_summary: string | null;
  error: string | null;
  started_at: string;
  duration_ms: number | null;
}

export interface Trace {
  execution_id: string;
  runs: AgentRun[];
  tool_calls: ToolCall[];
  totals: {
    runs: number;
    tool_calls: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    llm_calls: number;
    failed_runs: number;
    retries: number;
    tool_errors: number;
  };
}

export interface DiffResponse {
  diff: string;
  changed: ChangedFile[];
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  responsibilities: string[];
  tools: string[];
  uses_llm: boolean;
  state: "active" | "idle" | "error" | string;
  active_executions: string[];
  recent_nodes: string[];
  last_run: AgentRun | null;
  runs_total: number;
  failures_total: number;
  avg_duration_ms: number | null;
  recent_tools: ToolCall[];
}

export interface WorkflowGraph {
  nodes: { id: string }[];
  edges: { source: string; target: string; conditional: boolean }[];
}

export interface WorkflowDefinition {
  id: WorkflowId;
  title: string;
  description: string;
  graph: WorkflowGraph;
}

export interface Metrics {
  executions: {
    total: number;
    by_status: Record<string, number>;
    by_workflow: Record<string, number>;
    active: number;
    completed: number;
    failed: number;
  };
  avg_duration_ms: number | null;
  pending_approvals: number;
  repositories: number;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    agent_runs: number;
    tool_errors: number;
  };
  agents: { agent_id: string; runs: number; avg_duration_ms: number | null }[];
  daily: { date: string; succeeded: number; failed: number; other: number }[];
}

export interface Settings {
  llm: { provider: string; model: string; simulated: boolean; api_key_configured: boolean };
  github: { configured: boolean; auth: string | null; api_url: string };
  slack: { configured: boolean; bot_token_configured: boolean; authorized_users: number };
  limits: {
    execution_timeout_seconds: number;
    node_timeout_seconds: number;
    max_debug_attempts: number;
    max_parallel_tasks: number;
    max_patch_files: number;
    rate_limit_per_minute: number;
  };
  sandbox: {
    mode: string;
    image: string;
    cpus: number;
    memory_mb: number;
    pids_limit: number;
    command_timeout_seconds: number;
    allow_dependency_install: boolean;
    allow_unsafe_local_sandbox: boolean;
  };
  retention: { workspace_hours: number; event_days: number; history_days: number };
  observability: { otlp_endpoint_configured: boolean };
}

export interface Approval {
  id: string;
  execution_id: string;
  action: string;
  title: string;
  details: {
    repository?: string;
    branch?: string;
    base?: string;
    files?: ChangedFile[];
    verification?: string;
    review_summary?: string;
    publish?: boolean;
    [key: string]: unknown;
  };
  requested_permissions: string[];
  status: "pending" | "approved" | "rejected" | "expired" | string;
  decided_by: string | null;
  decision_comment: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface RepositorySummary {
  architecture?: string;
  key_modules?: string[];
  conventions?: string[];
  risks?: string[];
}

export interface Repository {
  id: string;
  provider: "github" | "local" | string;
  full_name: string;
  default_branch: string | null;
  description: string | null;
  analyzed_at: string | null;
  created_at: string;
  summary: RepositorySummary | null;
}

export interface ModuleInfo {
  path: string;
  language?: string;
  symbols?: string[];
  imports?: string[];
  lines?: number;
}

export interface RepositoryAnalysis {
  root_files?: string[];
  languages?: Record<string, number>;
  frameworks?: string[];
  package_managers?: string[];
  test_dirs?: string[];
  test_files?: string[];
  docs?: string[];
  entrypoints?: string[];
  modules?: ModuleInfo[];
  import_graph?: Record<string, string[]>;
  verification_profile?: string[][] | string[];
  lint_profile?: string[][] | string[];
  file_count?: number;
  total_lines?: number;
  conventions?: string[];
}

export interface RepositoryMemory {
  architecture?: {
    summary?: string;
    key_modules?: string[];
    entrypoints?: string[];
    docs?: string[];
    risks?: string[];
  };
  conventions?: { items?: string[] };
  dependencies?: {
    frameworks?: string[];
    package_managers?: string[];
    import_graph?: Record<string, string[]>;
  };
  test_structure?: {
    test_dirs?: string[];
    test_files?: string[];
    verification_profile?: unknown;
    lint_profile?: unknown;
  };
  [key: string]: unknown;
}

export interface HistoryRecord {
  kind: string;
  title: string;
  content: string;
  execution_id: string | null;
  created_at: string;
}

export interface RepositoryDetail extends Repository {
  analysis: RepositoryAnalysis | null;
  memory: RepositoryMemory | null;
  history: HistoryRecord[];
}

export interface RepositoryTree {
  files: string[];
  source: string;
}

export interface RepositoryFile {
  path: string;
  content: string;
}

export interface ListWithNote<T = Record<string, unknown>> {
  items: T[];
  note?: string | null;
}

export interface AuditEntry {
  actor: string;
  action: string;
  target: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface GitHubIssue {
  number: number;
  title: string;
  state: string;
  user: string;
  url: string;
  labels?: string[];
  updated_at: string;
}

export interface GitHubPull {
  number: number;
  title: string;
  state: string;
  user: string;
  url: string;
  draft?: boolean | null;
  head?: string;
  updated_at: string;
}

export interface GitHubBranch {
  name: string;
  sha: string;
  protected?: boolean | null;
}
