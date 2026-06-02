import { useState, type ComponentType } from "react";
import {
  ChevronLeft,
  Clock,
  Coins,
  Cpu,
  FileCog,
  FileText,
  LayoutDashboard,
  type LucideProps,
  MessagesSquare,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Plug,
  ScrollText,
  Sun,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ChannelsPanel,
  ConfigPanel,
  CronPanel,
  LogsPanel,
  MemoryPanel,
  ModelsPanel,
  OverviewPanel,
  SessionsPanel,
  UsagePanel,
} from "./panels";

interface NavItem {
  key: string;
  label: string;
  icon: ComponentType<LucideProps>;
  component: ComponentType;
}

const NAV: NavItem[] = [
  { key: "overview", label: "Overview", icon: LayoutDashboard, component: OverviewPanel },
  { key: "usage", label: "Usage & cost", icon: Coins, component: UsagePanel },
  { key: "sessions", label: "Sessions", icon: MessagesSquare, component: SessionsPanel },
  { key: "models", label: "Models", icon: Cpu, component: ModelsPanel },
  { key: "channels", label: "Channels", icon: Plug, component: ChannelsPanel },
  { key: "cron", label: "Cron", icon: Clock, component: CronPanel },
  { key: "memory", label: "Memory", icon: FileText, component: MemoryPanel },
  { key: "logs", label: "Logs", icon: ScrollText, component: LogsPanel },
  { key: "config", label: "Config", icon: FileCog, component: ConfigPanel },
];

const NAV_STORAGE_KEY = "nanobot-webui.dashboard.nav";

function readNavOpen(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(NAV_STORAGE_KEY) !== "0";
  } catch {
    return true;
  }
}

export interface DashboardViewProps {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onBackToChat: () => void;
}

export function DashboardView({ theme, onToggleTheme, onBackToChat }: DashboardViewProps) {
  const [activeKey, setActiveKey] = useState<string>("overview");
  const [navOpen, setNavOpen] = useState<boolean>(readNavOpen);

  const active = NAV.find((n) => n.key === activeKey) ?? NAV[0];
  const ActivePanel = active.component;

  const toggleNav = () => {
    setNavOpen((v) => {
      const next = !v;
      try {
        window.localStorage.setItem(NAV_STORAGE_KEY, next ? "1" : "0");
      } catch {
        // ignore
      }
      return next;
    });
  };

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-background">
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-sidebar-border/60 bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out",
          navOpen ? "w-[210px]" : "w-[60px]",
        )}
      >
        <div className={cn("flex items-center gap-2 px-3 py-3", navOpen ? "justify-between" : "justify-center")}>
          {navOpen ? (
            <span className="inline-flex items-center gap-2 text-[13px] font-semibold tracking-tight">
              <LayoutDashboard className="h-4 w-4" /> Dashboard
            </span>
          ) : null}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 rounded-lg text-muted-foreground/85 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground"
            onClick={toggleNav}
            aria-label={navOpen ? "Collapse nav" : "Expand nav"}
          >
            {navOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </Button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-1" aria-label="Dashboard sections">
          {NAV.map((item) => {
            const Icon = item.icon;
            const isActive = item.key === active.key;
            return (
              <button
                key={item.key}
                type="button"
                aria-current={isActive ? "page" : undefined}
                title={item.label}
                onClick={() => setActiveKey(item.key)}
                className={cn(
                  "flex h-9 w-full items-center gap-2.5 rounded-[10px] px-2.5 text-left text-[12.5px] font-medium transition-colors",
                  navOpen ? "justify-start" : "justify-center",
                  isActive
                    ? "bg-sidebar-accent/85 text-sidebar-foreground"
                    : "text-sidebar-foreground/75 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                {navOpen ? <span className="truncate">{item.label}</span> : null}
              </button>
            );
          })}
        </nav>

        <div className="border-t border-sidebar-border/50 px-2 py-2">
          <button
            type="button"
            onClick={onBackToChat}
            className={cn(
              "flex h-9 w-full items-center gap-2.5 rounded-[10px] px-2.5 text-[12.5px] font-medium text-sidebar-foreground/75 transition-colors hover:bg-sidebar-accent/55 hover:text-sidebar-foreground",
              navOpen ? "justify-start" : "justify-center",
            )}
            title="Back to chat"
          >
            <ChevronLeft className="h-4 w-4 shrink-0" aria-hidden />
            {navOpen ? <span>Back to chat</span> : null}
          </button>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border/60 bg-background/80 px-5 backdrop-blur-sm">
          <h1 className="text-[16px] font-semibold tracking-tight text-foreground">{active.label}</h1>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
            onClick={onToggleTheme}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto [scrollbar-gutter:stable]">
          <div className="mx-auto w-full max-w-[1100px] px-5 py-6">
            <ActivePanel />
          </div>
        </div>
      </main>
    </div>
  );
}
