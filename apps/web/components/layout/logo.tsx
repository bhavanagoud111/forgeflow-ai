import { cn } from "@/lib/utils";

/** ForgeFlow AI mark: an "F" drawn as a small flow graph. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" className={cn("size-7", className)}>
      <rect width="32" height="32" rx="7" className="fill-muted" />
      <path d="M11 23.5V10.5a2 2 0 0 1 2-2h7" stroke="var(--accent)" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M11 16h5.5" stroke="var(--accent)" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="22.5" cy="8.5" r="2.6" fill="var(--foreground)" />
      <circle cx="19" cy="16" r="2.6" fill="var(--foreground)" />
      <circle cx="11" cy="23.5" r="2.6" fill="var(--accent)" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <LogoMark />
      <span className="text-sm font-semibold tracking-tight">
        ForgeFlow <span className="text-muted-foreground">AI</span>
      </span>
    </span>
  );
}
