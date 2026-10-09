import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";

import { formatNumber } from "../lib/format";
import styles from "./Charts.module.css";

export const SERIES = ["#0284c7", "#14b8a6", "#f59e0b", "#ef4444", "#6366f1", "#94a3b8"];

function ChartTooltip({ active, payload, label, format = (n: number) => formatNumber(n) }: TooltipProps<number, string> & { format?: (n: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      {label !== undefined && <div className={styles.tooltipLabel}>{label}</div>}
      {payload.map((p) => (
        <div key={String(p.dataKey ?? p.name)} className={styles.tooltipRow}>
          <span className={styles.swatch} style={{ background: p.color ?? (p.payload as { fill?: string })?.fill }} />
          <span>{p.name}</span>
          <strong>{format(Number(p.value))}</strong>
        </div>
      ))}
    </div>
  );
}

/** Donut with a centered total and a value/percent legend. */
export function DonutChart({ data, centerLabel }: { data: { label: string; count: number }[]; centerLabel: string }) {
  const total = data.reduce((s, d) => s + d.count, 0);
  return (
    <div className={styles.donutWrap}>
      <div className={styles.donut}>
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie data={data} dataKey="count" nameKey="label" innerRadius="64%" outerRadius="92%" paddingAngle={2} stroke="none" animationDuration={900}>
              {data.map((d, i) => (
                <Cell key={d.label} fill={SERIES[i % SERIES.length]} />
              ))}
            </Pie>
            <Tooltip content={<ChartTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className={styles.center}>
          <strong>{formatNumber(total)}</strong>
          <span>{centerLabel}</span>
        </div>
      </div>
      <ul className={styles.legend}>
        {data.map((d, i) => (
          <li key={d.label}>
            <span className={styles.swatch} style={{ background: SERIES[i % SERIES.length] }} />
            <span className={styles.legendLabel}>{d.label}</span>
            <strong>{formatNumber(d.count)}</strong>
            <span className={styles.legendPct}>{total ? ((d.count / total) * 100).toFixed(1) : "0.0"}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Bars (volume, left axis) + line (rate, right axis). */
export function BarLineChart<T extends Record<string, unknown>>({
  data,
  x,
  bar,
  line,
  barName,
  lineName,
  height = 260,
  formatLine = (n: number) => formatNumber(n, 1),
  xFormatter,
}: {
  data: T[];
  x: keyof T & string;
  bar: keyof T & string;
  line: keyof T & string;
  barName: string;
  lineName: string;
  height?: number;
  formatLine?: (n: number) => string;
  xFormatter?: (v: string) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <defs>
          <linearGradient id="barFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="100%" stopColor="#0284c7" />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
        <XAxis dataKey={x} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#5b6b82" }} tickFormatter={xFormatter} />
        <YAxis yAxisId="l" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#5b6b82" }} tickFormatter={(v) => formatNumber(v)} />
        <YAxis yAxisId="r" orientation="right" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#5b6b82" }} />
        <Tooltip content={<ChartTooltip format={(n) => formatLine(n)} />} cursor={{ fill: "rgba(2,132,199,0.06)" }} />
        <Bar yAxisId="l" dataKey={bar} name={barName} fill="url(#barFill)" radius={[6, 6, 0, 0]} maxBarSize={28} animationDuration={900} />
        <Line yAxisId="r" dataKey={line} name={lineName} stroke="#14b8a6" strokeWidth={2.5} dot={false} type="monotone" animationDuration={1200} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Smooth area trend for one or more series. */
export function AreaTrend<T extends Record<string, unknown>>({
  data,
  x,
  series,
  height = 280,
  xFormatter,
}: {
  data: T[];
  x: keyof T & string;
  series: { key: keyof T & string; name: string }[];
  height?: number;
  xFormatter?: (v: string) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`area-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={SERIES[i]} stopOpacity={0.35} />
              <stop offset="100%" stopColor={SERIES[i]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
        <XAxis dataKey={x} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#5b6b82" }} tickFormatter={xFormatter} minTickGap={24} />
        <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#5b6b82" }} tickFormatter={(v) => formatNumber(v)} />
        <Tooltip content={<ChartTooltip />} />
        {series.map((s, i) => (
          <Area key={s.key} dataKey={s.key} name={s.name} type="monotone" stroke={SERIES[i]} strokeWidth={2.2} fill={`url(#area-${i})`} animationDuration={1100} />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars for ranked categories. */
export function RankedBars({ data, height = 260, format = (n: number) => formatNumber(n) }: { data: { label: string; value: number }[]; height?: number; format?: (n: number) => string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <ul className={styles.ranked} style={{ maxHeight: height }}>
      {data.map((d, i) => (
        <li key={d.label}>
          <span className={styles.rankedLabel}>{d.label}</span>
          <span className={styles.rankedTrack}>
            <span className={styles.rankedFill} style={{ width: `${(d.value / max) * 100}%`, animationDelay: `${i * 50}ms` }} />
          </span>
          <strong>{format(d.value)}</strong>
        </li>
      ))}
    </ul>
  );
}
