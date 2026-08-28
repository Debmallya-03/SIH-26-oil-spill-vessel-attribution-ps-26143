from app.modules.pipeline.orchestrator import run_pipeline
from app.schemas.pipeline import PipelineRequest, PipelineResponse


def execute_pipeline(request: PipelineRequest | None = None) -> PipelineResponse:
    return run_pipeline(request)

