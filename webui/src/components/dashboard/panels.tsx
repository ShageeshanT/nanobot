import { useMemo, useState } from "react";
import {
  Activity,
  Boxes,
  ChevronDown,
  ChevronRight,
  Clock,
  Coins,
  Copy,
  Cpu,
  MessagesSquare,
  Plug,
  Puzzle,
  RefreshCw,
  Trash2,
  Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  deleteSession,
  fetchCronJobs,
  fetchDashboardChannels,
  fetchDashboardConfig,
  fetchDashboardOverview,
  fetchIntegrations,
  fetchLogs,
  fetchMemoryFiles,
  fetchPresets,
  fetchSettings,
  fetchUsage,
  listSessions,
  updateSettings,
} from "@/lib/api";
import type { CronJobInfo, McpServerInfo, SettingsPayload } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useClient } from "@/providers/ClientProvider";
import {
  AreaChart,
  Badge,
  EmptyState,
  Panel,
  ProportionBar,
  QueryState,
  StatCard,
  StatusDot,
  formatDateTime,
  formatNumber,
  formatRelative,
  formatUptime,
  formatUsd,
  useDashboard,
} from "./widgets";

function humanizeMs(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return "—";
  const s = Math.round(ms / 1000);
  if (s % 86400 === 0) return `${s / 86400}d`;
  if (s % 3600 === 0) return `${s / 3600}h`;
  if (s % 60 === 0) return `${s / 60}m`;
  return `${s}s`;
}

function scheduleSummary(s: CronJobInfo["schedule"]): string {
  if (s.kind === "cron") return `cron ${s.expr ?? ""}${s.tz ? ` (${s.tz})` : ""}`.trim();
  if (s.kind === "every") return `every ${humanizeMs(s.every_ms)}`;
  if (s.kind === "at") return `at ${formatDateTime(s.at_ms)}`;
  return s.kind;
}

function Row({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center gap-3 border-b border-border/40 px-1 py-2.5 last:border-0", className)}>
      {children}
    </div>
  );
}

// --- Overview ---------------------------------------------------------------

export function OverviewPanel() {
  const query = useDashboard((token) => fetchDashboardOverview(token), { intervalMs: 15000 });
  return (
    <QueryState query={query}>
      {(d) => {
        const totals = d.usage.totals ?? {};
        const points = d.usage.series.map((p) => ({ label: p.date.slice(5), value: p.total_tokens }));
        return (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <Cpu className="h-3.5 w-3.5" /> <span className="text-foreground">{d.model}</span>
                <span className="text-muted-foreground/70">· {d.provider}</span>
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" /> up {formatUptime(d.uptime_s)}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Activity className="h-3.5 w-3.5" /> {d.active_connections} live
              </span>
              <span className="ml-auto text-muted-foreground/70">v{d.version}</span>
            </div>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <StatCard label="Sessions" value={formatNumber(d.counts.sessions)} icon={MessagesSquare} sub={`${d.counts.webui_sessions} web`} />
              <StatCard label="Tokens (30d)" value={formatNumber(totals.total_tokens)} icon={Coins} sub={`${formatNumber(totals.turns)} turns`} />
              <StatCard label="Est. cost (30d)" value={formatUsd(totals.cost_usd)} icon={Coins} />
              <StatCard label="Channels" value={`${d.counts.channels_enabled}/${d.counts.channels_total}`} icon={Plug} sub="enabled" />
              <StatCard label="Providers" value={formatNumber(d.counts.providers_configured)} icon={Boxes} sub="with keys" />
              <StatCard label="Cron jobs" value={formatNumber(d.counts.cron_jobs)} icon={Clock} />
            </div>

            <Panel title="Token usage" description="Total tokens per day, last 30 days">
              <AreaChart points={points} />
            </Panel>

            <div className="grid gap-5 lg:grid-cols-2">
              <Panel title="Recent sessions">
                {d.recent_sessions.length === 0 ? (
                  <EmptyState>No web sessions yet.</EmptyState>
                ) : (
                  <div>
                    {d.recent_sessions.map((s) => (
                      <Row key={s.key}>
                        <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">
                          {s.title || s.preview || s.key.replace(/^websocket:/, "")}
                        </span>
                        <span className="shrink-0 text-[11px] text-muted-foreground">
                          {formatRelative(s.updated_at ? Date.parse(s.updated_at) : null)}
                        </span>
                      </Row>
                    ))}
                  </div>
                )}
              </Panel>
              <Panel title="Channels">
                {d.channels.length === 0 ? (
                  <EmptyState>No channels configured.</EmptyState>
                ) : (
                  <div>
                    {d.channels.map((c) => (
                      <Row key={c.name}>
                        <StatusDot ok={c.enabled} />
                        <span className="flex-1 truncate text-[13px] capitalize text-foreground">{c.name}</span>
                        <Badge tone={c.configured ? "ok" : "muted"}>{c.configured ? "configured" : "no creds"}</Badge>
                      </Row>
                    ))}
                  </div>
                )}
              </Panel>
            </div>
          </div>
        );
      }}
    </QueryState>
  );
}

