import * as React from "react";
import { cn } from "@/lib/utils";

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "flex min-h-20 w-full rounded-md border border-input bg-background px-2.5 py-2 text-sm placeholder:text-muted-foreground disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
