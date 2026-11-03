# Docker builds

Run builds from the repository root:

```sh
docker build -f docker/zero-infra-mod-registry/Dockerfile -t registry-tool .
docker build -f docker/automated-registry-gateway/Dockerfile -t automated-registry-gateway:local .
```

- `zero-infra-mod-registry/`: registry image and GitHub Action entrypoint.
- `automated-registry-gateway/`: gateway image, Compose deployment, and example environment.

Both builds use the repository root as their context. Deployment instructions:
[gateway setup](../docs/registry/automated-registry-gateway.md).
