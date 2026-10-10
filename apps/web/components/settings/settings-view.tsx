"use client";

import { PageHeader } from "@/components/common/page-header";
import { SimulatedBadge } from "@/components/common/simulated-badge";
import { ErrorState, Skeleton } from "@/components/common/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDuration, formatNumber } from "@/lib/format";
import { useHealth, useSettings } from "@/lib/queries";

type Row = { label: string; value: React.ReactNode; env?: string };

function Bool({ value, yes = "Yes", no = "No" }: { value: boolean; yes?: string; no?: string }) {
  return <Badge variant={value ? "success" : "neutral"}>{value ? yes : no}</Badge>;
}

function SettingsCard({ title, description, rows }: { title: string; description?: string; rows: Row[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <dl className="divide-y divide-border">
          {rows.map((r) => (
            <div key={r.label} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-0.5 py-2">
              <dt className="text-sm">{r.label}</dt>
              <dd className="text-right text-sm font-medium tabular-nums">{r.value}</dd>
              {r.env && <p className="col-span-2 font-mono text-[11px] text-muted-foreground">{r.env}</p>}
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

const seconds = (s: number) => formatDuration(s * 1000);

export function SettingsView() {
  const settings = useSettings();
  const health = useHealth();
  const s = settings.data;
  const h = health.data;

  return (
    <>
      <PageHeader
        title="Settings"
        description="Read-only view of the API configuration. Change values with environment variables on the API server and restart it."
      />
      {settings.isError && <ErrorState error={settings.error} className="mb-4" />}
      {health.isError && <ErrorState error={health.error} className="mb-4" />}

      <div className="grid gap-4 lg:grid-cols-2">
        {h ? (
          <SettingsCard
            title="Health"
            description="Live status from /api/health."
            rows={[
              { label: "Status", value: <Badge variant={h.status === "ok" ? "success" : "danger"}>{h.status}</Badge> },
              { label: "API version", value: <span className="font-mono">{h.version}</span> },
              { label: "Database", value: <Bool value={h.database} yes="Connected" no="Unavailable" /> },
              { label: "Model provider", value: <span className="font-mono">{h.llm_provider}</span> },
              { label: "Simulated model", value: h.simulated_llm ? <SimulatedBadge /> : <Bool value={false} /> },
              { label: "Sandbox", value: <span className="font-mono">{h.sandbox}</span> },
              { label: "GitHub", value: <Bool value={h.github} yes="Configured" no="Not configured" /> },
              { label: "Slack", value: <Bool value={h.slack} yes="Configured" no="Not configured" /> },
            ]}
          />
        ) : (
          !health.isError && <Skeleton className="h-80" />
        )}

        {s ? (
          <>
            <SettingsCard
              title="Model provider"
              rows={[
                { label: "Provider", value: <span className="font-mono">{s.llm.provider}</span>, env: "FORGEFLOW_LLM_PROVIDER (demo | anthropic | openai | ollama)" },
                { label: "Model", value: <span className="font-mono">{s.llm.model}</span>, env: "FORGEFLOW_LLM_MODEL" },
                { label: "API key", value: <Bool value={s.llm.api_key_configured} yes="Configured" no="Not set" />, env: "FORGEFLOW_LLM_API_KEY" },
                { label: "Simulated output", value: s.llm.simulated ? <SimulatedBadge /> : <Bool value={false} />, env: "Set a real provider to disable the demo provider" },
              ]}
            />
            <SettingsCard
              title="GitHub"
              rows={[
                { label: "Status", value: <Bool value={s.github.configured} yes="Configured" no="Not configured" />, env: "FORGEFLOW_GITHUB_TOKEN, or FORGEFLOW_GITHUB_APP_ID + FORGEFLOW_GITHUB_APP_PRIVATE_KEY + FORGEFLOW_GITHUB_APP_INSTALLATION_ID" },
                { label: "Authentication", value: s.github.auth ?? "—" },
                { label: "API URL", value: <span className="font-mono text-xs">{s.github.api_url}</span>, env: "FORGEFLOW_GITHUB_API_URL" },
              ]}
            />
            <SettingsCard
              title="Slack"
              rows={[
                { label: "Status", value: <Bool value={s.slack.configured} yes="Configured" no="Not configured" />, env: "FORGEFLOW_SLACK_SIGNING_SECRET" },
                { label: "Bot token", value: <Bool value={s.slack.bot_token_configured} yes="Configured" no="Not set" />, env: "FORGEFLOW_SLACK_BOT_TOKEN" },
                { label: "Authorized users", value: formatNumber(s.slack.authorized_users), env: "FORGEFLOW_SLACK_USER_ROLES (JSON map of user id to role)" },
              ]}
            />
            <SettingsCard
              title="Limits"
              rows={[
                { label: "Execution timeout", value: seconds(s.limits.execution_timeout_seconds), env: "FORGEFLOW_EXECUTION_TIMEOUT_SECONDS" },
                { label: "Node timeout", value: seconds(s.limits.node_timeout_seconds), env: "FORGEFLOW_NODE_TIMEOUT_SECONDS" },
                { label: "Max debug attempts", value: s.limits.max_debug_attempts, env: "FORGEFLOW_MAX_DEBUG_ATTEMPTS" },
                { label: "Max parallel tasks", value: s.limits.max_parallel_tasks, env: "FORGEFLOW_MAX_PARALLEL_TASKS" },
                { label: "Max files per patch", value: s.limits.max_patch_files, env: "FORGEFLOW_MAX_PATCH_FILES" },
                { label: "Rate limit", value: `${s.limits.rate_limit_per_minute}/min`, env: "FORGEFLOW_RATE_LIMIT_PER_MINUTE" },
              ]}
            />
            <SettingsCard
              title="Sandbox"
              description="Where tests and verification commands run."
              rows={[
                { label: "Mode", value: <span className="font-mono">{s.sandbox.mode}</span>, env: "FORGEFLOW_SANDBOX_MODE (docker | runner | local)" },
                { label: "Image", value: <span className="font-mono text-xs">{s.sandbox.image}</span>, env: "FORGEFLOW_SANDBOX_IMAGE" },
                { label: "CPUs", value: s.sandbox.cpus, env: "FORGEFLOW_SANDBOX_CPUS" },
                { label: "Memory", value: `${formatNumber(s.sandbox.memory_mb)} MB`, env: "FORGEFLOW_SANDBOX_MEMORY_MB" },
                { label: "Process limit", value: s.sandbox.pids_limit, env: "FORGEFLOW_SANDBOX_PIDS_LIMIT" },
                { label: "Command timeout", value: seconds(s.sandbox.command_timeout_seconds), env: "FORGEFLOW_SANDBOX_COMMAND_TIMEOUT_SECONDS" },
                { label: "Dependency install", value: <Bool value={s.sandbox.allow_dependency_install} yes="Allowed" no="Blocked" />, env: "FORGEFLOW_ALLOW_DEPENDENCY_INSTALL" },
                { label: "Unsafe local sandbox", value: <Bool value={s.sandbox.allow_unsafe_local_sandbox} yes="Allowed" no="Not allowed" />, env: "FORGEFLOW_ALLOW_UNSAFE_LOCAL_SANDBOX" },
              ]}
            />
            <SettingsCard
              title="Retention and observability"
              rows={[
                { label: "Workspaces", value: `${s.retention.workspace_hours} h`, env: "FORGEFLOW_WORKSPACE_RETENTION_HOURS" },
                { label: "Events", value: `${s.retention.event_days} days`, env: "FORGEFLOW_EVENT_RETENTION_DAYS" },
                { label: "History", value: `${s.retention.history_days} days`, env: "FORGEFLOW_HISTORY_RETENTION_DAYS" },
                { label: "OTLP exporter", value: <Bool value={s.observability.otlp_endpoint_configured} yes="Configured" no="Not configured" />, env: "FORGEFLOW_OTEL_EXPORTER_OTLP_ENDPOINT" },
              ]}
            />
            <SettingsCard
              title="Web console"
              description="Configured on the Next.js server, never sent to the browser."
              rows={[
                { label: "API base URL", value: "server-side", env: "FORGEFLOW_API_URL" },
                { label: "API token", value: "server-side", env: "FORGEFLOW_API_TOKEN" },
              ]}
            />
          </>
        ) : (
          !settings.isError && <Skeleton className="h-80" />
        )}
      </div>
    </>
  );
}
