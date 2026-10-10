import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  description,
  className,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-border px-4 py-8 text-center",
        className,
      )}
    >
      <Inbox className="size-5 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-md text-xs text-muted-foreground">{description}</p>}
      {children}
    </div>
  );
}

export function ErrorState({ error, className }: { error: unknown; className?: string }) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2.5 text-sm text-danger",
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{errorMessage(error)}</span>
    </div>
  );
}

export function LoadingState({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 py-6 text-sm text-muted-foreground", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}
