import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-none [&_svg]:size-3",
  {
    variants: {
      variant: {
        neutral: "border-border bg-muted text-muted-foreground",
        accent: "border-accent/30 bg-accent-soft text-accent",
        success: "border-success/30 bg-success-soft text-success",
        danger: "border-danger/30 bg-danger-soft text-danger",
        warning: "border-warning/30 bg-warning-soft text-warning",
        info: "border-info/30 bg-info-soft text-info",
        outline: "border-border text-foreground",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
