# Splat Assets

This directory stores all 3D Gaussian Splatting assets used by the frontend.

Layout:

- `source/`: raw input assets dropped into the project
- `derived/`: generated runtime assets grouped by asset id
- `_pipeline/`: auto-ingest status and pipeline metadata

Operational notes:

- The app should load assets through manifests first, not by guessing flat filenames.
- New raw files should be placed in `source/`.
- The auto-ingest pipeline can still detect legacy files dropped into `static/splat_files/` root and move them into `source/`.
