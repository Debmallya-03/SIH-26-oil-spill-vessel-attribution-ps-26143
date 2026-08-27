# Module B: Drift Hindcasting and Forecasting

## Scope

Module B estimates synthetic development drift trajectories from an explicit geographic spill centroid and detection timestamp. It does not consume Module A image-space pixels as latitude/longitude, and it does not implement AIS/vessel attribution.

## Input

`POST /drift` accepts:

```json
{
  "latitude": 18.5204,
  "longitude": 72.89,
  "timestamp": "2026-08-26T12:00:00Z",
  "backward_hours": 6,
  "forward_hours": 6,
  "particle_count": 100,
  "environment_mode": "synthetic_dev"
}
```

Latitude is validated in `[-90, 90]` and longitude in `[-180, 180]`.

## GeoJSON Convention

All GeoJSON coordinates are ordered as:

```text
[longitude, latitude]
```

The backward path is ordered from detection to past. The forward path is ordered from detection to future.

## Synthetic Development Mode

`synthetic_dev` uses deterministic synthetic forcing:

- eastward/northward ocean current in m/s
- eastward/northward wind in m/s
- configurable windage factor
- deterministic seeded particle perturbations

Effective velocity is approximated as:

```text
ocean current + windage * wind
```

The engine converts meter displacement to latitude/longitude and accounts approximately for longitude scaling by latitude. This is a software pipeline validation engine only, not a scientifically validated oil-spill simulator.

## Particle Uncertainty

The development engine simulates a particle cloud. The centroid of the final backward particle distribution becomes the probable origin centroid. A convex hull of the final backward particles becomes the origin uncertainty polygon.

The origin time window is centered around the backward endpoint and uses a one-hour uncertainty window on each side.

## Real Data Mode

`real_data` is prepared for future NetCDF environmental forcing from sources such as Copernicus Marine, NOAA HYCOM, ERA5, and NOAA GFS. If no environmental files are configured, `/drift` returns `environment_data_not_ready` and does not fabricate forcing.

Current local files inspected:

```text
data/ocean/currents/cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_1787833203663.nc
data/ocean/wind/gfs.t06z.pgrb2.0p25.f000
data/ocean/wind/gfs.t06z.pgrb2.0p25.f006
data/ocean/wind/gfs.t06z.pgrb2.0p25.f012
```

Copernicus current file:

- dimensions: `time=5`, `depth=1`, `latitude=25`, `longitude=24`
- coordinates: `time`, `depth`, `latitude`, `longitude`
- variables: `uo`, `vo`
- `uo`: eastward sea-water velocity, `m s-1`
- `vo`: northward sea-water velocity, `m s-1`
- latitude coverage: `17.5` to `19.5`
- longitude coverage: `72.000015` to `73.91668`
- depth: `0.494025 m`
- time coverage: `2026-08-26T00:00Z` through `2026-08-27T00:00Z` at 6-hour steps

GFS GRIB2 files:

- grid: `9 x 9`, regular lat/lon, `0.25 degree`
- latitude coverage: `17.5` to `19.5`
- longitude coverage: `72.0` to `74.0`
- level: `10 m above ground`
- variables discovered: `u10`, 10 metre U/eastward wind component, `m s**-1`; `v10`, 10 metre V/northward wind component, `m s**-1`
- valid times: `2026-08-26T06:00Z`, `2026-08-26T12:00Z`, `2026-08-26T18:00Z`

The original target point is inside the current-file spatial/time bounds, but `uo/vo` interpolate to missing values at `18.5204, 72.89` for `2026-08-26T12:00Z`.

Nearest valid Copernicus current grid cell for the development point at `2026-08-26T12:00Z`, depth `0.494025 m`:

```text
requested: lat=18.5204, lon=72.89
nearest finite uo/vo: lat=18.5, lon=72.8333511352539
distance: 6.3894 km
uo: 0.05565712973475456 m s-1
vo: -0.08426374942064285 m s-1
```