// --- Usage ------------------------------------------------------------------

export function UsagePanel() {
  const [days, setDays] = useState(30);
  const query = useDashboard((token) => fetchUsage(token, days), { deps: [days], intervalMs: 30000 });
  return (
    <QueryState query={query}>
      {(d) => {
        const totals = d.totals ?? {};
        const points = d.series.map((p) => ({ label: p.date.slice(5), value: p.total_tokens }));
        const maxModel = Math.max(1, ...d.by_model.map((m) => m.total_tokens));
        return (
          <div className="space-y-5">
            <div className="flex items-center gap-2">
              {[7, 30, 90].map((n) => (
                <Button key={n} size="sm" variant={days === n ? "default" : "outline"} className="rounded-full" onClick={() => setDays(n)}>
                  {n}d
                </Button>
              ))}
              <Button size="sm" variant="ghost" className="ml-auto rounded-full" onClick={query.refresh}>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Refresh
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatCard label="Input tokens" value={formatNumber(totals.input_tokens)} />
              <StatCard label="Output tokens" value={formatNumber(totals.output_tokens)} />
              <StatCard label="Total tokens" value={formatNumber(totals.total_tokens)} />
              <StatCard label="Est. cost" value={formatUsd(totals.cost_usd)} sub={`${formatNumber(totals.turns)} turns`} />
            </div>
            <Panel title="Tokens per day"><AreaChart points={points} height={180} /></Panel>
            <Panel title="By model">
              {d.by_model.length === 0 ? (
                <EmptyState>No usage recorded yet. Token usage is tracked from now on.</EmptyState>
              ) : (
                <div className="space-y-3">
                  {d.by_model.map((m) => (
                    <div key={m.model} className="space-y-1.5">
                      <div className="flex items-center justify-between text-[13px]">
                        <span className="truncate text-foreground">{m.model}</span>
                        <span className="shrink-0 text-muted-foreground">
                          {formatNumber(m.total_tokens)} · {formatUsd(m.cost_usd)}
                        </span>
                      </div>
                      <ProportionBar value={m.total_tokens} max={maxModel} />
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>
        );
      }}
    </QueryState>
  );
}

// --- Sessions ---------------------------------------------------------------

export function SessionsPanel() {
  const { token } = useClient();
  const query = useDashboard((t) => listSessions(t));
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const onDelete = async (key: string) => {
    setBusy(key);
    try {
      await deleteSession(token, key);
      query.refresh();
    } catch {
      // ignore; refresh keeps state honest
    } finally {
      setBusy(null);
    }
  };

  return (
    <QueryState query={query}>
      {(sessions) => {
        const q = search.trim().toLowerCase();
        const rows = q
          ? sessions.filter((s) => `${s.title} ${s.preview} ${s.key}`.toLowerCase().includes(q))
          : sessions;
        return (
          <Panel
            title={`Sessions (${sessions.length})`}
            actions={
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search…" className="h-8 w-44 rounded-full text-[13px]" />
            }
          >
            {rows.length === 0 ? (
              <EmptyState>No sessions.</EmptyState>
            ) : (
              <div>
                {rows.map((s) => (
                  <Row key={s.key}>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] text-foreground">
                        {s.title || s.preview || s.chatId}
                      </div>
                      <div className="truncate text-[11px] text-muted-foreground">
                        {s.channel} · {formatRelative(s.updatedAt ? Date.parse(s.updatedAt) : null)}
                      </div>
                    </div>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 shrink-0 rounded-full text-muted-foreground hover:text-destructive"
                      disabled={busy === s.key}
                      onClick={() => onDelete(s.key)}
                      aria-label="Delete session"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </Row>
                ))}
              </div>
            )}
          </Panel>
        );
      }}
    </QueryState>
  );
}

// --- Models -----------------------------------------------------------------

export function ModelsPanel() {
  const { token } = useClient();
  const settings = useDashboard((t) => fetchSettings(t));
  const presets = useDashboard((t) => fetchPresets(t));
  const [draft, setDraft] = useState<{ model: string; provider: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const apply = async (model: string, provider: string) => {
    setSaving(true);
    try {
      await updateSettings(token, { model, ...(provider && provider !== "auto" ? { provider } : {}) });
      settings.refresh();
      setDraft(null);
    } catch {
      // settings.refresh keeps UI honest
    } finally {
      setSaving(false);
    }
  };

  return (
    <QueryState query={settings}>
      {(s: SettingsPayload) => {
        const form = draft ?? { model: s.agent.model, provider: s.agent.provider || "auto" };
        const configured = s.providers.filter((p) => p.configured);
        return (
          <div className="space-y-5">
            <Panel title="Active model" description="Hot-reloaded on the next turn — no restart needed.">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <label className="flex-1 space-y-1">
                  <span className="text-[12px] font-medium text-muted-foreground">Model</span>
                  <Input
                    value={form.model}
                    onChange={(e) => setDraft({ ...form, model: e.target.value })}
                    className="h-9 rounded-full text-[13px]"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-[12px] font-medium text-muted-foreground">Provider</span>
                  <select
                    value={form.provider}
                    onChange={(e) => setDraft({ ...form, provider: e.target.value })}
                    className="h-9 w-full rounded-full border border-input bg-background px-3 text-[13px] sm:w-48"
                  >
                    <option value="auto">auto</option>
                    {configured.map((p) => (
                      <option key={p.name} value={p.name}>{p.label}</option>
                    ))}
                  </select>
                </label>
                <Button
                  className="h-9 rounded-full"
                  disabled={saving || (form.model === s.agent.model && form.provider === (s.agent.provider || "auto"))}
                  onClick={() => apply(form.model, form.provider)}
                >
                  {saving ? "Applying…" : "Apply"}
                </Button>
              </div>
            </Panel>

            <QueryState query={presets}>
              {(p) =>
                p.presets.length === 0 ? (
                  <Panel title="Presets"><EmptyState>No model presets defined in config.</EmptyState></Panel>
                ) : (
                  <Panel title="Presets">
                    <div>
                      {p.presets.map((preset) => (
                        <Row key={preset.name}>
                          <div className="min-w-0 flex-1">
                            <div className="text-[13px] text-foreground">
                              {preset.name} {p.active === preset.name ? <Badge tone="ok">active</Badge> : null}
                            </div>
                            <div className="truncate text-[11px] text-muted-foreground">{preset.model} · {preset.provider}</div>
                          </div>
                          <Button size="sm" variant="outline" className="h-7 rounded-full" disabled={saving} onClick={() => apply(preset.model, preset.provider)}>
                            Use
                          </Button>
                        </Row>
                      ))}
                    </div>
                  </Panel>
                )
              }
            </QueryState>

            <Panel title="Providers" description="Configure API keys in Settings.">
              <div>
                {s.providers.map((p) => (
                  <Row key={p.name}>
                    <StatusDot ok={p.configured} />
                    <span className="flex-1 truncate text-[13px] text-foreground">{p.label}</span>
                    <Badge tone={p.configured ? "ok" : "muted"}>{p.configured ? "configured" : "not set"}</Badge>
                  </Row>
                ))}
              </div>
            </Panel>
          </div>
        );
      }}
    </QueryState>
  );
}

// --- Channels ---------------------------------------------------------------

export function ChannelsPanel() {
  const query = useDashboard((t) => fetchDashboardChannels(t), { intervalMs: 20000 });
  return (
    <QueryState query={query}>
      {(d) => (
        <Panel title={`Channels (${d.enabled_count} enabled)`}>
          {d.channels.length === 0 ? (
            <EmptyState>No channels configured. Add them in config.json.</EmptyState>
          ) : (
            <div>
              {d.channels.map((c) => (
                <Row key={c.name}>
                  <StatusDot ok={c.enabled} />
                  <span className="flex-1 truncate text-[13px] capitalize text-foreground">{c.name}</span>
                  {c.type ? <span className="text-[11px] text-muted-foreground">{c.type}</span> : null}
                  <Badge tone={c.enabled ? "ok" : "muted"}>{c.enabled ? "enabled" : "disabled"}</Badge>
                  <Badge tone={c.configured ? "ok" : "warn"}>{c.configured ? "creds" : "no creds"}</Badge>
                </Row>
              ))}
            </div>
          )}
        </Panel>
      )}
    </QueryState>
  );
}

// --- Integrations (MCP servers + capabilities) ------------------------------

const COMPOSIO_SNIPPET = `{
  "tools": {
    "mcpServers": {
      "composio": {
        "url": "https://backend.composio.dev/v3/mcp/<SERVER_ID>?user_id=<USER_ID>",
        "headers": { "x-api-key": "<COMPOSIO_API_KEY>" }
      }
    }
  }
}`;

function mcpTone(status: string): "ok" | "warn" | "error" | "muted" {
  if (status === "connected") return "ok";
  if (status === "connecting") return "warn";
  if (status === "error") return "error";
  return "muted";
}

function McpServerCard({ s }: { s: McpServerInfo }) {
  const [open, setOpen] = useState(false);
  const hasAllowlist = s.enabled_tools.length > 0 && !s.enabled_tools.includes("*");
  return (
    <div className="rounded-xl border border-border/60 bg-card/60 p-3.5">
      <div className="flex items-start gap-3">
        <StatusDot ok={s.status === "connected"} className="mt-1.5" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-[14px] font-medium text-foreground">{s.name}</span>
            <Badge tone="muted">{s.transport}</Badge>
            <Badge tone={mcpTone(s.status)}>{s.status}</Badge>
          </div>
          {s.target ? <div className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{s.target}</div> : null}
          {s.error ? <div className="mt-1 text-[11px] text-destructive">{s.error}</div> : null}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
            {s.tool_count > 0 ? <span>{s.tool_count} tools</span> : null}
            {s.header_count > 0 ? <span>· {s.header_count} headers</span> : null}
            {hasAllowlist ? <span>· allowlist: {s.enabled_tools.join(", ")}</span> : null}
          </div>
        </div>
        {s.tools.length > 0 ? (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 shrink-0 gap-1 rounded-full text-[12px]"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />} tools
          </Button>
        ) : null}
      </div>
      {open && s.tools.length > 0 ? (
        <div className="mt-3 max-h-64 space-y-1 overflow-y-auto border-t border-border/40 pt-3">
          {s.tools.map((tool) => (
            <div key={tool.name} className="flex items-start gap-2 text-[12px]">
              <Wrench className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground/60" aria-hidden />
              <span className="font-mono text-foreground">{tool.name}</span>
              {tool.description ? <span className="truncate text-muted-foreground">— {tool.description}</span> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function IntegrationsPanel() {
  const query = useDashboard((t) => fetchIntegrations(t), { intervalMs: 20000 });
  const [copied, setCopied] = useState(false);
  const copySnippet = () => {
    void navigator.clipboard?.writeText(COMPOSIO_SNIPPET).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <QueryState query={query}>
      {(d) => (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatCard label="MCP servers" value={`${d.mcp_connected}/${d.mcp_total}`} icon={Puzzle} sub="connected" />
            <StatCard label="MCP tools" value={formatNumber(d.mcp_servers.reduce((n, s) => n + s.tool_count, 0))} icon={Wrench} />
            <StatCard label="Capabilities" value={formatNumber(d.capabilities.filter((c) => c.enabled).length)} icon={Boxes} sub={`of ${d.capabilities.length}`} />
          </div>

          <Panel title="MCP servers" description="nanobot's native toolkit — connect any MCP server (Composio, GitHub, custom…).">
            {d.mcp_servers.length === 0 ? (
              <EmptyState>No MCP servers configured. Add one under tools.mcpServers in config — see below.</EmptyState>
            ) : (
              <div className="space-y-2.5">
                {d.mcp_servers.map((s) => (
                  <McpServerCard key={s.name} s={s} />
                ))}
              </div>
            )}
          </Panel>

          <Panel
            title="Add an integration (Composio & more)"
            description="Composio exposes 500+ apps as an MCP server — add it (or any MCP server) here."
            actions={
              <Button size="sm" variant="outline" className="h-8 rounded-full" onClick={copySnippet}>
                <Copy className="mr-1.5 h-3.5 w-3.5" /> {copied ? "Copied" : "Copy"}
              </Button>
            }
          >
            <pre className="overflow-auto rounded-xl border border-border/50 bg-muted/30 p-4 text-[12px] leading-relaxed text-foreground">
              {COMPOSIO_SNIPPET}
            </pre>
            <p className="mt-2 text-[12px] text-muted-foreground">
              Create a server at composio.dev, paste the URL + API key into config, then restart. It appears above with its live tools.
            </p>
          </Panel>

          <Panel title="Built-in capabilities">
            <div>
              {d.capabilities.map((c) => (
                <Row key={c.name}>
                  <StatusDot ok={c.enabled} />
                  <span className="flex-1 truncate text-[13px] text-foreground">{c.name}</span>
                  {c.detail ? <span className="text-[11px] text-muted-foreground">{c.detail}</span> : null}
                  <Badge tone={c.enabled ? "ok" : "muted"}>{c.enabled ? "on" : "off"}</Badge>
                </Row>
              ))}
            </div>
          </Panel>
        </div>
      )}
    </QueryState>
  );
}

// --- Cron -------------------------------------------------------------------

export function CronPanel() {
  const query = useDashboard((t) => fetchCronJobs(t), { intervalMs: 20000 });
  return (
    <QueryState query={query}>
      {(d) => (
        <Panel title={`Scheduled jobs (${d.jobs.length})`} description="Managed by the agent's cron tool.">
          {d.jobs.length === 0 ? (
            <EmptyState>No cron jobs.</EmptyState>
          ) : (
            <div>
              {d.jobs.map((j) => (
                <Row key={j.id}>
                  <StatusDot ok={j.enabled} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] text-foreground">{j.name || j.id}</div>
                    <div className="truncate text-[11px] text-muted-foreground">{scheduleSummary(j.schedule)}</div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-[11px] text-muted-foreground">next {formatRelative(j.next_run_at_ms)}</div>
                    {j.last_status ? (
                      <Badge tone={j.last_status === "ok" ? "ok" : j.last_status === "error" ? "error" : "muted"}>{j.last_status}</Badge>
                    ) : null}
                  </div>
                </Row>
              ))}
            </div>
          )}
        </Panel>
      )}
    </QueryState>
  );
}

// --- Memory -----------------------------------------------------------------

export function MemoryPanel() {
  const query = useDashboard((t) => fetchMemoryFiles(t));
  const [active, setActive] = useState<string | null>(null);
  return (
    <QueryState query={query}>
      {(d) => {
        const current = d.files.find((f) => f.name === active) ?? d.files.find((f) => f.exists) ?? d.files[0];
        return (
          <Panel title="Workspace files" description="Read-only. Edit via chat or the workspace.">
            <div className="mb-3 flex flex-wrap gap-1.5">
              {d.files.map((f) => (
                <Button
                  key={f.name}
                  size="sm"
                  variant={current?.name === f.name ? "default" : "outline"}
                  className={cn("h-7 rounded-full text-[12px]", !f.exists && "opacity-50")}
                  onClick={() => setActive(f.name)}
                >
                  {f.name}
                </Button>
              ))}
            </div>
            {current && current.exists ? (
              <pre className="max-h-[60vh] overflow-auto rounded-xl border border-border/50 bg-muted/30 p-4 text-[12.5px] leading-relaxed text-foreground whitespace-pre-wrap break-words">
                {current.content || "(empty)"}
              </pre>
            ) : (
              <EmptyState>{current ? `${current.name} does not exist yet.` : "No files."}</EmptyState>
            )}
          </Panel>
        );
      }}
    </QueryState>
  );
}

// --- Logs -------------------------------------------------------------------

const LOG_LEVELS = ["", "INFO", "WARNING", "ERROR"] as const;
const LEVEL_TONE: Record<string, string> = {
  ERROR: "text-destructive",
  WARNING: "text-amber-600 dark:text-amber-400",
  INFO: "text-foreground",
  DEBUG: "text-muted-foreground",
};

export function LogsPanel() {
  const [level, setLevel] = useState("");
  const [auto, setAuto] = useState(true);
  const query = useDashboard((t) => fetchLogs(t, 400, level || undefined), {
    deps: [level],
    intervalMs: auto ? 4000 : undefined,
  });
  return (
    <QueryState query={query}>
      {(d) => (
        <Panel
          title="Gateway logs"
          description={`${d.count} buffered`}
          actions={
            <>
              <select value={level} onChange={(e) => setLevel(e.target.value)} className="h-8 rounded-full border border-input bg-background px-3 text-[12px]">
                {LOG_LEVELS.map((l) => (
                  <option key={l} value={l}>{l || "all levels"}</option>
                ))}
              </select>
              <Button size="sm" variant={auto ? "default" : "outline"} className="h-8 rounded-full" onClick={() => setAuto((v) => !v)}>
                {auto ? "Live" : "Paused"}
              </Button>
              <Button size="icon" variant="ghost" className="h-8 w-8 rounded-full" onClick={query.refresh} aria-label="Refresh">
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </>
          }
        >
          {d.logs.length === 0 ? (
            <EmptyState>No log lines buffered yet.</EmptyState>
          ) : (
            <div className="max-h-[64vh] overflow-auto rounded-xl border border-border/50 bg-muted/20 p-2 font-mono text-[11.5px] leading-relaxed">
              {d.logs.map((l, i) => (
                <div key={`${l.ts}-${i}`} className="flex gap-2 px-1 py-0.5">
                  <span className="shrink-0 text-muted-foreground/70">{new Date(l.ts).toLocaleTimeString()}</span>
                  <span className={cn("shrink-0 font-semibold", LEVEL_TONE[l.level] ?? "text-muted-foreground")}>{l.level}</span>
                  <span className="min-w-0 whitespace-pre-wrap break-words text-foreground/90">{l.message}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}
    </QueryState>
  );
}

// --- Config -----------------------------------------------------------------

export function ConfigPanel() {
  const query = useDashboard((t) => fetchDashboardConfig(t));
  const pretty = useMemo(() => (query.data ? JSON.stringify(query.data.config, null, 2) : ""), [query.data]);
  return (
    <QueryState query={query}>
      {(d) => (
        <Panel title="Configuration" description={d.config_path}>
          <pre className="max-h-[68vh] overflow-auto rounded-xl border border-border/50 bg-muted/30 p-4 text-[12px] leading-relaxed text-foreground">
            {pretty}
          </pre>
        </Panel>
      )}
    </QueryState>
  );
}
