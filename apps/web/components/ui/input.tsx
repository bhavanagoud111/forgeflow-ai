import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-8 w-full rounded-md border border-input bg-background px-2.5 text-sm placeholder:text-muted-foreground disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
