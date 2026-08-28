interface StatusPillProps {
  label: string;
  tone?: "ok" | "warn" | "danger" | "muted";
}

export function StatusPill({ label, tone = "muted" }: StatusPillProps) {
  return <span className={`status-pill status-${tone}`}>{label}</span>;
}
