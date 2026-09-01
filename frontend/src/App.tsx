import { useEffect, useMemo, useState } from "react";
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
  VesselScore
} from "./api/types";
import { FactorBars } from "./components/FactorBars";
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
  image_path: "../data/synthetic_sar/images/sar_001.png",
  spill_seed: DEMO_SEED,
  detection_mode: "synthetic_dev",
  drift_mode: "real_data",
  drift_engine: "development_drift_engine",
  drift_forcing_strategy: "native_grid",
  attribution_mode: "synthetic_dev",
  persist: true
};

const EMPTY_REQUEST: PipelineRequest = {
  pipeline_mode: "demo",
  image_path: "",
  spill_seed: DEMO_SEED,
  detection_mode: "synthetic_dev",
  drift_mode: "real_data",
  drift_engine: "development_drift_engine",
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
      }
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
        <div>
          <div className="brand-row">
            <span className="brand-mark">MARIS</span>
            <span className="brand-subtitle">AI Marine Spill Intelligence</span>
          </div>
          <p>PS 26143 visual investigation dashboard</p>
        </div>
        <div className="topbar-status">
          <StatusPill label={`API ${health?.status ?? "checking"}`} tone={health?.status === "healthy" ? "ok" : "warn"} />
          <StatusPill label={`PostGIS ${health?.database?.status ?? "unknown"}`} tone={health?.database?.status === "connected" ? "ok" : "warn"} />
          <StatusPill label={activeResult?.status ? `Investigation ${activeResult.status}` : "No active run"} tone={activeResult?.status === "completed" ? "ok" : activeResult ? "warn" : "muted"} />
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          {NAV.map(([key, label]) => (
            <button key={key} className={page === key ? "nav-active" : ""} onClick={() => setPage(key)}>
              {label}
            </button>
          ))}
          <button className="demo-button" onClick={loadDemoScenario}>Load Demo Scenario</button>
          <div className="api-box">
            <span>Backend</span>
            <code>{API_BASE_URL}</code>
          </div>
        </aside>

        <main className="content">
          {error && <div className="alert-banner">{error}</div>}
          {page === "overview" && (
            <Overview
              health={health}
              incidentCount={incidents.length}
              completedCount={completedCount}
              latest={incidents[0]}
              result={activeResult}
              onRefresh={refreshSystem}
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
              filter={incidentFilter}
              setFilter={setIncidentFilter}
              onOpen={openIncident}
              onRefresh={refreshSystem}
            />
          )}
          {page === "vessels" && (
            <VesselIntelligence candidates={candidates} selected={selectedVessel} setSelected={setSelectedVessel} />
          )}
          {page === "status" && <SystemStatus health={health} result={activeResult} onRefresh={refreshSystem} />}
        </main>
      </div>
    </div>
  );
}

