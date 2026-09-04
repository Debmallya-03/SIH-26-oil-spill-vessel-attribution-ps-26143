import { useEffect, useMemo, useState, type ComponentType, type CSSProperties, type SVGProps } from "react";
import { API_BASE_URL, ApiError } from "./api/client";
import { getHealth } from "./api/health";
import { getIncident, getIncidentVessels, listIncidents } from "./api/incidents";
import { runPipeline } from "./api/pipeline";
import type {
  HealthResponse,
  IncidentDetail,
  IncidentSummary,
  PipelineRequest,
  PipelineResponse,
  VesselScore,
  VesselScoreFactors
} from "./api/types";
import { FactorBars } from "./components/FactorBars";
import {
  IconAlertTriangle,
  IconArchive,
  IconBolt,
  IconCheck,
  IconCloud,
  IconDatabase,
  IconRadar,
  IconShip,
  IconSignal,
  IconWaves,
  NAV_ICONS
} from "./components/Icons";
import { MaritimeMap } from "./components/MaritimeMap";
import { StatusPill } from "./components/StatusPill";

type Page = "overview" | "analysis" | "investigation" | "incidents" | "vessels" | "status";
type StageState = "idle" | "running" | "complete" | "failed";

const NAV: Array<[Page, string]> = [
  ["overview", "Overview"],
  ["analysis", "New Analysis"],
  ["investigation", "Live Investigation"],
  ["incidents", "Incidents"],
  ["vessels", "Vessel Intelligence"],
  ["status", "System Status"]
];

const DEMO_SEED = {
  latitude: 18.5,
  longitude: 72.8333511352539,
  timestamp: "2026-08-26T12:00:00Z"
};

const DEMO_REQUEST: PipelineRequest = {
  pipeline_mode: "demo",
  image_path: "../data/deep_sar_sos/extracted/images/val/palsar_0.png",
  spill_seed: DEMO_SEED,
  detection_mode: "deep_sar_sos",
  drift_mode: "real_data",
  drift_engine: "opendrift_openoil",
  drift_forcing_strategy: "native_grid",
  attribution_mode: "synthetic_dev",
  persist: true
};

const EMPTY_REQUEST: PipelineRequest = {
  pipeline_mode: "demo",
  image_path: "",
  spill_seed: DEMO_SEED,
  detection_mode: "deep_sar_sos",
  drift_mode: "real_data",
  drift_engine: "opendrift_openoil",
  drift_forcing_strategy: "native_grid",
  attribution_mode: "synthetic_dev",
  persist: true
};

