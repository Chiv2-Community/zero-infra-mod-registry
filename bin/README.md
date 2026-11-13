# Bundled scanner

`UnchainedScanner` is the Linux x64 scanner built from
[UnchainedLauncher `5c773ec`](https://github.com/Chiv2-Community/UnchainedLauncher/commit/5c773ecf62f800f524fcde7161c613ce6d5ee6bb)
(merged PR #191 on `hotfix/v1.0.x`).

Build from that checkout:

```sh
dotnet publish UnchainedLauncher.PakScannerApp/UnchainedLauncher.PakScannerApp.csproj \
  --configuration Release --runtime linux-x64 --self-contained true \
  -p:PublishSingleFile=true -p:PublishTrimmed=false --output scanner-publish
```

Published with .NET SDK 10.0.112, targeting the project's .NET 8 runtime.
SHA-256: `5b1810cab5ff1e07b94b9b7aace0a0161445d6b6770d046a54d6080db6f9ebe2`.

Only explicit `show_in_gui: false` opts out of GUI visibility. Missing/null
values remain null in registry records; no synthetic `is_hidden` is emitted.
