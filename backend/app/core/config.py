from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Marine Oil Spill Intelligence API"
    app_version: str = "0.1.0"
    database_url: str = "postgresql://USER:PASSWORD@localhost:5432/DATABASE"
    frontend_origin: str = "http://localhost:5173"
    detection_model_path: str = "backend/models/unet-baseline.pth"
    drift_environment_mode: str = "synthetic_dev"
    drift_backward_hours: int = 6
    drift_forward_hours: int = 6
    drift_particle_count: int = 100
    drift_random_seed: int = 42
    drift_windage_factor: float = 0.03
    drift_max_nearest_current_distance_km: float = 10.0
    drift_environment_data_path: str | None = None
    drift_current_data_path: str = "../data/ocean/currents/cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_1787833203663.nc"
    drift_wind_data_glob: str = "../data/ocean/wind/gfs.t06z.pgrb2.0p25.f*"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
