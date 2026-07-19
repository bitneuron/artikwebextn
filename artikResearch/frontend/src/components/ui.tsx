import React from "react";

export function Pill({ children, color = "#8b949e" }: { children: React.ReactNode; color?: string }) {
  return (
    <span className="pill" style={{ color, border: `1px solid ${color}44`, background: `${color}18` }}>
      {children}
    </span>
  );
}

export function statusColor(s?: string) {
  return ({ uploaded: "#8b949e", extracted: "#60a5fa", analyzed: "#a78bfa", ready: "#34d399" } as any)[s || ""] || "#8b949e";
}

export function readinessColor(v?: number) {
  if (v == null) return "#8b949e";
  return v >= 85 ? "#34d399" : v >= 65 ? "#fbbf24" : "#f87171";
}

export function ScoreBar({ label, value }: { label: string; value: number }) {
  const c = readinessColor(value);
  return (
    <div className="flex items-center gap-3 py-1">
      <div className="text-mut text-xs w-40 shrink-0">{label}</div>
      <div className="flex-1 h-2 rounded-full bg-[#0d1117] overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${value}%`, background: c }} />
      </div>
      <div className="text-xs w-10 text-right" style={{ color: c }}>{value}%</div>
    </div>
  );
}

export function Ring({ value, size = 96 }: { value: number; size?: number }) {
  const c = readinessColor(value);
  const r = (size - 12) / 2;
  const circ = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} stroke="#30363d" strokeWidth="8" fill="none" />
      <circle cx={size / 2} cy={size / 2} r={r} stroke={c} strokeWidth="8" fill="none"
        strokeDasharray={circ} strokeDashoffset={circ * (1 - value / 100)} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" textAnchor="middle" dy=".35em" fontSize="20" fontWeight="700" fill={c}>{value}%</text>
    </svg>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`card p-4 ${className}`}>{children}</div>;
}

export function Spinner({ label = "Working…" }: { label?: string }) {
  return <div className="text-mut text-sm animate-pulse">⟳ {label}</div>;
}
