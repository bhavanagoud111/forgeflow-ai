import { FlaskConical } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/** Shown wherever output comes from the deterministic offline demo provider. */
export function SimulatedBadge({ className }: { className?: string }) {
  return (
    <Badge
      variant="warning"
      className={cn("font-normal", className)}
      title="The demo LLM provider is deterministic and offline; model output is scripted."
    >
      <FlaskConical />
      Simulated model output (demo provider)
    </Badge>
  );
}