The nearest grid cell to the original point is `lat=18.5, lon=72.91667938232422`, and both `uo` and `vo` are masked there. A local neighborhood inspection shows valid cells to the west and masked cells around and east of the requested longitude, so the original point is a coastal/land-masked area and interpolation fails because it crosses masked values. No extrapolation is performed.

GRIB message inspection with ecCodes found two messages per corrected GFS file:

```text
gfs.t06z.pgrb2.0p25.f000: shortName=10u, name=10 metre U wind component, typeOfLevel=heightAboveGround, level=10, valid=2026-08-26 06:00 UTC, units=m s**-1
gfs.t06z.pgrb2.0p25.f000: shortName=10v, name=10 metre V wind component, typeOfLevel=heightAboveGround, level=10, valid=2026-08-26 06:00 UTC, units=m s**-1
gfs.t06z.pgrb2.0p25.f006: shortName=10u, name=10 metre U wind component, typeOfLevel=heightAboveGround, level=10, valid=2026-08-26 12:00 UTC, units=m s**-1
gfs.t06z.pgrb2.0p25.f006: shortName=10v, name=10 metre V wind component, typeOfLevel=heightAboveGround, level=10, valid=2026-08-26 12:00 UTC, units=m s**-1
gfs.t06z.pgrb2.0p25.f012: shortName=10u, name=10 metre U wind component, typeOfLevel=heightAboveGround, level=10, valid=2026-08-26 18:00 UTC, units=m s**-1
gfs.t06z.pgrb2.0p25.f012: shortName=10v, name=10 metre V wind component, typeOfLevel=heightAboveGround, level=10, valid=2026-08-26 18:00 UTC, units=m s**-1
```

`cfgrib` loads these corrected files with both `u10` and `v10`.

Approved real-data development scenario:

```text
latitude: 18.5
longitude: 72.8333511352539
timestamp: 2026-08-26T12:00:00Z
```

At that point and time, the verified environmental values are:

```text
uo = 0.05565712966566139 m/s
vo = -0.08426375145450038 m/s
u10 = 5.444647407552111 m/s
v10 = -0.15588012556281683 m/s
```

Coastal masked-current handling in development mode uses the nearest finite Copernicus ocean grid cell only when it is within the configured distance threshold. Otherwise the particle is marked beached. This is a prototype policy and must be replaced/validated against OpenDrift/OpenOil coastline and reader behavior for production use.

The default development threshold is:

```text
DRIFT_MAX_NEAREST_CURRENT_DISTANCE_KM=10.0
```

Every nearest-current substitution is included in response metadata with the requested particle position, substituted grid position, distance, current values, and timestamp. The engine never synthesizes missing current values and never substitutes beyond the configured radius. Wind remains strict: unavailable or out-of-coverage GFS wind returns an explicit error instead of fabricated forcing.

Future NetCDF/GRIB integration should provide configurable variable mappings for latitude, longitude, time, u-current, v-current, u-wind, and v-wind.

## OpenDrift / OpenOil

OpenDrift/OpenOil remains the intended future physics engine. It is not installed in the current backend environment. A dry-run dependency check found that it would install `opendrift` plus a large geospatial stack including Cartopy, GeoPandas, NetCDF4, Copernicus Marine, and related dependencies. The development engine is isolated behind module boundaries so OpenDrift can replace it later without changing the API contract.

## Module A Integration Limitation

The current synthetic Module A checkpoint returns image-space centroid coordinates. These are not geospatial latitude/longitude values. `/drift` therefore requires explicit geographic input until georeferenced Sentinel-1 detection output is available.

## Scientific Limitation

This module currently validates the software path:

```text
geographic centroid -> synthetic forcing -> particle drift -> origin polygon -> forecast path -> API
```

It does not provide scientific validation, operational readiness, legal attribution, or real environmental reconstruction.
