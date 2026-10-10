"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConnectRepository } from "@/lib/queries";

export function ConnectRepositoryDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const connect = useConnectRepository();
  const [provider, setProvider] = useState<"github" | "local">("github");
  const [value, setValue] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const v = value.trim();
    if (!v) return;
    connect.mutate(provider === "github" ? { provider, full_name: v } : { provider, path: v }, {
      onSuccess: (repo) => router.push(`/repositories/${repo.id}`),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect repository</DialogTitle>
          <DialogDescription>
            GitHub repositories need a configured token or GitHub App. Local paths must be under an allowed root on the
            API server.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="flex gap-1" role="radiogroup" aria-label="Provider">
            {(["github", "local"] as const).map((p) => (
              <Button
                key={p}
                type="button"
                size="sm"
                role="radio"
                aria-checked={provider === p}
                variant={provider === p ? "secondary" : "ghost"}
                onClick={() => setProvider(p)}
              >
                {p === "github" ? "GitHub" : "Local path"}
              </Button>
            ))}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="repo-value">{provider === "github" ? "Repository (owner/name or URL)" : "Path"}</Label>
            <Input
              id="repo-value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={provider === "github" ? "octo-org/service-api" : "taskboard-api"}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          {connect.isError && <ErrorState error={connect.error} />}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!value.trim() || connect.isPending}>
              {connect.isPending ? "Connecting…" : "Connect"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
