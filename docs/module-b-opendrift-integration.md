# Module B OpenDrift/OpenOil Integration

## Status

OpenDrift/OpenOil is available as an optional Day 3 Module B engine:

```text
engine=opendrift_openoil
```

The default engine remains:

```text
engine=development_drift_engine
```

This keeps the existing synthetic and real-data development engine behavior intact while allowing OpenOil smoke testing through the same `/drift` contract.

Native gridded forcing is now available and is the preferred development configuration for OpenOil experiments:

```text
engine=opendrift_openoil
forcing_strategy=native_grid
```

## Request

```json
{
  "latitude": 18.5,
  "longitude": 72.8333511352539,
  "timestamp": "2026-08-26T12:00:00Z",
  "mode": "real_data",
  "engine": "opendrift_openoil",
  "forcing_strategy": "native_grid"
}
```

`mode=real_data` is required for the OpenOil path. The adapter never silently falls back to synthetic environmental values.

## Forcing Strategies

Three drift configurations are supported:

- `development_drift_engine`: deterministic lightweight engine; supports `synthetic_dev` and real sampled vectors.
- `opendrift_openoil` + `constant_sample`: OpenOil with one real sampled current/wind vector held constant for debugging and regression.
- `opendrift_openoil` + `native_grid`: OpenOil with native gridded readers for spatially and temporally varying Copernicus currents and NOAA GFS winds.

## Native Grid Readers

The native-grid strategy attaches two OpenDrift readers to OpenOil:

```text
Copernicus currents -> opendrift.readers.reader_netCDF_CF_generic.Reader
NOAA GFS winds      -> opendrift.readers.reader_netCDF_CF_generic.Reader
```

The Copernicus NetCDF file is read directly with `standard_name_mapping`.

The NOAA GFS GRIB files are first loaded with `xarray`/`cfgrib`, combined across `valid_time`, normalized into an in-memory CF-like `xarray.Dataset`, and then passed to `reader_netCDF_CF_generic.Reader`. This keeps interpolation inside OpenDrift's reader system while avoiding the legacy `reader_grib` dependency on `pygrib`.

Variable mapping:

```text
uo  -> x_sea_water_velocity
vo  -> y_sea_water_velocity
u10 -> x_wind
v10 -> y_wind
```

## Constant Sample Bridge

The `constant_sample` strategy remains available. It uses the existing real-data reader to sample local files:

- Copernicus Marine currents: `uo`, `vo`
- NOAA GFS wind: `u10`, `v10`

The sampled values are mapped into OpenDrift's standard variable names:

```text
uo/current_u_mps -> x_sea_water_velocity
vo/current_v_mps -> y_sea_water_velocity
u10/wind_u_mps   -> x_wind
v10/wind_v_mps   -> y_wind
```

For the approved development scenario, the sampled values are:

```text
latitude: 18.5
longitude: 72.8333511352539
timestamp: 2026-08-26T12:00:00Z

current_u_mps: 0.05565712966566139
current_v_mps: -0.08426375145450038
wind_u_mps: 5.444647407552111
wind_v_mps: -0.15588012556281683
```

In `constant_sample`, these values are passed through an OpenDrift constant reader for the run. This is an integration bridge, not full gridded environmental forcing.

In `native_grid`, these same values are used only as a reader validation point; particles query gridded readers as they move through longitude, latitude, and time.

## Backward And Forward Runs

The adapter runs OpenOil twice:

- backward hindcast with a negative timestep
- forward forecast with a positive timestep

Both runs seed the configured particle count at the explicit geographic spill coordinate. API GeoJSON output remains longitude-first:

```text
[longitude, latitude]
```

## Configuration

```env
DRIFT_ENGINE=development_drift_engine

OPENDRIFT_BACKWARD_HOURS=6
OPENDRIFT_FORWARD_HOURS=6
OPENDRIFT_PARTICLE_COUNT=100
OPENDRIFT_TIME_STEP_MINUTES=60
OPENDRIFT_SEED_RADIUS_METERS=100.0
OPENDRIFT_FORCING_STRATEGY=native_grid
```

To use OpenOil by default in local experiments:

```env
DRIFT_ENGINE=opendrift_openoil
```

Per-request `engine` still takes precedence over the environment default.

## API And Pipeline Behavior

`POST /drift` supports `engine=opendrift_openoil`.

`POST /pipeline` supports `drift_engine=opendrift_openoil` and `drift_forcing_strategy=native_grid`. Both values are forwarded to Module B when an explicit geospatial spill seed is supplied.

If OpenDrift import fails, the backend still starts. The OpenOil path returns:

```text
status=opendrift_not_available
```

The health endpoint includes OpenDrift capability metadata.

## Limitations

This is not a scientifically validated operational oil-spill simulation.

Known limitations:

- Native GFS wind forcing is normalized from GRIB to an in-memory xarray dataset before OpenDrift reader attachment.
- Coastline, beaching, oil weathering, vertical processes, and ensemble calibration still require scientific review.
- Module A synthetic image centroids are still image-space pixels and are not converted to latitude/longitude.

The next scientific integration step is to validate coastline behavior, oil weathering settings, vertical processes, uncertainty calibration, and the environmental reader configuration against known incidents or domain-reviewed scenarios.
