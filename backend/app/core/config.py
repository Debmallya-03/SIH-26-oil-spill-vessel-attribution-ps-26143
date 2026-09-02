from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Marine Oil Spill Intelligence API"
    app_version: str = "0.1.0"
    database_url: str | None = None
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str | None = None
    database_user: str | None = None
    database_password: str | None = None
    database_connect_timeout_seconds: int = 2
    frontend_origin: str = "http://localhost:5173"
    detection_model_path: str = "models/unet-deep-sar-sos.pth"
    drift_environment_mode: str = "synthetic_dev"
    drift_engine: str = "development_drift_engine"
    drift_backward_hours: int = 6
    drift_forward_hours: int = 6
    drift_particle_count: int = 100
    drift_random_seed: int = 42
    drift_windage_factor: float = 0.03
    drift_max_nearest_current_distance_km: float = 10.0
    drift_environment_data_path: str | None = None
    drift_current_data_path: str = "../data/ocean/currents/cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_1787833203663.nc"
    drift_wind_data_glob: str = "../data/ocean/wind/gfs.t06z.pgrb2.0p25.f*"
    opendrift_backward_hours: int = 6
    opendrift_forward_hours: int = 6
    opendrift_particle_count: int = 100
    opendrift_time_step_minutes: int = 60
    opendrift_seed_radius_meters: float = 100.0
    opendrift_forcing_strategy: str = "native_grid"
    ais_mode: str = "synthetic_dev"
    ais_data_path: str | None = None
    ais_candidate_radius_km: float = 25.0
    ais_time_buffer_hours: float = 2.0
    ais_gap_threshold_minutes: float = 15.0
    ais_max_real_records: int = 20000

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_database_url(self) -> str:
        if self.database_url and not self._is_placeholder_database_url(self.database_url):
            return self.database_url
        if not self.database_name or not self.database_user or not self.database_password:
            raise ValueError("DATABASE_NAME, DATABASE_USER, and DATABASE_PASSWORD are required.")
        user = quote(self.database_user, safe="")
        password = quote(self.database_password, safe="")
        return f"postgresql://{user}:{password}@{self.database_host}:{self.database_port}/{self.database_name}"

    @property
    def database_target(self) -> dict[str, str | int | None]:
        return {
            "host": self.database_host,
            "port": self.database_port,
            "database": self.database_name,
            "user": self.database_user,
        }

    @staticmethod
    def _is_placeholder_database_url(value: str) -> bool:
        return "USER:PASSWORD" in value or value.endswith("/DATABASE")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
