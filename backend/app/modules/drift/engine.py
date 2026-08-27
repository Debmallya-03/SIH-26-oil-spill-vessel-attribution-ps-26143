from dataclasses import dataclass
from datetime import datetime, timedelta
import random

from app.modules.drift.environmental import CurrentUnavailableError, EnvironmentalProvider
from app.modules.drift.geometry import (
    line_string_from_coordinates,
    move_coordinate,
    origin_polygon_from_particles,
    particle_centroid,
    validate_coordinate,
)
from app.schemas.detection import GeoCoordinate
from app.schemas.drift import DriftMetadata, LineStringGeometry, OriginWindow, PolygonGeometry


@dataclass(frozen=True)
class DriftSimulationResult:
    engine: str
    origin_centroid: GeoCoordinate
    origin_area: PolygonGeometry
    origin_time_window: OriginWindow
    backward_path: LineStringGeometry
    forward_path: LineStringGeometry
    metadata: DriftMetadata


@dataclass(frozen=True)
class IntegrationResult:
    particles: list[tuple[float, float]]
    centroids: list[GeoCoordinate]
    active_count: int
    beached_count: int
    substitutions: list[dict[str, object]]


class InsufficientParticlesError(RuntimeError):
    def __init__(self, message: str, metadata: DriftMetadata) -> None:
        super().__init__(message)
        self.metadata = metadata


class DevelopmentDriftEngine:
    name = "development_drift_engine"

    def __init__(
        self,
        environment: EnvironmentalProvider,
        windage_factor: float = 0.03,
        random_seed: int = 42,
        time_step_minutes: int = 60,
    ) -> None:
        self.environment = environment
        self.windage_factor = windage_factor
        self.random_seed = random_seed
        self.time_step_minutes = time_step_minutes

    def simulate(
        self,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        backward_hours: int,
        forward_hours: int,
        particle_count: int,
    ) -> DriftSimulationResult:
        validate_coordinate(latitude, longitude)
        initial_particles = self._initial_particles(latitude, longitude, particle_count)

        backward_result = self._integrate(
            initial_particles,
            timestamp,
            initial_latitude=latitude,
            initial_longitude=longitude,
            hours=backward_hours,
            direction=-1,
        )
        forward_result = self._integrate(
            initial_particles,
            timestamp,
            initial_latitude=latitude,
            initial_longitude=longitude,
            hours=forward_hours,
            direction=1,
        )

        substitutions = backward_result.substitutions + forward_result.substitutions
        max_actual_distance = max(
            (float(item["distance_km"]) for item in substitutions),
            default=0.0,
        )
        metadata = DriftMetadata(
            backward_hours=backward_hours,
            forward_hours=forward_hours,
            particle_count=particle_count,
            time_step_minutes=self.time_step_minutes,
            windage_factor=self.windage_factor,
            particles_requested=particle_count,
            backward_particles_active=backward_result.active_count,
            backward_particles_beached=backward_result.beached_count,
            forward_particles_active=forward_result.active_count,
            forward_particles_beached=forward_result.beached_count,
            nearest_current_substitution_count=len(substitutions),
            nearest_current_substitutions=substitutions,
            max_nearest_current_distance_km=getattr(self.environment, "max_nearest_current_distance_km", None),
            max_actual_substitution_distance_km=max_actual_distance,
        )
        if len(backward_result.particles) < 3:
            raise InsufficientParticlesError(
                "Too few active backward particles survived to produce an origin polygon.",
                metadata,
            )

        origin_centroid = particle_centroid(backward_result.particles)
        endpoint_time = timestamp - timedelta(hours=backward_hours)
        return DriftSimulationResult(
            engine=self.name,
            origin_centroid=origin_centroid,
            origin_area=origin_polygon_from_particles(backward_result.particles),
            origin_time_window=OriginWindow(
                start=endpoint_time - timedelta(hours=1),
                end=endpoint_time + timedelta(hours=1),
            ),
            backward_path=line_string_from_coordinates(backward_result.centroids),
            forward_path=line_string_from_coordinates(forward_result.centroids),
            metadata=metadata,
        )

    def _initial_particles(self, latitude: float, longitude: float, particle_count: int) -> list[tuple[float, float]]:
        rng = random.Random(self.random_seed)
        particles: list[tuple[float, float]] = []
        for _ in range(particle_count):
            east_jitter = rng.gauss(0.0, 35.0)
            north_jitter = rng.gauss(0.0, 35.0)
            particles.append(move_coordinate(latitude, longitude, east_jitter, north_jitter))
        return particles

    def _integrate(
        self,
        particles: list[tuple[float, float]],
        timestamp: datetime,
        initial_latitude: float,
        initial_longitude: float,
        hours: int,
        direction: int,
    ) -> IntegrationResult:
        rng = random.Random(self.random_seed + (1000 if direction > 0 else 2000))
        current_particles = list(particles)
        centroids = [GeoCoordinate(latitude=initial_latitude, longitude=initial_longitude)]
        beached_count = 0
        substitutions: list[dict[str, object]] = []
        steps = int((hours * 60) / self.time_step_minutes)
        step_seconds = self.time_step_minutes * 60

        for step in range(steps):
            step_time = timestamp + timedelta(minutes=direction * self.time_step_minutes * step)
            next_particles: list[tuple[float, float]] = []
            for latitude, longitude in current_particles:
                try:
                    forcing = self.environment.get_forcing(latitude, longitude, step_time)
                except CurrentUnavailableError:
                    beached_count += 1
                    continue

                substitution = (forcing.source_metadata or {}).get("current", {}).get("nearest_current_substitution")
                if substitution:
                    substitutions.append(
                        {
                            **substitution,
                            "simulation_direction": "forward" if direction > 0 else "backward",
                            "step_time": step_time.isoformat(),
                        }
                    )
                u_mps = forcing.current_u_mps + self.windage_factor * forcing.wind_u_mps + rng.gauss(0.0, 0.012)
                v_mps = forcing.current_v_mps + self.windage_factor * forcing.wind_v_mps + rng.gauss(0.0, 0.012)
                next_particles.append(
                    move_coordinate(
                        latitude,
                        longitude,
                        direction * u_mps * step_seconds,
                        direction * v_mps * step_seconds,
                    )
                )
            current_particles = next_particles
            if not current_particles:
                break
            centroids.append(particle_centroid(current_particles))

        return IntegrationResult(
            particles=current_particles,
            centroids=centroids,
            active_count=len(current_particles),
            beached_count=beached_count,
            substitutions=substitutions,
        )
