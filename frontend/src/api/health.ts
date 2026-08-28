import { requestJson } from "./client";
import type { HealthResponse } from "./types";

export function getHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/health");
}
