from app.core.config import settings
from app.modules.drift.engine import DevelopmentDriftEngine, InsufficientParticlesError
from app.modules.drift.environmental import EnvironmentDataError, RealDataEnvironmentProvider
from app.modules.drift.opendrift_engine import FORCING_NATIVE_GRID, OpenDriftOpenOilEngine, OpenDriftUnavailableError
from app.modules.drift.synthetic_environment import SyntheticDevelopmentEnvironment
from app.schemas.drift import DriftRequest, DriftResponse


def estimate_drift(request: DriftRequest) -> DriftResponse:
    mode = request.mode or request.environment_mode or settings.drift_environment_mode
    engine_name = request.engine or settings.drift_engine
    forcing_strategy = request.forcing_strategy or settings.opendrift_forcing_strategy
    if engine_name == "opendrift_openoil":
        backward_hours = request.backward_hours or settings.opendrift_backward_hours
        forward_hours = request.forward_hours or settings.opendrift_forward_hours
        particle_count = request.particle_count or settings.opendrift_particle_count
    else:
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
                engine=engine_name,
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
                engine=engine_name,
                input=request,
                message=str(exc),
            )
    else:
        provider = SyntheticDevelopmentEnvironment()
        input_forcing = None

    if engine_name == "opendrift_openoil":
        if mode != "real_data" or input_forcing is None:
            return DriftResponse(
                status="environment_data_not_ready",
                mode=mode,
                environment="synthetic" if mode == "synthetic_dev" else "real",
                engine="opendrift_openoil",
                input=request,
                message="OpenDrift/OpenOil integration currently requires mode=real_data with configured environmental files.",
            )
        engine = OpenDriftOpenOilEngine(
            time_step_minutes=settings.opendrift_time_step_minutes,
            seed_radius_meters=settings.opendrift_seed_radius_meters,
            forcing_strategy=forcing_strategy,
            current_path=provider.current_path,
            wind_files=provider.wind_files,
        )
        try:
            result = engine.simulate(
                latitude=request.latitude,
                longitude=request.longitude,
                timestamp=request.timestamp,
                backward_hours=backward_hours,
                forward_hours=forward_hours,
                particle_count=particle_count,
                forcing=input_forcing,
            )
        except OpenDriftUnavailableError as exc:
            return DriftResponse(
                status="opendrift_not_available",
                mode=mode,
                environment="real",
                engine="opendrift_openoil",
                input=request,
                message=str(exc),
            )
        except EnvironmentDataError as exc:
            return DriftResponse(
                status="environment_data_not_ready",
                mode=mode,
                environment="real",
                engine="opendrift_openoil",
                input=request,
                message=str(exc),
            )
        except InsufficientParticlesError as exc:
            return DriftResponse(
                status="insufficient_particles",
                mode=mode,
                environment="real",
                engine="opendrift_openoil",
                input=request,
                metadata=exc.metadata,
                message=str(exc),
            )
        return _success_response(
            request=request,
            result=result,
            mode=mode,
            input_forcing=input_forcing,
            message=(
                "OpenDrift/OpenOil engine using native gridded Copernicus/GFS readers. "
                "This is a development integration step, not scientific validation."
                if forcing_strategy == FORCING_NATIVE_GRID
                else "OpenDrift/OpenOil engine using constant forcing sampled from real Copernicus/GFS data at the "
                "detection point/time. This is an integration step, not scientific validation."
            ),
        )

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
            engine=engine_name,
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

    return _success_response(
        request=request,
        result=result,
        mode=mode,
        input_forcing=input_forcing,
        message=(
            "Synthetic development drift engine; not scientific environmental forcing."
            if mode == "synthetic_dev"
            else "Development drift engine consuming real environmental vectors; not OpenDrift/OpenOil."
        ),
    )


def _success_response(
    *,
    request: DriftRequest,
    result,
    mode: str,
    input_forcing,
    message: str,
) -> DriftResponse:
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
        message=message,
    )
