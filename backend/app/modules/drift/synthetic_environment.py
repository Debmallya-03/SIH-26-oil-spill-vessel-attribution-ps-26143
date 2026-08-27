from datetime import datetime

from app.modules.drift.environmental import EnvironmentalForcing


class SyntheticDevelopmentEnvironment:
    mode = "synthetic_dev"

    def __init__(
        self,
        current_u_mps: float = 0.18,
        current_v_mps: float = 0.07,
        wind_u_mps: float = 2.0,
        wind_v_mps: float = 1.0,
    ) -> None:
        self.forcing = EnvironmentalForcing(
            current_u_mps=current_u_mps,
            current_v_mps=current_v_mps,
            wind_u_mps=wind_u_mps,
            wind_v_mps=wind_v_mps,
        )

    def get_forcing(self, latitude: float, longitude: float, timestamp: datetime) -> EnvironmentalForcing:
        return self.forcing
