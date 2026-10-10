"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Metrics } from "@/lib/types";

const SERIES = [
  { key: "succeeded", label: "Succeeded", color: "var(--success)" },
  { key: "failed", label: "Failed", color: "var(--danger)" },
  { key: "other", label: "Other", color: "var(--muted-foreground)" },
] as const;

function shortDate(value: string) {
  const d = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
}

export function ExecutionsChart({ daily }: { daily: Metrics["daily"] }) {
  return (
    <div className="h-56 w-full" role="img" aria-label="Executions per day, stacked by outcome">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={daily} margin={{ top: 8, right: 8, left: -18, bottom: 0 }} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
          />
          <YAxis
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
          />
          <Tooltip
            cursor={{ fill: "var(--muted)", opacity: 0.6 }}
            labelFormatter={(v) => shortDate(String(v))}
            contentStyle={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              fontSize: 12,
              color: "var(--foreground)",
            }}
            itemStyle={{ color: "var(--foreground)" }}
          />
          <Legend
            iconType="square"
            iconSize={8}
            wrapperStyle={{ fontSize: 11, color: "var(--muted-foreground)", paddingTop: 4 }}
          />
          {SERIES.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stackId="executions"
              fill={s.color}
              stroke="var(--card)"
              strokeWidth={1}
              maxBarSize={36}
              radius={i === SERIES.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
