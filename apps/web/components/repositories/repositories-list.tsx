"use client";

import { FolderGit2, HardDrive, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, Skeleton } from "@/components/common/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatRelative } from "@/lib/format";
import { useRepositories } from "@/lib/queries";
import { ConnectRepositoryDialog } from "./connect-dialog";

export function RepositoriesList() {
  const repos = useRepositories();
  const [open, setOpen] = useState(false);

  return (
    <>
      <PageHeader
        title="Repositories"
        description="Codebases agents can analyze and change."
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus />
            Connect repository
          </Button>
        }
      />
      {repos.isError ? (
        <ErrorState error={repos.error} />
      ) : repos.isPending ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : repos.data.items.length === 0 ? (
        <EmptyState title="No repositories connected" description="Connect a GitHub repository or a local path." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {repos.data.items.map((r) => (
            <Link key={r.id} href={`/repositories/${r.id}`} className="block">
              <Card className="h-full p-4 transition-colors hover:border-muted-foreground/40">
                <div className="flex items-center gap-2">
                  {r.provider === "github" ? (
                    <FolderGit2 className="size-4 text-muted-foreground" aria-hidden="true" />
                  ) : (
                    <HardDrive className="size-4 text-muted-foreground" aria-hidden="true" />
                  )}
                  <span className="truncate font-medium">{r.full_name}</span>
                  <Badge variant="neutral" className="ml-auto">
                    {r.provider}
                  </Badge>
                </div>
                {r.description && <p className="mt-1 text-xs text-muted-foreground">{r.description}</p>}
                <p className="mt-3 line-clamp-3 text-xs text-muted-foreground">
                  {r.summary?.architecture ?? "Not analyzed yet."}
                </p>
                <p className="mt-3 text-[11px] text-muted-foreground">
                  {r.default_branch && <span className="font-mono">{r.default_branch}</span>}
                  {" · "}
                  {r.analyzed_at ? `analyzed ${formatRelative(r.analyzed_at)}` : "never analyzed"}
                </p>
              </Card>
            </Link>
          ))}
        </div>
      )}
      <ConnectRepositoryDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
