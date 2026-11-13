# Bundled scanner

`UnchainedScanner` is the Linux x64 scanner built from
[UnchainedLauncher `0b0974d`](https://github.com/Chiv2-Community/UnchainedLauncher/commit/0b0974d0636e8174d0f87b609202345566fa103d)
(merged PR #192 on `hotfix/v1.0.x`).

Build from that checkout:

```sh
dotnet publish UnchainedLauncher.PakScannerApp/UnchainedLauncher.PakScannerApp.csproj \
  --configuration Release --runtime linux-x64 --self-contained true \
  -p:PublishSingleFile=true -p:PublishTrimmed=false --output scanner-publish
```

Published with .NET SDK 10.0.112, targeting the project's .NET 8 runtime.
SHA-256: `4965e497d6939880ee4dfbecb91454c61fa59f4eebbc4506c1f6712ae81699c9`.

Only explicit `show_in_gui: false` opts out of GUI visibility. Missing/null
values remain null in registry records; no synthetic `is_hidden` is emitted.

Manifest asset lists and marker blueprint references use ordinal path ordering.
Pak entries use ordinal pak path, then name. Specialized-asset overlap cleanup
runs after parallel scanning finishes, avoiding nondeterministic inventory loss.
The `generated_at` envelope timestamp remains per-run; registry inventories do
not store it.
