import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import { Loader2, type LucideProps } from "lucide-react";

import { cn } from "@/lib/utils";
import { useClient } from "@/providers/ClientProvider";

// --- data hook --------------------------------------------------------------

export interface DashboardQuery<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

/** Fetch dashboard data with the auth token, with manual + interval refresh. */
export function useDashboard<T>(
  fetcher: (token: string) => Promise<T>,
  opts?: { intervalMs?: number; deps?: unknown[] },
): DashboardQuery<T> {
  const { token } = useClient();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const aliveRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const result = await fetcherRef.current(token);
      if (aliveRef.current) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (aliveRef.current) setError((e as Error).message);
    } finally {
      if (aliveRef.current) setLoading(false);
    }
  }, [token]);

  const deps = opts?.deps ?? [];
  const intervalMs = opts?.intervalMs;
  useEffect(() => {
    aliveRef.current = true;
    setLoading(true);
    void load();
    let timer: number | undefined;
    if (intervalMs && intervalMs > 0) {
      timer = window.setInterval(() => void load(), intervalMs);
    }
    return () => {
      aliveRef.current = false;
      if (timer) window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, intervalMs, ...deps]);

  const refresh = useCallback(() => void load(), [load]);
  return { data, error, loading, refresh };
}

// --- formatters -------------------------------------------------------------

export function formatNumber(n: number | undefined | null): string {
  const v = n ?? 0;
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(1)}k`;
  return String(v);
}

export function formatUsd(n: number | undefined | null): string {
  const v = n ?? 0;
  if (v === 0) return "$0";
  return `$${v < 1 ? v.toFixed(4) : v.toFixed(2)}`;
}

export function formatUptime(seconds: number | undefined | null): string {
  const s = Math.max(0, Math.floor(seconds ?? 0));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

export function formatRelative(ms: number | undefined | null): string {
  if (!ms) return "—";
  const diff = Date.now() - ms;
  const abs = Math.abs(diff);
  const min = Math.floor(abs / 60000);
  const suffix = diff >= 0 ? "ago" : "from now";
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ${suffix}`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ${suffix}`;
  const d = Math.floor(h / 24);
  return `${d}d ${suffix}`;
}

export function formatDateTime(ms: number | undefined | null): string {
  if (!ms) return "—";
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return "—";
  }
}

// --- layout primitives ------------------------------------------------------

export function Panel({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-2xl border border-border/60 bg-card/80 p-5 shadow-sm", className)}>
      {(title || actions) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-[15px] font-semibold tracking-tight text-foreground">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatCard({
  label,
  value,
  sub,
  icon: Icon,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ComponentType<LucideProps>;
}) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/80 p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-[12px] font-medium text-muted-foreground">{label}</span>
        {Icon ? <Icon className="h-4 w-4 text-muted-foreground/70" aria-hidden /> : null}
      </div>
      <div className="mt-2 text-[26px] font-semibold leading-none tracking-tight text-foreground">{value}</div>
      {sub ? <div className="mt-1.5 text-[12px] text-muted-foreground">{sub}</div> : null}
    </div>
  );
}

export function StatusDot({ ok, className }: { ok: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        ok ? "bg-emerald-500" : "bg-muted-foreground/40",
        className,
      )}
      aria-hidden
    />
  );
}

export function Badge({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "ok" | "warn" | "error" }) {
  const tones: Record<string, string> = {
    muted: "bg-muted text-muted-foreground",
    ok: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    warn: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    error: "bg-destructive/10 text-destructive",
  };
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium", tones[tone])}>
      {children}
    </span>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border/60 bg-card/40 px-4 py-8 text-center text-[13px] text-muted-foreground">
      {children}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label ?? "Loading…"}
    </div>
  );
}

export function QueryState<T>({
  query,
  children,
}: {
  query: DashboardQuery<T>;
  children: (data: T) => ReactNode;
}) {
  if (query.loading && query.data === null) return <Spinner />;
  if (query.error && query.data === null) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-[13px] text-destructive">
        {query.error}
      </div>
    );
  }
  if (query.data === null) return <EmptyState>No data.</EmptyState>;
  return <>{children(query.data)}</>;
}

// --- charts -----------------------------------------------------------------

/** Lightweight responsive SVG area chart (no chart library). */
export function AreaChart({
  points,
  height = 150,
}: {
  points: Array<{ label: string; value: number }>;
  height?: number;
}) {
  if (points.length === 0) return <EmptyState>No data in this window yet.</EmptyState>;
  const W = 720;
  const H = height;
  const pad = 6;
  const max = Math.max(1, ...points.map((p) => p.value));
  const n = points.length;
  const xAt = (i: number) => (n === 1 ? W / 2 : (i / (n - 1)) * (W - pad * 2) + pad);
  const yAt = (v: number) => H - pad - (v / max) * (H - pad * 2);
  const line = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(p.value).toFixed(1)}`)
    .join(" ");
  const area = `${line} L${xAt(n - 1).toFixed(1)},${H - pad} L${xAt(0).toFixed(1)},${H - pad} Z`;
  const last = points[n - 1];
  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="w-full text-primary"
        style={{ height }}
        role="img"
        aria-label="usage chart"
      >
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={pad}
            x2={W - pad}
            y1={pad + f * (H - pad * 2)}
            y2={pad + f * (H - pad * 2)}
            stroke="hsl(var(--border))"
            strokeWidth={1}
            strokeDasharray="3 4"
            opacity={0.5}
          />
        ))}
        <path d={area} fill="hsl(var(--primary))" opacity={0.12} />
        <path d={line} fill="none" stroke="hsl(var(--primary))" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        <circle cx={xAt(n - 1)} cy={yAt(last.value)} r={3.5} fill="hsl(var(--primary))" />
      </svg>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>{points[0]?.label}</span>
        <span>{last?.label}</span>
      </div>
    </div>
  );
}

/** Horizontal proportion bar (for per-model breakdowns). */
export function ProportionBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className="h-full rounded-full bg-primary/70" style={{ width: `${pct}%` }} />
    </div>
  );
}
