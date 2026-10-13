const statusMessages = {
  400: 'Invalid request. Check kind, release_tag and asset_name; update the action.',
  401: 'Identity rejected. Check id-token: write, endpoint, public tag and repository enrollment.',
  403: 'Release identity mismatch. Run from the published tag in its own repository; keep the tag unchanged.',
  404: 'Endpoint not found. Check the endpoint URL and proxy routing to /registrations.',
  409: 'Conflicting request or reused token. Check the existing registry issue; rerun for a fresh token.',
  413: 'Request too large. The limit is 16 KiB; check proxy limits and update the action.',
  415: 'JSON required. Use the action and preserve Content-Type through the proxy.',
  422: 'Release or asset missing. Publish the release, upload a nonempty asset and check the exact asset_name.',
  429: 'Rate limit reached. Wait for the one-hour window or ask the operator to adjust limits.',
  502: 'GitHub API request failed. Ask the operator to check API quotas, App permissions and connectivity.',
  503: 'Gateway unavailable. Ask the operator to check the App installation, private key and state storage.',
  504: 'Gateway timed out. Ask the operator to check the proxy timeout, then rerun.',
};

function statusError(status) {
  const advice = statusMessages[status] || (status >= 500
    ? 'Service failed. Ask the operator to check gateway and proxy logs, then rerun.'
    : 'Request rejected. Check the endpoint and action inputs, or contact the operator.');
  return new Error(`Automated publish failed (HTTP ${status}): ${advice}`);
}

async function submitGateway(core, endpoint, request, fetchRequest = fetch) {
  let url;
  try {
    url = new URL(endpoint);
  } catch {
    throw new Error('endpoint must be an HTTPS URL ending in /registrations.');
  }
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/registrations') {
    throw new Error('endpoint must be an HTTPS URL ending in /registrations without credentials or query parameters.');
  }
  // Bind the GitHub-signed identity token to this exact gateway audience.
  let token;
  try {
    token = await core.getIDToken(endpoint);
  } catch {
    throw new Error('Automated publish could not obtain a GitHub OIDC token. Add permissions.id-token: write to this job.');
  }
  core.setSecret(token);
  let response;
  try {
    response = await fetchRequest(endpoint, {
      method: 'POST',
      redirect: 'error',
      signal: AbortSignal.timeout(90000),
      headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'},
      body: JSON.stringify(request),
    });
  } catch {
    throw new Error('Automated publish could not reach the gateway. Check HTTPS, certificate and proxy, then rerun.');
  }
  if (!response.ok) throw statusError(response.status);
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error('Automated publish received an invalid JSON response. Ask the operator to check proxy routing.');
  }
  if (!result || typeof result !== 'object' || typeof result.issue_url !== 'string' || !/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/issues\/\d+$(?![\s\S])/.test(result.issue_url)) {
    throw new Error('Registration gateway returned an invalid issue URL.');
  }
  return result.issue_url;
}
module.exports = { submitGateway, statusError };
