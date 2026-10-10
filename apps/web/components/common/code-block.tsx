import { cn } from "@/lib/utils";

/** Scrollable monospace block for command output, JSON and file content. */
export function CodeBlock({
  children,
  className,
  maxHeight = "24rem",
}: {
  children: React.ReactNode;
  className?: string;
  maxHeight?: string;
}) {
  return (
    <pre
      className={cn(
        "overflow-auto rounded-md border border-border bg-muted/50 p-3 font-mono text-xs leading-relaxed whitespace-pre",
        className,
      )}
      style={{ maxHeight }}
    >
      {children}
    </pre>
  );
}

export function KeyValue({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-right font-medium">{children}</dd>
    </div>
  );
}

export function Mono({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("font-mono text-xs", className)}>{children}</span>;
}
