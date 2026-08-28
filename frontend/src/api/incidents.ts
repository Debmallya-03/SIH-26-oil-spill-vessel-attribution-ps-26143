import { requestJson } from "./client";
import type { IncidentDetail, IncidentListResponse, VesselCandidatesResponse } from "./types";

export function listIncidents(): Promise<IncidentListResponse> {
  return requestJson<IncidentListResponse>("/incidents");
}

export function getIncident(incidentId: string): Promise<IncidentDetail> {
  return requestJson<IncidentDetail>(`/incidents/${incidentId}`);
}

export function getIncidentVessels(incidentId: string): Promise<VesselCandidatesResponse> {
  return requestJson<VesselCandidatesResponse>(`/incidents/${incidentId}/vessels`);
}
