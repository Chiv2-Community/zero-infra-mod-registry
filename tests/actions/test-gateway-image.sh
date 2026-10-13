#!/usr/bin/env bash
set -euo pipefail
image=${1:?Pass the built gateway image}
temp=$(mktemp -d)
container="automated-registry-gateway-smoke-$$"
cleanup() {
  docker rm --force "$container" >/dev/null 2>&1 || true
  rm -rf "$temp"
}
trap cleanup EXIT
# This generated test key is not an installed GitHub App credential.
docker run --rm --entrypoint python "$image" -c '
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import sys
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
sys.stdout.buffer.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
' > "$temp/app.pem"
chmod 444 "$temp/app.pem"
mkdir "$temp/state"
chmod 777 "$temp/state"
docker run --detach --name "$container" --read-only --cap-drop ALL --security-opt no-new-privileges \
  --env GATEWAY_AUDIENCE=https://registry.example.com/registrations \
  --env REGISTRY_REPOSITORY=Org/Registry --env GITHUB_APP_ID=123 --env GITHUB_INSTALLATION_ID=456 \
  --env GITHUB_PRIVATE_KEY_FILE=/run/secrets/app.pem \
  --volume "$temp/app.pem:/run/secrets/app.pem:ro" --volume "$temp/state:/data" \
  "$image" >/dev/null
docker exec "$container" python -c '
import os, time, urllib.request, urllib.error
assert os.getuid() == 10001
for attempt in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/healthz", timeout=1) as response:
            assert response.status == 200
        break
    except urllib.error.URLError:
        if attempt == 29:
            raise
        time.sleep(0.1)
request = urllib.request.Request("http://127.0.0.1:8080/registrations", data=b"{}", headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(request, timeout=2)
    raise AssertionError("Unauthenticated registration accepted")
except urllib.error.HTTPError as error:
    assert error.code == 401
'
echo 'Gateway image smoke tests passed'
