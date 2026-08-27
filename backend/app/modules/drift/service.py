from app.core.config import settings
from app.modules.drift.engine import DevelopmentDriftEngine, InsufficientParticlesError
from app.modules.drift.environmental import EnvironmentDataError, RealDataEnvironmentProvider
from app.modules.drift.synthetic_environment import SyntheticDevelopmentEnvironment
from app.schemas.drift import DriftRequest, DriftResponse


def estimate_drift(request: DriftRequest) -> DriftResponse:
    mode = request.mode or request.environment_mode or settings.drift_environment_mode
    backward_hours = request.backward_hours or settings.drift_backward_hours
    forward_hours = request.forward_hours or settings.drift_forward_hours
    particle_count = request.particle_count or settings.drift_particle_count

    if mode == "real_data":
        provider = RealDataEnvironmentProvider(
            current_path=settings.drift_current_data_path or settings.drift_environment_data_path,
            wind_glob=settings.drift_wind_data_glob,
            max_nearest_current_distance_km=settings.drift_max_nearest_current_distance_km,
        )
        if not provider.is_ready():
            return DriftResponse(
                status="environment_data_not_ready",
                mode="real_data",
                environment="real",
                engine="development_drift_engine",
                input=request,
                message="Real environmental NetCDF/GRIB files are not configured or available.",
            )
        try:
            input_forcing = provider.get_forcing(request.latitude, request.longitude, request.timestamp)
        except EnvironmentDataError as exc:
            return DriftResponse(
                status="environment_data_not_ready",
                mode="real_data",
                environment="real",
                engine="development_drift_engine",
                input=request,
                message=str(exc),
            )
    else:
        provider = SyntheticDevelopmentEnvironment()
        input_forcing = None

    engine = DevelopmentDriftEngine(
        provider,
        windage_factor=settings.drift_windage_factor,
        random_seed=settings.drift_random_seed,
    )
    try:
        result = engine.simulate(
            latitude=request.latitude,
            longitude=request.longitude,
            timestamp=request.timestamp,
            backward_hours=backward_hours,
            forward_hours=forward_hours,
            particle_count=particle_count,
        )
    except EnvironmentDataError as exc:
        return DriftResponse(
            status="environment_data_not_ready",
            mode="real_data",
            environment="real",
            engine="development_drift_engine",
            input=request,
            message=str(exc),
        )
    except InsufficientParticlesError as exc:
        return DriftResponse(
            status="insufficient_particles",
            mode=mode,
            environment="real" if mode == "real_data" else "synthetic",
            engine="development_drift_engine",
            input=request,
            metadata=exc.metadata,
            message=str(exc),
        )

    return DriftResponse(
        status="success",
        mode=mode,
        environment="real" if mode == "real_data" else "synthetic",
        engine=result.engine,
        input=request,
        origin=result.origin_centroid,
        origin_centroid=result.origin_centroid,
        origin_area=result.origin_area,
        origin_time_window=result.origin_time_window,
        backward_path=result.backward_path,
        forward_path=result.forward_path,
        metadata=result.metadata,
        environmental_forcing={
            "current_u_mps": input_forcing.current_u_mps,
            "current_v_mps": input_forcing.current_v_mps,
            "wind_u_mps": input_forcing.wind_u_mps,
            "wind_v_mps": input_forcing.wind_v_mps,
            "source_metadata": input_forcing.source_metadata,
        }
        if input_forcing is not None
        else None,
        message=(
            "Synthetic development drift engine; not scientific environmental forcing."
            if mode == "synthetic_dev"
            else "Development drift engine consuming real environmental vectors; not OpenDrift/OpenOil."
        ),
    )
