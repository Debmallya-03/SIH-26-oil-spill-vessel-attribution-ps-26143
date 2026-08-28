import { requestJson } from "./client";
import type { PipelineRequest, PipelineResponse } from "./types";

export function runPipeline(payload: PipelineRequest): Promise<PipelineResponse> {
  return requestJson<PipelineResponse>("/pipeline", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
