# Data Directory

This directory contains local development data for SIH 2026 PS 26143. External datasets and environmental forcing files are intentionally not committed to Git; teammates should place them in the expected folders after acquiring them from the original sources.

## Expected Layout

```text
data/
├── README.md
├── kaggle/              # external / ignored
├── synthetic_sar/       # small development smoke-test assets
└── ocean/
    ├── currents/        # external Copernicus NetCDF / ignored
    └── wind/            # external NOAA GFS GRIB2 / ignored
```

## Kaggle SAR Classification Dataset

Purpose: development exploration and classification-data inspection for Module A.

Expected folder:

```text
data/kaggle/
```

Expected files: image folders such as `Class_0/` and `Class_1/`, plus any metadata provided by Kaggle.

Git policy: do not commit. This is an external dataset and should be downloaded locally by each teammate according to the dataset license and Kaggle access rules.

## Synthetic SAR Development Dataset

Purpose: small software pipeline smoke testing for:

```text
training -> checkpoint -> inference -> predicted mask -> polygon extraction -> /detect
```

Expected folder:

```text
data/synthetic_sar/
```

Expected files: small PNG image/mask pairs under `images/` and `masks/`.

Git policy: may be committed if the team wants reproducible smoke tests. These samples are development-only and are not scientific Sentinel-1 training data.

The synthetic development masks are aligned to their corresponding image dimensions using nearest-neighbour interpolation solely for software pipeline smoke testing.

This alignment policy must not be applied blindly to real scientific datasets.

## Copernicus Marine Current Data

Purpose: real environmental current forcing for Day 3 Module B development tests.

Expected folder:

```text
data/ocean/currents/
```

Expected files: NetCDF files, for example `*.nc`, containing eastward and northward current variables such as `uo` and `vo`.

Git policy: do not commit. These are external environmental forcing files and may be large or subject to source-specific terms. Do not store Copernicus credentials or temporary authenticated URLs in this repository.

## NOAA GFS Wind Data

Purpose: real 10 m wind forcing for Day 3 Module B development tests.

Expected folder:

```text
data/ocean/wind/
```

Expected files: GRIB2 files such as:

```text
gfs.t06z.pgrb2.0p25.f000
gfs.t06z.pgrb2.0p25.f006
gfs.t06z.pgrb2.0p25.f012
```

Required variables: both `u10`/`10u` and `v10`/`10v` at 10 m above ground.

Git policy: do not commit. These are external environmental files and should be downloaded or regenerated locally from NOAA/NCEP GFS sources.
