from datetime import UTC, datetime, timedelta

from app.modules.attribution.ais_loader import AISRecord

ORIGIN_LATITUDE = 18.522014161747748
ORIGIN_LONGITUDE = 72.78917658819358
START_TIME = datetime(2026, 8, 26, 3, 0, tzinfo=UTC)
END_TIME = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)
INTERVAL_MINUTES = 10


def generate_synthetic_ais_records() -> list[AISRecord]:
    records: list[AISRecord] = []
    records.extend(_linear_track("419000001", "Demo Vessel Alpha", -0.08, 0.0, 0.08, 0.0, 12.0, 90.0))
    records.extend(_linear_track("419000002", "Demo Vessel Bravo", -0.055, -0.015, 0.055, 0.015, 11.0, 74.0, slow_near_origin=True))
    records.extend(_linear_track("419000003", "Demo Vessel Charlie", 0.02, -0.07, 0.02, 0.07, 10.5, 0.0, course_change=True))
    records.extend(_linear_track("419000004", "Demo Vessel Delta", -0.06, 0.025, 0.06, -0.025, 9.5, 110.0, gap_near_origin=True))
    records.extend(_linear_track("419000005", "Demo Vessel Echo", -0.20, 0.18, 0.10, 0.18, 13.0, 90.0))
    records.extend(_linear_track("419000006", "Demo Vessel Foxtrot", 0.17, -0.15, 0.17, 0.10, 8.0, 0.0))
    records.extend(_linear_track("419000007", "Demo Vessel Gulf", -0.24, -0.08, -0.18, 0.08, 14.0, 25.0))
    records.extend(_linear_track("419000008", "Demo Vessel Harbor", 0.10, 0.12, 0.22, 0.12, 7.5, 90.0))
    records.extend(_linear_track("419000009", "Demo Vessel India", -0.15, -0.13, -0.02, -0.13, 12.5, 90.0))
    records.extend(_linear_track("419000010", "Demo Vessel Juliet", 0.12, -0.18, 0.24, -0.05, 11.5, 43.0))
    return sorted(records, key=lambda record: (record.mmsi, record.timestamp))


def _linear_track(
    mmsi: str,
    vessel_name: str,
    start_lon_offset: float,
    start_lat_offset: float,
    end_lon_offset: float,
    end_lat_offset: float,
    sog: float,
    cog: float,
    slow_near_origin: bool = False,
    course_change: bool = False,
    gap_near_origin: bool = False,
) -> list[AISRecord]:
    steps = int((END_TIME - START_TIME).total_seconds() / 60 / INTERVAL_MINUTES)
    records: list[AISRecord] = []
    for index in range(steps + 1):
        timestamp = START_TIME + timedelta(minutes=index * INTERVAL_MINUTES)
        if gap_near_origin and datetime(2026, 8, 26, 5, 50, tzinfo=UTC) <= timestamp <= datetime(2026, 8, 26, 6, 20, tzinfo=UTC):
            continue

        fraction = index / steps
        latitude = ORIGIN_LATITUDE + start_lat_offset + (end_lat_offset - start_lat_offset) * fraction
        longitude = ORIGIN_LONGITUDE + start_lon_offset + (end_lon_offset - start_lon_offset) * fraction
        point_sog = sog
        point_cog = cog

        if slow_near_origin and datetime(2026, 8, 26, 5, 40, tzinfo=UTC) <= timestamp <= datetime(2026, 8, 26, 6, 20, tzinfo=UTC):
            point_sog = 3.2
        if course_change and timestamp >= datetime(2026, 8, 26, 6, 0, tzinfo=UTC):
            point_cog = 58.0

        records.append(
            AISRecord(
                mmsi=mmsi,
                timestamp=timestamp,
                latitude=latitude,
                longitude=longitude,
                sog=point_sog,
                cog=point_cog,
                vessel_name=vessel_name,
                ship_type="cargo",
            )
        )
    return records

