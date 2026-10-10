"use client";

import {
  Bot,
  FolderGit2,
  LayoutDashboard,
  Menu,
  Settings,
  ShieldCheck,
  Workflow,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { SimulatedBadge } from "@/components/common/simulated-badge";
import { Button } from "@/components/ui/button";
import { useHealth, useMe, useMetrics } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { Logo } from "./logo";
import { ThemeToggle } from "./theme-toggle";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/executions", label: "Executions", icon: Workflow },
  { href: "/repositories", label: "Repositories", icon: FolderGit2 },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const metrics = useMetrics();
  const health = useHealth();
  const me = useMe();
  const pending = metrics.data?.pending_approvals ?? 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center px-4">
        <Link href="/" onClick={onNavigate} aria-label="ForgeFlow AI home">
          <Logo />
        </Link>
      </div>
      <nav className="flex-1 space-y-0.5 px-2 py-2" aria-label="Main">
        {NAV.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors",
                active
                  ? "bg-muted font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
              )}
            >
              <Icon className={cn("size-4", active && "text-accent")} />
              <span className="flex-1">{item.label}</span>
              {item.href === "/approvals" && pending > 0 && (
                <span className="rounded bg-warning-soft px-1.5 text-[11px] font-medium text-warning tabular-nums">
                  {pending}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="space-y-2 border-t border-border p-3 text-xs">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "size-2 rounded-full",
              health.isError ? "bg-danger" : health.data?.status === "ok" ? "bg-success" : "bg-muted-foreground",
            )}
            aria-hidden="true"
          />
          <span className="text-muted-foreground">
            {health.isError
              ? "API unreachable"
              : health.data
                ? `API ${health.data.status} · v${health.data.version}`
                : "Checking API…"}
          </span>
        </div>
        {health.data?.simulated_llm && <SimulatedBadge />}
        <div className="flex items-center justify-between">
          <span className="truncate text-muted-foreground">
            {me.data ? `${me.data.name} · ${me.data.role}` : " "}
          </span>
          <ThemeToggle />
        </div>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 border-r border-border bg-card/40 md:block">
        <Sidebar />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-border bg-card">
            <Button
              variant="ghost"
              size="icon"
              className="absolute top-3 right-2"
              onClick={() => setOpen(false)}
              aria-label="Close navigation"
            >
              <X />
            </Button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-12 items-center gap-2 border-b border-border bg-background/90 px-3 backdrop-blur md:hidden">
          <Button variant="ghost" size="icon" onClick={() => setOpen(true)} aria-label="Open navigation">
            <Menu />
          </Button>
          <Logo />
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}
