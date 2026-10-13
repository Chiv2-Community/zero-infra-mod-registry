const assert = require('node:assert/strict');
const { test } = require('node:test');
const { submitGateway, statusError } = require('./gateway.cjs');
const endpoint = 'https://registry.example.com/registrations';
const request = {kind: 'plugin', release_tag: 'v1.0.0', asset_name: 'Plugin.dll'};

test('binds the identity token to the endpoint and submits only structured release details', async () => {
  const core = {
    getIDToken: async audience => { assert.equal(audience, endpoint); return 'identity-token'; },
    setSecret: token => assert.equal(token, 'identity-token'),
  };
  const url = await submitGateway(core, endpoint, request, async (target, options) => {
    assert.equal(target, endpoint);
    assert.equal(options.redirect, 'error');
    assert.deepEqual(options.headers, {Authorization: 'Bearer identity-token', 'Content-Type': 'application/json'});
    assert.deepEqual(JSON.parse(options.body), request);
    return {ok: true, json: async () => ({issue_url: 'https://github.com/Org/Registry/issues/1'})};
  });
  assert.equal(url, 'https://github.com/Org/Registry/issues/1');
});
test('rejects unsafe endpoint URLs before requesting a token', async () => {
  for (const value of ['http://example.com/registrations', 'https://a:b@example.com/registrations', `${endpoint}?token=secret`, `${endpoint}#fragment`, 'https://example.com/other']) {
    await assert.rejects(submitGateway({}, value, request), /HTTPS URL/);
  }
});
test('requires id-token permission and propagates transport failures', async () => {
  await assert.rejects(submitGateway({getIDToken: async () => {throw new Error('id-token permission missing');}}, endpoint, request), /id-token: write/);
  await assert.rejects(submitGateway({getIDToken: async () => 'token', setSecret: () => {}}, endpoint, request, async () => {throw new Error('network');}), /could not reach/);
});
test('does not expose the token or upstream response bodies in errors', async () => {
  await assert.rejects(submitGateway({getIDToken: async () => 'secret-token', setSecret: () => {}}, endpoint, request,
    async () => ({ok: false, status: 403, json: async () => {throw new Error('must not read body');}})), /HTTP 403/);
});
test('requires a GitHub issue URL in the response', async () => {
  for (const issue_url of [null, 'javascript:alert(1)', 'https://attacker.example/issues/1', 'https://github.com/Org/Registry/issues/1\n']) {
    await assert.rejects(submitGateway({getIDToken: async () => 'token', setSecret: () => {}}, endpoint, request,
      async () => ({ok: true, json: async () => ({issue_url})})), /invalid issue URL/);
  }
});

test('each HTTP failure has human-readable, actionable guidance without response bodies', async () => {
  const advice = new Map([
    [400, /kind/], [401, /id-token/], [403, /published tag/], [404, /endpoint URL/],
    [409, /existing registry issue/], [413, /16 KiB/], [415, /Content-Type/],
    [422, /nonempty/], [429, /one-hour/], [502, /API quotas/],
    [503, /private key/], [504, /proxy timeout/], [500, /operator/], [418, /inputs/],
  ]);
  for (const [status, message] of advice) {
    assert.match(statusError(status).message, message);
    await assert.rejects(submitGateway({getIDToken: async () => 'token', setSecret: () => {}}, endpoint, request,
      async () => ({ok: false, status, json: async () => {throw new Error('must not read body');}})), message);
  }
});

test('malformed responses return clear guidance rather than raw parse errors', async () => {
  await assert.rejects(submitGateway({getIDToken: async () => 'token', setSecret: () => {}}, endpoint, request,
    async () => ({ok: true, json: async () => {throw new Error('parse error with sensitive body');}})), /invalid JSON response/);
});

test('two filename invocations request separate OIDC tokens without caching', async () => {
  let tokens = 0;
  const core = {getIDToken: async audience => {assert.equal(audience, endpoint); return `token-${++tokens}`;}, setSecret: () => {}};
  for (const [kind, asset_name] of [['plugin', 'Plugin.dll'], ['mod', 'Mod.pak']]) {
    const body = {kind, asset_name, release_tag: request.release_tag};
    await submitGateway(core, endpoint, body, async (target, options) => {
      assert.equal(options.headers.Authorization, `Bearer token-${tokens}`);
      assert.deepEqual(JSON.parse(options.body), body);
      return {ok: true, json: async () => ({issue_url: `https://github.com/Org/Registry/issues/${tokens}`})};
    });
  }
  assert.equal(tokens, 2);
});
