import type { VesselScoreFactors } from "../api/types";

const FACTOR_LABELS: Array<[keyof VesselScoreFactors, string]> = [
  ["proximity", "Proximity"],
  ["temporal_proximity", "Temporal"],
  ["trajectory_alignment", "Trajectory"],
  ["speed_anomaly", "Speed"],
  ["course_anomaly", "Course"],
  ["ais_gap", "AIS gap"]
];

export function FactorBars({ factors }: { factors: VesselScoreFactors }) {
  return (
    <div className="factor-bars">
      {FACTOR_LABELS.map(([key, label]) => {
        const value = Math.max(0, Math.min(1, factors[key] ?? 0));
        return (
          <div className="factor-row" key={key}>
            <span>{label}</span>
            <div className="factor-track">
              <div className="factor-fill" style={{ width: `${Math.round(value * 100)}%` }} />
            </div>
            <strong>{Math.round(value * 100)}</strong>
          </div>
        );
      })}
    </div>
  );
}
