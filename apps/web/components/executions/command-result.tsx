import { CodeBlock } from "@/components/common/code-block";
import { Badge } from "@/components/ui/badge";
import { formatDuration } from "@/lib/format";
import type { CommandResult } from "@/lib/types";

export function CommandResultView({ command }: { command: CommandResult }) {
  const ok = command.exit_code === 0 && !command.timed_out;
  const output = [command.stdout, command.stderr].filter(Boolean).join(command.stdout && command.stderr ? "\n" : "");
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <code className="rounded bg-muted px-1.5 py-0.5 font-mono">$ {command.argv.join(" ")}</code>
        <Badge variant={ok ? "success" : "danger"}>
          {command.timed_out ? "timed out" : `exit ${command.exit_code ?? "?"}`}
        </Badge>
        {command.duration_ms !== undefined && (
          <span className="text-muted-foreground">{formatDuration(command.duration_ms)}</span>
        )}
        {command.sandbox && <span className="text-muted-foreground">{command.sandbox} sandbox</span>}
      </div>
      {output ? (
        <CodeBlock maxHeight="18rem">{output}</CodeBlock>
      ) : (
        <p className="text-xs text-muted-foreground">No output.</p>
      )}
    </div>
  );
}