function App() {
  const [page, setPage] = useState<Page>("overview");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<IncidentDetail | null>(null);
  const [selectedVessel, setSelectedVessel] = useState<VesselScore | null>(null);
  const [pipelineRequest, setPipelineRequest] = useState<PipelineRequest>(EMPTY_REQUEST);
  const [pipelineResult, setPipelineResult] = useState<PipelineResponse | null>(null);
  const [stageState, setStageState] = useState<Record<string, StageState>>(initialStages());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [incidentFilter, setIncidentFilter] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    refreshSystem();
  }, []);

  const activeResult = pipelineResult ?? detailToPipeline(selectedIncident);
  const candidates = activeResult?.attribution?.suspects ?? selectedIncident?.vessel_candidates ?? [];
  const filteredIncidents = incidents.filter((incident) => {
    const target = `${incident.incident_id} ${incident.status ?? ""} ${incident.scenario ?? ""} ${incident.pipeline_mode ?? ""}`.toLowerCase();
    return target.includes(incidentFilter.toLowerCase());
  });
  const completedCount = incidents.filter((incident) => incident.status === "completed").length;

  async function refreshSystem() {
    try {
      const [healthResponse, incidentResponse] = await Promise.all([getHealth(), listIncidents()]);
      setHealth(healthResponse);
      if (incidentResponse.status === "success") {
        setIncidents(incidentResponse.incidents);
      } else {
        setIncidents([]);
        setError(incidentResponse.message ?? "Incident persistence is unavailable.");
      }
      setLastUpdated(new Date());
    } catch (apiError) {
      setError(formatApiError(apiError));
    }
  }

  function loadDemoScenario() {
    setPipelineRequest(DEMO_REQUEST);
    setPage("analysis");
    setError(null);
  }

  async function submitPipeline() {
    setLoading(true);
    setError(null);
    setStageState(markRunning());
    setPipelineResult(null);
    try {
      const payload = normalizeRequest(pipelineRequest);
      const response = await runPipeline(payload);
      setPipelineResult(response);
      setSelectedIncident(null);
      setSelectedVessel(response.summary.top_candidate ?? response.attribution?.suspects?.[0] ?? null);
      setStageState(stagesFromPipeline(response));
      if (response.status !== "completed") {
        setError(formatPipelineStatus(response));
      }
      setPage("investigation");
      await refreshSystem();
    } catch (apiError) {
      setStageState(markFailed());
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  async function openIncident(incidentId: string) {
    setError(null);
    try {
      const [detail, vessels] = await Promise.all([getIncident(incidentId), getIncidentVessels(incidentId)]);
      const merged = { ...detail, vessel_candidates: vessels.vessels.length ? vessels.vessels : detail.vessel_candidates };
      setSelectedIncident(merged);
      setPipelineResult(null);
      setSelectedVessel(merged.vessel_candidates?.[0] ?? null);
      setPage("investigation");
    } catch (apiError) {
      setError(formatApiError(apiError));
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-row">
          <span className="brand-icon">
            <IconRadar width={20} height={20} />
          </span>
          <div className="brand-text">
            <div className="brand-mark">
              MARIS
              <span className="brand-subtitle">AI Marine Spill Intelligence</span>
            </div>
            <p>Visual investigation dashboard</p>
          </div>
        </div>
        <div className="topbar-status">
          <StatusPill label={`API ${health?.status ?? "checking"}`} tone={health?.status === "healthy" ? "ok" : "warn"} />
          <StatusPill label={`PostGIS ${health?.database?.status ?? "unknown"}`} tone={health?.database?.status === "connected" ? "ok" : "warn"} />
          <StatusPill label={activeResult?.status ? `Investigation ${activeResult.status}` : "No active run"} tone={activeResult?.status === "completed" ? "ok" : activeResult ? "warn" : "muted"} />
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <div className="sidebar-rail">
            {NAV.map(([key, label]) => {
              const NavIcon = NAV_ICONS[key];
              return (
                <button key={key} className={page === key ? "nav-active" : ""} onClick={() => setPage(key)}>
                  <NavIcon />
                  <span>{label}</span>
                </button>
              );
            })}
            <button className="demo-button" onClick={loadDemoScenario}>
              <IconBolt />
              <span>Load Demo Scenario</span>
            </button>
            <div className="api-box">
              <span>Backend</span>
              <code>{API_BASE_URL}</code>
            </div>
          </div>
        </aside>

        <main className="content">
          {error && <div className="alert-banner">{error}</div>}
          {page === "overview" && (
            <Overview
              health={health}
              incidents={incidents}
              completedCount={completedCount}
              latest={incidents[0]}
              result={activeResult}
              seed={pipelineRequest.spill_seed}
              lastUpdated={lastUpdated}
              onRefresh={refreshSystem}
              onNavigate={setPage}
              onOpenIncident={openIncident}
              onDemo={loadDemoScenario}
            />
          )}
          {page === "analysis" && (
            <NewAnalysis
              request={pipelineRequest}
              setRequest={setPipelineRequest}
              loading={loading}
              stageState={stageState}
              onSubmit={submitPipeline}
              onDemo={loadDemoScenario}
            />
          )}
          {page === "investigation" && (
            <LiveInvestigation
              result={activeResult}
              seed={pipelineRequest.spill_seed}
              candidates={candidates}
              selectedVessel={selectedVessel}
              setSelectedVessel={setSelectedVessel}
            />
          )}
          {page === "incidents" && (
            <Incidents
              incidents={filteredIncidents}
              dbConnected={health?.database?.status === "connected"}
              filter={incidentFilter}
              setFilter={setIncidentFilter}
              onOpen={openIncident}
              onRefresh={refreshSystem}
            />
          )}
          {page === "vessels" && (
            <VesselIntelligence
              candidates={candidates}
              selected={selectedVessel}
              setSelected={setSelectedVessel}
              incidents={incidents}
              lastUpdated={lastUpdated}
              onRefresh={refreshSystem}
            />
          )}
          {page === "status" && <SystemStatus health={health} result={activeResult} onRefresh={refreshSystem} />}
        </main>
      </div>
    </div>
  );
}

function Overview({
  health,
  incidents,
  completedCount,
  latest,
  result,
  seed,
  lastUpdated,
  onRefresh,
  onNavigate,
  onOpenIncident,
  onDemo
}: {
  health: HealthResponse | null;
  incidents: IncidentSummary[];
  completedCount: number;
  latest?: IncidentSummary;
  result: PipelineResponse | null;
  seed?: { latitude: number; longitude: number } | null;
  lastUpdated: Date | null;
  onRefresh: () => void;
  onNavigate: (page: Page) => void;
  onOpenIncident: (incidentId: string) => void;
  onDemo: () => void;
}) {
  const components = [
    {
      label: "SAR Detection",
      value: result?.detection?.status ?? "available via /detect",
      provenance: result?.detection?.model_dataset_type ?? "Deep-SAR SOS checkpoint when demo pipeline is used",
      icon: IconRadar
    },
    {
      label: "Ocean Drift Engine",
      value: result?.drift?.engine ?? health?.opendrift?.engine ?? "available via /drift",
      provenance: result?.data_provenance?.drift_forcing_strategy ?? "Copernicus Marine + NOAA GFS in real_data mode",
      icon: IconWaves
    },
    {
      label: "AIS Attribution",
      value: result?.attribution?.status ?? "available via /score",
      provenance: result?.data_provenance?.ais ?? "synthetic_dev or real_ais",
      icon: IconSignal
    },
    {
      label: "PostGIS Integration",
      value: health?.database?.status ?? "unknown",
      provenance: "Optional Day-5 persistence",
      icon: IconDatabase
    }
  ];
  const hasMapData = Boolean(seed || result?.drift?.origin_centroid || result?.drift?.backward_path?.coordinates?.length || result?.drift?.forward_path?.coordinates?.length);
  const dbConnected = health?.database?.status === "connected";

  return (
    <section className="dash-grid">
      <div className="section-heading">
        <div>
          <h1>Maritime Intelligence Overview</h1>
          <p>Backend-derived operational view for the current SIH development system.</p>
        </div>
        <div className="dash-header-actions">
          <span className="dash-updated">{lastUpdated ? `Last updated ${formatDate(lastUpdated.toISOString())}` : "Not refreshed yet"}</span>
          <button className="secondary-button" onClick={onRefresh}>Refresh</button>
        </div>
      </div>

      <div className="dash-metric-grid">
        <DashMetric icon={IconArchive} tone="cyan" label="Stored Incidents" value={incidents.length} hint="Total incidents stored" />
        <DashMetric icon={IconCheck} tone="teal" label="Completed Investigations" value={completedCount} hint="Investigations completed" />
        <DashMetric icon={IconCloud} tone="blue" label="Backend API" value={health?.status ?? "checking"} hint="API status" />
        <DashMetric icon={IconDatabase} tone="amber" label="PostGIS Status" value={health?.database?.status ?? "unknown"} hint="Spatial DB status" />
      </div>

      <div className="dash-main-grid">
        <Panel title="System Components">
          {components.map((item) => (
            <ComponentStatus key={item.label} label={item.label} value={item.value} provenance={item.provenance} icon={item.icon} />
          ))}
        </Panel>

        <section className="panel dash-aoi-panel">
          <div className="dash-aoi-header">
            <h2>Area of Interest</h2>
            {hasMapData && <StatusPill label="Live" tone="ok" />}
          </div>
          {hasMapData ? (
            <MaritimeMap result={result} seed={seed} compact />
          ) : (
            <EmptyState title="No active geometry" text="Run an investigation to plot the spill seed and drift paths." />
          )}
        </section>

        <Panel title="Latest Analysis">
          {latest ? (
            <div className="detail-list">
              <span>Incident</span><code>{latest.incident_id}</code>
              <span>Status</span><strong>{latest.status ?? "unknown"}</strong>
              <span>Scenario</span><strong>{latest.scenario ?? "not recorded"}</strong>
              <span>Created</span><strong>{formatDate(latest.created_at)}</strong>
            </div>
          ) : (
            <EmptyState title="No stored incidents" text="Run a persisted demo pipeline after PostGIS is available." />
          )}
          <button className="primary-button dash-cta" onClick={onDemo}>
            <IconBolt />
            Run Demo Pipeline
          </button>
        </Panel>
      </div>

      <div className="dash-secondary-grid">
        <Panel title="Incidents Over Time">
          <IncidentsChart incidents={incidents} dbConnected={dbConnected} onRunDemo={onDemo} />
        </Panel>
        <Panel title="Component Health">
          <ComponentHealthDonut items={components} />
        </Panel>
        <Panel title="Recent Incidents">
          <RecentIncidents incidents={incidents} dbConnected={dbConnected} onOpen={onOpenIncident} onViewAll={() => onNavigate("incidents")} onRunDemo={onDemo} />
        </Panel>
      </div>
    </section>
  );
}

function DashMetric({
  icon: Icon,
  tone,
  label,
  value,
  hint
}: {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  tone: "cyan" | "teal" | "blue" | "amber";
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className={`dash-metric tone-${tone}`}>
      <div className="dash-icon-badge">
        <Icon width={20} height={20} />
      </div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{hint}</small>
      </div>
    </div>
  );
}

function categorizeStatus(value: string): "available" | "development" | "unknown" {
  const normalized = value.toLowerCase();
  if (normalized.includes("available") || normalized.includes("success") || normalized.includes("connected")) {
    return "available";
  }
  if (normalized.includes("development") || normalized.includes("dev")) {
    return "development";
  }
  return "unknown";
}

const DONUT_COLORS: Record<"available" | "development" | "unknown", string> = {
  available: "#2dd4bf",
  development: "#38bdf8",
  unknown: "#f59e0b"
};

function ComponentHealthDonut({ items }: { items: Array<{ label: string; value: string }> }) {
  const counts = { available: 0, development: 0, unknown: 0 };
  items.forEach((item) => {
    counts[categorizeStatus(item.value)] += 1;
  });
  const total = items.length;
  const segments = (["available", "development", "unknown"] as const).map((key) => ({
    key,
    label: key === "available" ? "Available" : key === "development" ? "Development" : "Unknown",
    count: counts[key],
    color: DONUT_COLORS[key]
  }));
  let cursor = 0;
  const stops = segments
    .filter((segment) => segment.count > 0)
    .map((segment) => {
      const start = (cursor / total) * 360;
      cursor += segment.count;
      const end = (cursor / total) * 360;
      return `${segment.color} ${start}deg ${end}deg`;
    })
    .join(", ");

  return (
    <div className="donut-widget">
      <div className="donut-ring" style={{ background: total ? `conic-gradient(${stops})` : "rgba(148, 163, 184, 0.16)" }}>
        <div className="donut-center">
          <strong>{total}</strong>
          <span>Total</span>
        </div>
      </div>
      <ul className="donut-legend">
        {segments.map((segment) => (
          <li key={segment.key}>
            <span className="legend-dot" style={{ background: segment.color }} />
            {segment.label}
            <b>{segment.count}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

function IncidentsChart({
  incidents,
  dbConnected,
  onRunDemo
}: {
  incidents: IncidentSummary[];
  dbConnected: boolean;
  onRunDemo: () => void;
}) {
  const buckets = buildDailyBuckets(incidents);
  if (!buckets.length) {
    if (!dbConnected) {
      return (
        <EmptyState
          title="Database not connected"
          text="PostGIS persistence is unavailable, so incident history can't be recorded yet. Check System Status for setup details."
        />
      );
    }
    return (
      <div className="empty-state-cta">
        <EmptyState title="No incident history yet" text="Persisted incidents will appear here as a daily trend." />
        <button className="secondary-button" onClick={onRunDemo}>
          <IconBolt />
          Run Demo Pipeline
        </button>
      </div>
    );
  }
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1);
  return (
    <div className="trend-chart">
      {buckets.map((bucket) => (
        <div className="trend-bar" key={bucket.key}>
          <span className="trend-bar-count">{bucket.count}</span>
          <div className="trend-bar-track">
            <div className="trend-bar-fill" style={{ height: `${Math.max(6, (bucket.count / max) * 100)}%` }} />
          </div>
          <small>{bucket.label}</small>
        </div>
      ))}
    </div>
  );
}

function buildDailyBuckets(incidents: IncidentSummary[]) {
  const counts = new Map<string, number>();
  incidents.forEach((incident) => {
    if (!incident.created_at) {
      return;
    }
    const day = incident.created_at.slice(0, 10);
    counts.set(day, (counts.get(day) ?? 0) + 1);
  });
  return Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-7)
    .map(([key, count]) => ({
      key,
      count,
      label: new Date(key).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    }));
}

function RecentIncidents({
  incidents,
  dbConnected,
  onOpen,
  onViewAll,
  onRunDemo
}: {
  incidents: IncidentSummary[];
  dbConnected: boolean;
  onOpen: (incidentId: string) => void;
  onViewAll: () => void;
  onRunDemo: () => void;
}) {
  const recent = incidents.slice(0, 5);
  if (!recent.length) {
    if (!dbConnected) {
      return (
        <EmptyState
          title="Database not connected"
          text="PostGIS persistence is unavailable, so incidents can't be recorded yet. Check System Status for setup details."
        />
      );
    }
    return (
      <div className="empty-state-cta">
        <EmptyState title="No recent incidents" text="Persisted incidents will show up here." />
        <button className="secondary-button" onClick={onRunDemo}>
          <IconBolt />
          Run Demo Pipeline
        </button>
      </div>
    );
  }
  return (
    <div className="recent-list">
      {recent.map((incident) => (
        <button key={incident.incident_id} className="recent-row" onClick={() => onOpen(incident.incident_id)}>
          <span className={`recent-dot ${incident.status === "completed" ? "status-ok" : "status-warn"}`} />
          <div>
            <strong>{incident.scenario ?? incident.incident_id}</strong>
            <span>{formatDate(incident.created_at)}</span>
          </div>
          <StatusPill label={incident.status ?? "unknown"} tone={incident.status === "completed" ? "ok" : "warn"} />
        </button>
      ))}
      <button className="text-link" onClick={onViewAll}>View all incidents →</button>
    </div>
  );
}

function NewAnalysis({
  request,
  setRequest,
  loading,
  stageState,
  onSubmit,
  onDemo
}: {
  request: PipelineRequest;
  setRequest: (next: PipelineRequest) => void;
  loading: boolean;
  stageState: Record<string, StageState>;
  onSubmit: () => void;
  onDemo: () => void;
}) {
  const seed = request.spill_seed ?? DEMO_SEED;
  return (
    <section className="page-grid">
      <div className="section-heading">
        <div>
          <h1>New Investigation</h1>
          <p>Submit the existing Day-5 pipeline schema. Geospatial spill seed is explicit.</p>
        </div>
        <button className="secondary-button" onClick={onDemo}>Load Demo Scenario</button>
      </div>
      <div className="analysis-grid">
        <Panel title="Investigation Input">
          <div className="form-grid">
            <Field label="SAR image path">
              <input value={request.image_path ?? ""} onChange={(event) => setRequest({ ...request, image_path: event.target.value })} />
            </Field>
            <Field label="Latitude">
              <input type="number" value={seed.latitude} onChange={(event) => setRequest({ ...request, spill_seed: { ...seed, latitude: Number(event.target.value) } })} />
            </Field>
            <Field label="Longitude">
              <input type="number" value={seed.longitude} onChange={(event) => setRequest({ ...request, spill_seed: { ...seed, longitude: Number(event.target.value) } })} />
            </Field>
            <Field label="Timestamp">
              <input value={seed.timestamp} onChange={(event) => setRequest({ ...request, spill_seed: { ...seed, timestamp: event.target.value } })} />
            </Field>
            <Field label="Pipeline mode">
              <select value={request.pipeline_mode} onChange={(event) => setRequest({ ...request, pipeline_mode: event.target.value as PipelineRequest["pipeline_mode"] })}>
                <option value="demo">demo</option>
                <option value="detection_only">detection_only</option>
                <option value="real_validation">real_validation</option>
              </select>
            </Field>
            <Field label="Detection model">
              <select value={request.detection_mode ?? "deep_sar_sos"} onChange={(event) => setRequest({ ...request, detection_mode: event.target.value as PipelineRequest["detection_mode"] })}>
                <option value="deep_sar_sos">deep_sar_sos</option>
                <option value="synthetic_dev">synthetic_dev</option>
              </select>
            </Field>
            <Field label="Drift mode">
              <select value={request.drift_mode} onChange={(event) => setRequest({ ...request, drift_mode: event.target.value as PipelineRequest["drift_mode"] })}>
                <option value="real_data">real_data</option>
                <option value="synthetic_dev">synthetic_dev</option>
              </select>
            </Field>
            <Field label="Drift engine">
              <select value={request.drift_engine ?? "development_drift_engine"} onChange={(event) => setRequest({ ...request, drift_engine: event.target.value as PipelineRequest["drift_engine"] })}>
                <option value="development_drift_engine">development_drift_engine</option>
                <option value="opendrift_openoil">opendrift_openoil</option>
              </select>
            </Field>
            <Field label="Forcing strategy">
              <select value={request.drift_forcing_strategy ?? "native_grid"} onChange={(event) => setRequest({ ...request, drift_forcing_strategy: event.target.value as PipelineRequest["drift_forcing_strategy"] })}>
                <option value="native_grid">native_grid</option>
                <option value="constant_sample">constant_sample</option>
              </select>
            </Field>
            <Field label="Attribution mode">
              <select value={request.attribution_mode} onChange={(event) => setRequest({ ...request, attribution_mode: event.target.value as PipelineRequest["attribution_mode"] })}>
                <option value="synthetic_dev">synthetic_dev</option>
                <option value="real_data">real_data</option>
              </select>
            </Field>
            <label className="checkbox-field">
              <input type="checkbox" checked={request.persist} onChange={(event) => setRequest({ ...request, persist: event.target.checked })} />
              Persist to PostGIS
            </label>
          </div>
          <button className="primary-button" onClick={onSubmit} disabled={loading}>
            {loading && <span className="button-spinner" aria-hidden="true" />}
            {loading ? "Running Investigation" : "Run Investigation"}
          </button>
        </Panel>
        <Panel title="Pipeline Progress">
          <StageList stages={stageState} />
          <div className="notice">
            Stage completion reflects the final backend response. The API does not stream intermediate progress yet.
          </div>
        </Panel>
      </div>
    </section>
  );
}

function LiveInvestigation({
  result,
  seed,
  candidates,
  selectedVessel,
  setSelectedVessel
}: {
  result: PipelineResponse | null;
  seed?: { latitude: number; longitude: number } | null;
  candidates: VesselScore[];
  selectedVessel: VesselScore | null;
  setSelectedVessel: (vessel: VesselScore) => void;
}) {
  return (
    <section className="investigation-layout">
      <MaritimeMap result={result} seed={seed} />
      <aside className="investigation-panel">
        <Panel title="Investigation">
          {result ? (
            <div className="detail-list">
              <span>Incident ID</span><code>{result.incident_id}</code>
              <span>Status</span><strong>{result.status}</strong>
              <span>Detection</span><strong>{result.detection.status}</strong>
              <span>Detection model</span><strong>{result.detection.model ?? "not reported"}</strong>
              <span>Dataset</span><strong>{result.detection.model_dataset_type ?? result.data_provenance?.sar ?? "not reported"}</strong>
              <span>Confidence</span><strong>{formatPercent(result.detection.confidence)}</strong>
              <span>Area</span><strong>{formatPixels(result.detection.area_pixels)}</strong>
              <span>Perimeter</span><strong>{formatPixels(result.detection.perimeter_pixels)}</strong>
              <span>Hindcasting engine</span><strong>{result.drift?.engine ?? "not available"}</strong>
              <span>Forcing strategy</span><strong>{result.data_provenance?.drift_forcing_strategy ?? result.drift?.metadata?.forcing_strategy ?? "not reported"}</strong>
              <span>Estimated origin</span><strong>{formatCoordinate(result.drift?.origin_centroid)}</strong>
              <span>Origin window</span><strong>{formatWindow(result.drift?.origin_time_window)}</strong>
              <span>Hindcast points</span><strong>{result.drift?.backward_path?.coordinates?.length ?? 0}</strong>
              <span>Forecast points</span><strong>{result.drift?.forward_path?.coordinates?.length ?? 0}</strong>
              <span>Candidates</span><strong>{result.summary.candidate_vessels ?? candidates.length}</strong>
              <span>Top candidate</span><strong>{result.summary.top_candidate?.vessel_name ?? "None"}</strong>
              <span>Persistence</span><strong>{result.persistence.status}</strong>
            </div>
          ) : (
            <EmptyState title="No active investigation" text="Run the demo scenario or open a persisted incident." />
          )}
        </Panel>
        <Panel title="Provenance">
          <Provenance result={result} />
        </Panel>
        <Panel title="Ranked Candidates">
          {result?.attribution?.mode && (
            <div className="inline-badges">
              <StatusPill
                label={result.attribution.mode === "synthetic_dev" ? "Synthetic AIS Demo" : "Historical AIS"}
                tone={result.attribution.mode === "synthetic_dev" ? "warn" : "ok"}
              />
            </div>
          )}
          <VesselList vessels={candidates} selected={selectedVessel} onSelect={setSelectedVessel} compact />
        </Panel>
      </aside>
    </section>
  );
}

function Incidents({
  incidents,
  dbConnected,
  filter,
  setFilter,
  onOpen,
  onRefresh
}: {
  incidents: IncidentSummary[];
  dbConnected: boolean;
  filter: string;
  setFilter: (value: string) => void;
  onOpen: (id: string) => void;
  onRefresh: () => void;
}) {
  return (
    <section className="page-grid">
      <div className="section-heading">
        <div>
          <h1>Incident History</h1>
          <p>Stored Day-5 pipeline incidents from PostGIS.</p>
        </div>
        <button className="secondary-button" onClick={onRefresh}>Refresh</button>
      </div>
      <Panel title="Search Incidents">
        <input className="wide-input" placeholder="Search by incident, scenario, status, or mode" value={filter} onChange={(event) => setFilter(event.target.value)} />
      </Panel>
      <div className="table-panel">
        {incidents.length > 0 && (
          <div className="incident-row incident-header">
            <span>Incident</span>
            <span>Created</span>
            <span>Scenario</span>
            <span>Status</span>
            <span>Mode</span>
          </div>
        )}
        {incidents.length ? incidents.map((incident) => (
          <button className="incident-row" key={incident.incident_id} onClick={() => onOpen(incident.incident_id)}>
            <code>{incident.incident_id}</code>
            <span>{formatDate(incident.created_at)}</span>
            <strong>{incident.scenario ?? "unknown"}</strong>
            <StatusPill label={incident.status ?? "unknown"} tone={incident.status === "completed" ? "ok" : "warn"} />
            <span>{incident.pipeline_mode ?? "not recorded"}</span>
          </button>
        )) : (
          <EmptyState
            title={dbConnected ? "No persisted incidents yet" : "Persistence unavailable"}
            text={dbConnected ? "Run a persisted investigation to populate incident history." : "PostGIS is unavailable, so persisted incidents cannot be loaded."}
          />
        )}
      </div>
    </section>
  );
}

function VesselIntelligence({
  candidates,
  selected,
  setSelected,
  incidents,
  lastUpdated,
  onRefresh
}: {
  candidates: VesselScore[];
  selected: VesselScore | null;
  setSelected: (vessel: VesselScore) => void;
  incidents: IncidentSummary[];
  lastUpdated: Date | null;
  onRefresh: () => void;
}) {
  const active = selected ?? candidates[0] ?? null;
  const total = candidates.length;
  const highRisk = candidates.filter((vessel) => vessel.priority === "high").length;
  const highRiskPct = total ? Math.round((highRisk / total) * 100) : 0;
  const avgScore = total ? candidates.reduce((sum, vessel) => sum + vessel.score, 0) / total : 0;
  const distances = candidates.map((vessel) => vessel.minimum_distance_km).filter((distance): distance is number => distance != null);
  const closest = distances.length ? Math.min(...distances) : null;
  const sourceLabel = candidates[0]?.trajectory_source === "historical_ais" ? "Historical AIS" : candidates[0]?.trajectory_source === "synthetic_dev" ? "Synthetic AIS Demo" : "AIS source not available";

  return (
    <section className="dash-grid">
      <div className="section-heading">
        <div>
          <h1>Vessel Intelligence</h1>
          <p>Analyze candidate vessels and explainable attribution signals for the active investigation.</p>
        </div>
        <div className="dash-header-actions">
          <StatusPill label={sourceLabel} tone={sourceLabel === "Historical AIS" ? "ok" : sourceLabel === "Synthetic AIS Demo" ? "warn" : "muted"} />
          <span className="dash-updated">{lastUpdated ? `Last updated ${formatDate(lastUpdated.toISOString())}` : "Not refreshed yet"}</span>
          <button className="secondary-button" onClick={onRefresh}>Refresh</button>
        </div>
      </div>

      <div className="dash-metric-grid">
        <DashMetric icon={IconShip} tone="cyan" label="Candidate Vessels" value={total} hint="Across the active investigation" />
        <DashMetric icon={IconAlertTriangle} tone="amber" label="High Priority Vessels" value={highRisk} hint={total ? `${highRiskPct}% of candidates` : "No candidates yet"} />
        <DashMetric icon={IconCheck} tone="teal" label="Avg Attribution Score" value={total ? avgScore.toFixed(1) : "n/a"} hint="Average across candidates" />
        <DashMetric icon={IconRadar} tone="blue" label="Closest Vessel" value={closest != null ? formatKm(closest) : "n/a"} hint="Minimum distance to spill" />
      </div>

      <div className="vessel-charts-grid">
        <Panel title="Candidate Vessels Over Time">
          <CandidateTrendPanel incidents={incidents} />
        </Panel>
        <Panel title="Priority Distribution">
          <RiskDonut candidates={candidates} />
        </Panel>
      </div>

      <div className="vessel-charts-grid">
        <Panel title="Average Factor Breakdown">
          <AverageFactorBreakdown candidates={candidates} />
        </Panel>
        <Panel title="Score Distribution">
          <ScoreDistributionChart candidates={candidates} />
        </Panel>
      </div>

      <div className="analysis-grid">
        <Panel title="Candidate Vessels">
          <VesselTable vessels={candidates} selected={active} onSelect={setSelected} />
        </Panel>
        <Panel title="Explainable Attribution">
          {active ? (
            <div className="vessel-detail">
              <div className="vessel-hero">
                <div>
                  <h2>{active.vessel_name}</h2>
                  <code>{active.mmsi}</code>
                </div>
                <div
                  className="score-gauge"
                  style={gaugeStyle(active.score)}
                >
                  <span>{active.score.toFixed(1)}</span>
                </div>
              </div>
              <div className="detail-list">
                <span>Rank</span><strong>{active.rank ?? "n/a"}</strong>
                <span>Priority</span><strong>{active.priority ?? "unlabelled"}</strong>
                <span>Closest distance</span><strong>{formatKm(active.minimum_distance_km)}</strong>
                <span>Relevant time</span><strong>{formatDate(active.nearest_approach_time)}</strong>
              </div>
              <FactorBars factors={active.factors} />
              <h3>Why was this vessel ranked?</h3>
              <ul className="reason-list">
                {active.reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
              <p className="disclaimer">AIS gaps and anomaly scores are investigation signals, not proof of wrongdoing.</p>
            </div>
          ) : (
            <EmptyState title="No candidate selected" text="Run an investigation or open an incident with vessel candidates." />
          )}
        </Panel>
      </div>
    </section>
  );
}

const RISK_COLORS: Record<"high" | "medium" | "low", string> = {
  high: "#f87171",
  medium: "#fbbf24",
  low: "#5eead4"
};

function CandidateTrendPanel({ incidents }: { incidents: IncidentSummary[] }) {
  const [buckets, setBuckets] = useState<Array<{ key: string; label: string; count: number }> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const recent = incidents.slice(0, 8);
    if (!recent.length) {
      setBuckets([]);
      return;
    }
    setBuckets(null);
    Promise.all(
      recent.map((incident) =>
        getIncidentVessels(incident.incident_id)
          .then((response) => ({ incident, count: response.vessels.length }))
          .catch(() => ({ incident, count: 0 }))
      )
    ).then((results) => {
      if (cancelled) {
        return;
      }
      const counts = new Map<string, number>();
      results.forEach(({ incident, count }) => {
        if (!incident.created_at) {
          return;
        }
        const day = incident.created_at.slice(0, 10);
        counts.set(day, (counts.get(day) ?? 0) + count);
      });
      const sorted = Array.from(counts.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .slice(-7)
        .map(([key, count]) => ({
          key,
          count,
          label: new Date(key).toLocaleDateString(undefined, { month: "short", day: "numeric" })
        }));
      setBuckets(sorted);
    });
    return () => {
      cancelled = true;
    };
  }, [incidents]);

  if (buckets === null) {
    return <EmptyState title="Loading candidate history" text="Fetching vessel candidates from persisted incidents." />;
  }
  if (!buckets.length) {
    return <EmptyState title="No incident history yet" text="Candidate trends will appear once investigations are persisted to PostGIS." />;
  }
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1);
  return (
    <div className="trend-chart">
      {buckets.map((bucket) => (
        <div className="trend-bar" key={bucket.key}>
          <span className="trend-bar-count">{bucket.count}</span>
          <div className="trend-bar-track">
            <div className="trend-bar-fill" style={{ height: bucket.count ? `${Math.max(6, (bucket.count / max) * 100)}%` : "0%" }} />
          </div>
          <small>{bucket.label}</small>
        </div>
      ))}
    </div>
  );
}

const FACTOR_LABELS: Array<[keyof VesselScoreFactors, string]> = [
  ["proximity", "Proximity"],
  ["temporal_proximity", "Temporal"],
  ["trajectory_alignment", "Trajectory"],
  ["speed_anomaly", "Speed"],
  ["course_anomaly", "Course"],
  ["ais_gap", "AIS gap"]
];

function AverageFactorBreakdown({ candidates }: { candidates: VesselScore[] }) {
  if (!candidates.length) {
    return <EmptyState title="No candidates yet" text="Average factor breakdown will appear once vessel candidates are scored." />;
  }
  return (
    <div className="factor-bars">
      {FACTOR_LABELS.map(([key, label]) => {
        const avg = candidates.reduce((sum, vessel) => sum + Math.max(0, Math.min(1, vessel.factors[key] ?? 0)), 0) / candidates.length;
        const pct = Math.round(avg * 100);
        return (
          <div className="factor-row" key={key}>
            <span>{label}</span>
            <div className="factor-track">
              <div className="factor-fill" style={{ width: `${pct}%` }} />
            </div>
            <strong>{pct}</strong>
          </div>
        );
      })}
    </div>
  );
}

function RiskDonut({ candidates }: { candidates: VesselScore[] }) {
  const total = candidates.length;
  if (!total) {
    return <EmptyState title="No candidates yet" text="Risk distribution will appear once vessel candidates are scored." />;
  }
  const counts = { high: 0, medium: 0, low: 0 };
  candidates.forEach((vessel) => {
    const key = vessel.priority === "high" ? "high" : vessel.priority === "medium" ? "medium" : "low";
    counts[key] += 1;
  });
  const segments = (["high", "medium", "low"] as const).map((key) => ({
    key,
    label: key === "high" ? "High Priority" : key === "medium" ? "Medium Priority" : "Low Priority",
    count: counts[key],
    color: RISK_COLORS[key]
  }));
  let cursor = 0;
  const stops = segments
    .filter((segment) => segment.count > 0)
    .map((segment) => {
      const start = (cursor / total) * 360;
      cursor += segment.count;
      const end = (cursor / total) * 360;
      return `${segment.color} ${start}deg ${end}deg`;
    })
    .join(", ");
  return (
    <div className="donut-widget">
      <div className="donut-ring" style={{ background: `conic-gradient(${stops})` }}>
        <div className="donut-center">
          <strong>{total}</strong>
          <span>Total</span>
        </div>
      </div>
      <ul className="donut-legend">
        {segments.map((segment) => (
          <li key={segment.key}>
            <span className="legend-dot" style={{ background: segment.color }} />
            {segment.label}
            <b>{segment.count}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

const SCORE_BUCKETS = [
  { label: "0-20", min: 0, max: 20 },
  { label: "20-40", min: 20, max: 40 },
  { label: "40-60", min: 40, max: 60 },
  { label: "60-80", min: 60, max: 80 },
  { label: "80-100", min: 80, max: 100 }
];

function ScoreDistributionChart({ candidates }: { candidates: VesselScore[] }) {
  if (!candidates.length) {
    return <EmptyState title="No scores yet" text="Score distribution will appear once vessel candidates are scored." />;
  }
  const buckets = SCORE_BUCKETS.map((bucket) => ({
    ...bucket,
    count: candidates.filter((vessel) => vessel.score >= bucket.min && (bucket.max === 100 ? vessel.score <= bucket.max : vessel.score < bucket.max)).length
  }));
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1);
  return (
    <div className="trend-chart">
      {buckets.map((bucket) => (
        <div className="trend-bar" key={bucket.label}>
          <span className="trend-bar-count">{bucket.count}</span>
          <div className="trend-bar-track">
            <div className="trend-bar-fill" style={{ height: bucket.count ? `${Math.max(6, (bucket.count / max) * 100)}%` : "0%" }} />
          </div>
          <small>{bucket.label}</small>
        </div>
      ))}
    </div>
  );
}

function VesselTable({
  vessels,
  selected,
  onSelect
}: {
  vessels: VesselScore[];
  selected: VesselScore | null;
  onSelect: (vessel: VesselScore) => void;
}) {
  if (!vessels.length) {
    return <EmptyState title="No candidate vessels" text="The backend returned no vessel candidates for this investigation." />;
  }
  return (
    <div className="table-panel">
      <div className="vessel-row vessel-row-header">
        <span>Vessel</span>
        <span>MMSI</span>
        <span>Priority</span>
        <span>Last Seen</span>
        <span>Score</span>
      </div>
      {vessels.map((vessel) => (
        <button
          key={`${vessel.rank}-${vessel.mmsi}`}
          className={selected?.mmsi === vessel.mmsi ? "vessel-row selected" : "vessel-row"}
          onClick={() => onSelect(vessel)}
        >
          <strong>{vessel.vessel_name}</strong>
          <code>{vessel.mmsi}</code>
          <StatusPill label={vessel.priority ?? "unlabelled"} tone={vessel.priority === "high" ? "danger" : vessel.priority === "medium" ? "warn" : "muted"} />
          <span>{formatDate(vessel.nearest_approach_time)}</span>
          <span className="vessel-score-cell">
            <span className="mini-bar-track">
              <span className="mini-bar-fill" style={{ width: `${Math.min(100, Math.max(0, vessel.score))}%`, background: gaugeColor(vessel.score) }} />
            </span>
            <b style={{ color: gaugeColor(vessel.score) }}>{vessel.score.toFixed(1)}</b>
          </span>
        </button>
      ))}
    </div>
  );
}

function SystemStatus({ health, result, onRefresh }: { health: HealthResponse | null; result: PipelineResponse | null; onRefresh: () => void }) {
  return (
    <section className="page-grid">
      <div className="section-heading">
        <div>
          <h1>System Status</h1>
          <p>Read-only health and module status from the current backend session.</p>
        </div>
        <button className="secondary-button" onClick={onRefresh}>Refresh</button>
      </div>
      <div className="metric-grid">
        <Metric label="Backend API" value={health?.status ?? "checking"} />
        <Metric label="Database/PostGIS" value={health?.database?.status ?? "unknown"} />
        <Metric label="OpenDrift/OpenOil" value={health?.opendrift?.status ?? "unknown"} />
        <Metric label="Detection Module" value={result?.detection?.status ?? "ready endpoint"} />
        <Metric label="Pipeline" value={result?.status ?? "idle"} />
      </div>
      <Panel title="Scientific Labeling">
        <div className="notice-list">
          <p>Deep-SAR SOS metrics are validation metrics only, not operational field accuracy.</p>
          <p>Module A returns image-space segmentation; geographic spill seeds are explicitly supplied.</p>
          <p>Real drift uses Copernicus Marine currents and NOAA GFS wind with OpenDrift/OpenOil when the backend reports it available.</p>
          <p>Synthetic AIS demo candidates are not real-world vessel evidence.</p>
          <p>Candidate scores support investigation prioritization only.</p>
        </div>
      </Panel>
    </section>
  );
}

function VesselList({ vessels, selected, onSelect, compact = false }: { vessels: VesselScore[]; selected: VesselScore | null; onSelect: (vessel: VesselScore) => void; compact?: boolean }) {
  if (!vessels.length) {
    return <EmptyState title="No candidate vessels" text="The backend returned no vessel candidates for this investigation." />;
  }
  return (
    <div className={compact ? "vessel-list compact" : "vessel-list"}>
      {vessels.map((vessel) => (
        <button key={`${vessel.rank}-${vessel.mmsi}`} className={selected?.mmsi === vessel.mmsi ? "vessel-card selected" : "vessel-card"} onClick={() => onSelect(vessel)}>
          <div>
            <span>Rank {vessel.rank ?? "-"}</span>
            <strong>{vessel.vessel_name}</strong>
            <code>{vessel.mmsi}</code>
          </div>
          <div>
            <b style={{ color: gaugeColor(vessel.score) }}>{vessel.score.toFixed(1)}</b>
            <StatusPill label={vessel.priority ?? "priority"} tone={vessel.priority === "high" ? "danger" : vessel.priority === "medium" ? "warn" : "muted"} />
          </div>
        </button>
      ))}
    </div>
  );
}

function Provenance({ result }: { result: PipelineResponse | null }) {
  const provenance = result?.data_provenance;
  if (!provenance) {
    return <EmptyState title="No provenance yet" text="Run an investigation to see source labeling." />;
  }
  return (
    <div className="provenance-grid">
      {Object.entries(provenance).map(([key, value]) => (
        <div key={key}>
          <span>{key.replaceAll("_", " ")}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ComponentStatus({
  label,
  value,
  provenance,
  icon: Icon
}: {
  label: string;
  value: string;
  provenance: string;
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
}) {
  return (
    <div className="component-row">
      <div className="component-row-top">
        <div className="component-row-lead">
          {Icon && (
            <div className={`dash-icon-badge tone-${categorizeStatus(value)}`}>
              <Icon width={16} height={16} />
            </div>
          )}
          <strong>{label}</strong>
        </div>
        <StatusPill label={value} tone={value.includes("success") || value.includes("available") || value.includes("connected") ? "ok" : "muted"} />
      </div>
      <span className="component-row-provenance">{provenance}</span>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function StageList({ stages }: { stages: Record<string, StageState> }) {
  return (
    <div className="stage-list">
      {Object.entries(stages).map(([stage, state]) => (
        <div className={`stage-row stage-${state}`} key={stage}>
          <span>{stage}</span>
          <strong>{state}</strong>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

function initialStages(): Record<string, StageState> {
  return {
    "SAR Analysis": "idle",
    "Drift Reconstruction": "idle",
    "AIS Correlation": "idle",
    "Risk Scoring": "idle",
    Persistence: "idle"
  };
}

function markRunning(): Record<string, StageState> {
  return Object.fromEntries(Object.keys(initialStages()).map((key) => [key, "running"])) as Record<string, StageState>;
}

function markFailed(): Record<string, StageState> {
  return Object.fromEntries(Object.keys(initialStages()).map((key) => [key, "failed"])) as Record<string, StageState>;
}

function stagesFromPipeline(result: PipelineResponse): Record<string, StageState> {
  return {
    "SAR Analysis": result.detection.status === "success" ? "complete" : "failed",
    "Drift Reconstruction": result.drift?.status === "success" ? "complete" : result.failed_stage === "drift" ? "failed" : "idle",
    "AIS Correlation": result.attribution?.status === "success" ? "complete" : result.failed_stage === "attribution" ? "failed" : "idle",
    "Risk Scoring": result.attribution?.status === "success" ? "complete" : result.failed_stage === "attribution" ? "failed" : "idle",
    Persistence: result.persistence.status === "persisted" || result.persistence.status === "skipped" ? "complete" : "failed"
  };
}

function normalizeRequest(request: PipelineRequest): PipelineRequest {
  return {
    ...request,
    image_path: request.image_path || null,
    spill_seed: request.pipeline_mode === "detection_only" ? null : request.spill_seed
  };
}

function detailToPipeline(detail: IncidentDetail | null): PipelineResponse | null {
  if (!detail?.incident || detail.status !== "success") {
    return null;
  }
  return {
    status: String(detail.incident.status ?? "unknown"),
    incident_id: String(detail.incident.id ?? ""),
    scenario: String(detail.incident.scenario ?? "persisted"),
    data_provenance: (detail.incident.provenance as Record<string, string>) ?? {},
    detection: detail.detection ?? { status: "not_available" },
    drift: detail.drift ?? null,
    attribution: detail.vessel_candidates.length
      ? { status: "success", candidate_count: detail.vessel_candidates.length, suspects: detail.vessel_candidates }
      : null,
    summary: {
      spill_detected: detail.detection?.spill_detected ?? null,
      origin_centroid: detail.drift?.origin_centroid ?? null,
      candidate_vessels: detail.vessel_candidates.length,
      top_candidate: detail.vessel_candidates[0] ?? null
    },
    timings_ms: {},
    persistence: { status: "persisted" }
  };
}

function formatApiError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.kind === "network") {
      return `Backend unavailable: ${error.message}`;
    }
    if (error.status && error.status >= 500) {
      return `Pipeline failed: ${error.message}`;
    }
    return `Request rejected: ${error.message}`;
  }
  return error instanceof Error ? error.message : "Unexpected frontend error.";
}

function formatPipelineStatus(response: PipelineResponse): string {
  if (response.failed_stage === "detection") {
    return `Pipeline failed: ${response.message ?? "detection input image could not be loaded."}`;
  }
  return `Pipeline ${response.status}: ${response.message ?? "Review stage details."}`;
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "not available";
  }
  return new Date(value).toLocaleString();
}

function formatCoordinate(value?: { latitude: number; longitude: number } | null): string {
  if (!value) {
    return "not available";
  }
  return `${value.latitude.toFixed(6)}, ${value.longitude.toFixed(6)}`;
}

function formatWindow(value?: { start: string; end: string } | null): string {
  if (!value) {
    return "not available";
  }
  return `${formatDate(value.start)} - ${formatDate(value.end)}`;
}

function formatKm(value?: number | null): string {
  return value == null ? "not available" : `${value.toFixed(2)} km`;
}

function formatPercent(value?: number | null): string {
  return value == null ? "not available" : `${(value * 100).toFixed(1)}%`;
}

function formatPixels(value?: number | null): string {
  return value == null ? "not available" : `${Math.round(value).toLocaleString()} px`;
}

function gaugeColor(score: number): string {
  if (score >= 70) {
    return "#f87171";
  }
  if (score >= 40) {
    return "#fbbf24";
  }
  return "#5eead4";
}

function gaugeStyle(score: number): CSSProperties {
  const pct = Math.max(0, Math.min(100, score));
  return {
    "--pct": pct,
    "--gauge-color": gaugeColor(score)
  } as CSSProperties;
}

export default App;