function Overview({
  health,
  incidentCount,
  completedCount,
  latest,
  result,
  onRefresh
}: {
  health: HealthResponse | null;
  incidentCount: number;
  completedCount: number;
  latest?: IncidentSummary;
  result: PipelineResponse | null;
  onRefresh: () => void;
}) {
  return (
    <section className="page-grid">
      <div className="section-heading">
        <div>
          <h1>Maritime Intelligence Overview</h1>
          <p>Backend-derived operational view for the current SIH development system.</p>
        </div>
        <button className="secondary-button" onClick={onRefresh}>Refresh</button>
      </div>
      <div className="metric-grid">
        <Metric label="Stored Incidents" value={incidentCount} />
        <Metric label="Completed Investigations" value={completedCount} />
        <Metric label="Backend API" value={health?.status ?? "checking"} />
        <Metric label="PostGIS" value={health?.database?.status ?? "unknown"} />
      </div>
      <div className="two-column">
        <Panel title="System Components">
          <ComponentStatus label="SAR Detection" value={result?.detection?.status ?? "available via /detect"} provenance="Synthetic development checkpoint when demo pipeline is used" />
          <ComponentStatus label="Ocean Drift Engine" value={result?.drift?.engine ?? "development_drift_engine"} provenance="Copernicus Marine + NOAA GFS in real_data mode" />
          <ComponentStatus label="AIS Attribution" value={result?.attribution?.status ?? "available via /score"} provenance={result?.data_provenance?.ais ?? "synthetic_dev or real_ais"} />
          <ComponentStatus label="PostGIS" value={health?.database?.status ?? "unknown"} provenance="Optional Day-5 persistence" />
        </Panel>
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
        </Panel>
      </div>
    </section>
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
          <button className="primary-button" onClick={onSubmit} disabled={loading}>{loading ? "Running Investigation" : "Run Investigation"}</button>
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
              <span>Estimated origin</span><strong>{formatCoordinate(result.drift?.origin_centroid)}</strong>
              <span>Origin window</span><strong>{formatWindow(result.drift?.origin_time_window)}</strong>
              <span>Candidates</span><strong>{result.summary.candidate_vessels ?? candidates.length}</strong>
              <span>Top candidate</span><strong>{result.summary.top_candidate?.vessel_name ?? "None"}</strong>
            </div>
          ) : (
            <EmptyState title="No active investigation" text="Run the demo scenario or open a persisted incident." />
          )}
        </Panel>
        <Panel title="Provenance">
          <Provenance result={result} />
        </Panel>
        <Panel title="Ranked Candidates">
          <VesselList vessels={candidates} selected={selectedVessel} onSelect={setSelectedVessel} compact />
        </Panel>
      </aside>
    </section>
  );
}

function Incidents({
  incidents,
  filter,
  setFilter,
  onOpen,
  onRefresh
}: {
  incidents: IncidentSummary[];
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
        {incidents.length ? incidents.map((incident) => (
          <button className="incident-row" key={incident.incident_id} onClick={() => onOpen(incident.incident_id)}>
            <code>{incident.incident_id}</code>
            <span>{formatDate(incident.created_at)}</span>
            <strong>{incident.scenario ?? "unknown"}</strong>
            <StatusPill label={incident.status ?? "unknown"} tone={incident.status === "completed" ? "ok" : "warn"} />
            <span>{incident.pipeline_mode ?? "not recorded"}</span>
          </button>
        )) : <EmptyState title="No incidents available" text="PostGIS may be empty or unavailable." />}
      </div>
    </section>
  );
}

function VesselIntelligence({
  candidates,
  selected,
  setSelected
}: {
  candidates: VesselScore[];
  selected: VesselScore | null;
  setSelected: (vessel: VesselScore) => void;
}) {
  const active = selected ?? candidates[0] ?? null;
  return (
    <section className="analysis-grid">
      <Panel title="Candidate Vessels">
        <VesselList vessels={candidates} selected={active} onSelect={setSelected} />
      </Panel>
      <Panel title="Explainable Attribution">
        {active ? (
          <div className="vessel-detail">
            <div className="vessel-hero">
              <div>
                <h2>{active.vessel_name}</h2>
                <code>{active.mmsi}</code>
              </div>
              <div className="score-gauge">{active.score.toFixed(1)}</div>
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
    </section>
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
        <Metric label="Detection Module" value={result?.detection?.status ?? "ready endpoint"} />
        <Metric label="Pipeline" value={result?.status ?? "idle"} />
      </div>
      <Panel title="Scientific Labeling">
        <div className="notice-list">
          <p>Module A synthetic checkpoint metrics are development only.</p>
          <p>Real drift uses Copernicus Marine currents and NOAA GFS wind with the development drift engine, not OpenDrift/OpenOil.</p>
          <p>Synthetic AIS demo tracks are not real-world evidence.</p>
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
            <b>{vessel.score.toFixed(1)}</b>
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

function ComponentStatus({ label, value, provenance }: { label: string; value: string; provenance: string }) {
  return (
    <div className="component-row">
      <div>
        <strong>{label}</strong>
        <span>{provenance}</span>
      </div>
      <StatusPill label={value} tone={value.includes("success") || value.includes("available") || value.includes("connected") ? "ok" : "muted"} />
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

export default App;
