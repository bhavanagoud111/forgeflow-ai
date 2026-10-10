import {
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  Clock,
  Loader2,
  PauseCircle,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS: Record<string, { variant: BadgeVariant; icon: LucideIcon; spin?: boolean; label?: string }> = {
  queued: { variant: "neutral", icon: Clock },
  running: { variant: "accent", icon: Loader2, spin: true },
  resuming: { variant: "accent", icon: Loader2, spin: true },
  active: { variant: "accent", icon: Loader2, spin: true },
  awaiting_approval: { variant: "warning", icon: PauseCircle, label: "Awaiting approval" },
  pending: { variant: "warning", icon: PauseCircle },
  succeeded: { variant: "success", icon: CheckCircle2 },
  completed: { variant: "success", icon: CheckCircle2 },
  approved: { variant: "success", icon: CheckCircle2 },
  passed: { variant: "success", icon: CheckCircle2 },
  idle: { variant: "neutral", icon: CircleDashed },
  failed: { variant: "danger", icon: XCircle },
  error: { variant: "danger", icon: XCircle },
  rejected: { variant: "danger", icon: XCircle },
  blocked: { variant: "danger", icon: CircleSlash },
  cancelled: { variant: "neutral", icon: CircleSlash },
  expired: { variant: "neutral", icon: CircleSlash },
  skipped: { variant: "neutral", icon: CircleDashed },
};

export function statusVariant(status: string): BadgeVariant {
  return STATUS[status]?.variant ?? "neutral";
}

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const cfg = STATUS[status] ?? { variant: "neutral" as const, icon: CircleDashed };
  const Icon = cfg.icon;
  return (
    <Badge variant={cfg.variant} className={className}>
      <Icon className={cn(cfg.spin && "animate-spin")} />
      {cfg.label ?? humanize(status)}
    </Badge>
  );
}
