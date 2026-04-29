# Tooling

Project-local helper scripts live here.

Guideline:

- Keep heavyweight third-party toolchains outside the repo when possible
- Prefer setting `SPARK_ROOT` to an external Spark checkout such as `D:/tools/spark`
- Treat `tools/vendor/` as a fallback location only, not the default working setup
