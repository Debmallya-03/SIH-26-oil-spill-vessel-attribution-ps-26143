export type PipelineMode = "detection_only" | "demo" | "real_validation";
export type DataMode = "synthetic_dev" | "real_data";
export type DriftEngine = "development_drift_engine" | "opendrift_openoil";
export type DriftForcingStrategy = "native_grid" | "constant_sample";

export interface GeoCoordinate {
  latitude: number;
  longitude: number;
}

export interface ImageCoordinate {
  x: number;
  y: number;
}

export interface OriginWindow {
  start: string;
  end: string;
}

export interface LineStringGeometry {
  type: "LineString";
  coordinates: number[][];
}

export interface PolygonGeometry {
  type: "Polygon";
  coordinates: number[][][];
}

export interface DetectionResponse {
  status: string;
  spill_detected?: boolean | null;
  spill_id?: string | null;
  detected_at?: string | null;
  area_pixels?: number | null;
  perimeter_pixels?: number | null;
  centroid?: ImageCoordinate | null;
  polygon?: PolygonGeometry | null;
  confidence?: number | null;
  model?: string | null;
  model_checkpoint?: string | null;
  model_dataset_type?: string | null;
  image_size?: number | null;
  message?: string | null;
}

export interface DriftMetadata {
  backward_hours: number;
  forward_hours: number;
  particle_count: number;
  time_step_minutes: number;
  windage_factor: number;
  backward_path_direction?: string;
  forward_path_direction?: string;
  particles_requested?: number | null;
  backward_particles_active?: number | null;
  backward_particles_beached?: number | null;
  forward_particles_active?: number | null;
  forward_particles_beached?: number | null;
  nearest_current_substitution_count?: number | null;
  nearest_current_substitutions?: Record<string, unknown>[];
  max_nearest_current_distance_km?: number | null;
  max_actual_substitution_distance_km?: number | null;
}

export interface DriftResponse {
  status: string;
  mode?: string | null;
  environment?: string | null;
  engine?: string | null;
  input?: Record<string, unknown> | null;
  origin?: GeoCoordinate | null;
  origin_centroid?: GeoCoordinate | null;
  origin_area?: PolygonGeometry | null;
  origin_time_window?: OriginWindow | null;
  backward_path?: LineStringGeometry | null;
  forward_path?: LineStringGeometry | null;
  metadata?: DriftMetadata | null;
  environmental_forcing?: Record<string, unknown> | null;
  message?: string | null;
}

export interface VesselScoreFactors {
  proximity: number;
  temporal_proximity: number;
  trajectory_alignment: number;
  speed_anomaly: number;
  course_anomaly: number;
  ais_gap: number;
}

export interface VesselScore {
  rank?: number | null;
  mmsi: string;
  vessel_name: string;
  score: number;
  priority?: string | null;
  minimum_distance_km?: number | null;
  nearest_approach_time?: string | null;
  factors: VesselScoreFactors;
  reasons: string[];
}

export interface ScoreResponse {
  status: string;
  mode?: string | null;
  environment?: string | null;
  scenario?: string | null;
  candidate_count?: number | null;
  temporal_filter?: Record<string, unknown> | null;
  spatial_filter?: Record<string, unknown> | null;
  suspects: VesselScore[];
  message?: string | null;
}

export interface SpillSeed {
  latitude: number;
  longitude: number;
  timestamp: string;
}

export interface PipelineRequest {
  pipeline_mode: PipelineMode;
  image_path?: string | null;
  spill_seed?: SpillSeed | null;
  detection_mode?: "deep_sar_sos" | "synthetic_dev" | null;
  drift_mode: DataMode;
  drift_engine?: DriftEngine | null;
  drift_forcing_strategy?: DriftForcingStrategy | null;
  attribution_mode: DataMode;
  persist: boolean;
}

export interface PipelineSummary {
  spill_detected?: boolean | null;
  origin_centroid?: GeoCoordinate | null;
  candidate_vessels?: number | null;
  top_candidate?: VesselScore | null;
}

export interface PersistenceStatus {
  status: string;
  reason?: string | null;
}

export interface PipelineResponse {
  status: string;
  incident_id: string;
  scenario: string;
  data_provenance: Record<string, string>;
  detection: DetectionResponse;
  drift?: DriftResponse | null;
  attribution?: ScoreResponse | null;
  summary: PipelineSummary;
  timings_ms: Record<string, number>;
  persistence: PersistenceStatus;
  failed_stage?: string | null;
  message?: string | null;
}

export interface HealthResponse {
  status: string;
  service: string;
  problem_statement: string;
  version: string;
  database?: {
    status: string;
    message?: string | null;
  };
  opendrift?: {
    status: string;
    engine?: string | null;
    model?: string | null;
    version?: string | null;
    message?: string | null;
  };
}

export interface IncidentSummary {
  incident_id: string;
  created_at?: string | null;
  scenario?: string | null;
  status?: string | null;
  pipeline_mode?: string | null;
  provenance?: Record<string, unknown> | null;
}

export interface IncidentListResponse {
  status: string;
  incidents: IncidentSummary[];
  message?: string | null;
}

export interface IncidentDetail {
  status: string;
  incident?: Record<string, unknown> | null;
  detection?: DetectionResponse | null;
  drift?: DriftResponse | null;
  vessel_candidates: VesselScore[];
  message?: string | null;
}

export interface VesselCandidatesResponse {
  status: string;
  incident_id: string;
  vessels: VesselScore[];
  message?: string | null;
}
