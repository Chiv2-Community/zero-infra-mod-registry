const assert = require('node:assert/strict');
const { test } = require('node:test');
const { prepareRequest, submitRequest, repositoryParts } = require('./request.cjs');
const { parseRequest } = require('./issue.cjs');
const repository = { owner: 'Chiv2-Community', repo: 'UnchainedPlugin' };
const registry = { owner: 'Chiv2-Community', repo: 'C2ModRegistry' };
const release = { draft: false, tag_name: 'v1.0.0-RC3', assets: [{ name: 'UnchainedPlugin.dll', state: 'uploaded', size: 123 }] };
const source = data => ({ rest: { repos: { getReleaseByTag: async args => {
  assert.deepEqual(args, { ...repository, tag: release.tag_name });
  return { data };
} } } });
const prepare = data => prepareRequest(source(data), repository, release.tag_name, { kind: 'plugin' });

test('kind-scoped markers retain legacy recovery and exact prerelease tags', async () => {
  const request = await prepare(release);
  assert.equal(request.title, '[DLL RELEASE] UnchainedPlugin Version v1.0.0-RC3');
  assert.equal(request.marker, '<!-- c2modregistry:Chiv2-Community/UnchainedPlugin:v1.0.0-RC3:plugin -->');
  assert.equal(request.legacyMarker, '<!-- c2modregistry:Chiv2-Community/UnchainedPlugin:v1.0.0-RC3 -->');
  assert.deepEqual(parseRequest(request.body), { action: 'add-dll-release', repo_url: 'https://github.com/Chiv2-Community/UnchainedPlugin', release_tag: release.tag_name, dll_file: '' });
});
test('invalid tags and kinds are rejected without contacting GitHub', async () => {
  for (const tag of ['main', 'v1', 'v1.0.0\nmalicious', 'v1.0.0"']) await assert.rejects(prepareRequest({}, repository, tag, { kind: 'plugin' }), /semantic version/);
  await assert.rejects(prepareRequest({}, repository, release.tag_name, { kind: 'other' }), /kind/);
});
test('unpublished, mismatched, missing, empty, unfinished or ambiguous assets fail', async () => {
  for (const data of [
    { ...release, draft: true }, { ...release, tag_name: 'v1.0.0' }, { ...release, assets: [] },
    { ...release, assets: [{ ...release.assets[0], size: 0 }] },
    { ...release, assets: [{ ...release.assets[0], state: 'new' }] },
    { ...release, assets: [...release.assets, { ...release.assets[0], name: 'Other.dll' }] },
  ]) await assert.rejects(prepare(data));
});
test('explicit DLL selection is exact and reaches the request payload', async () => {
  const data = { ...release, assets: [...release.assets, { ...release.assets[0], name: 'Other.dll' }] };
  const request = await prepareRequest(source(data), repository, release.tag_name, { kind: 'plugin', asset: 'Other.dll' });
  assert.equal(parseRequest(request.body).dll_file, 'Other.dll');
  for (const asset of ['other.dll', 'missing.dll', 'mod.pak']) await assert.rejects(prepareRequest(source(data), repository, release.tag_name, { kind: 'plugin', asset }));
});
test('pak requests use the same registration protocol', async () => {
  const data = { ...release, assets: [{ name: 'Mod.pak', state: 'uploaded', size: 1 }] };
  const request = await prepareRequest(source(data), repository, release.tag_name, { kind: 'mod' });
  assert.equal(parseRequest(request.body).action, 'add-package-release');
  await assert.rejects(prepareRequest(source(release), repository, release.tag_name, { kind: 'mod' }));
});
test('creates a request in a configurable registry', async () => {
  const request = await prepare(release);
  const target = { owner: 'Other', repo: 'Registry' };
  const github = {
    rest: { issues: { listForRepo: 'list', create: async args => {
      assert.deepEqual(args, { ...target, title: request.title, body: request.body });
      return { data: { html_url: 'created' } };
    } } },
    paginate: async (method, args) => { assert.equal(method, 'list'); assert.deepEqual(args, { ...target, state: 'all', per_page: 100 }); return []; },
  };
  assert.equal((await submitRequest(github, target, request)).html_url, 'created');
});
test('mod preflight rejects multiple paks even with an explicit selection or unfinished second asset', async () => {
  for (const second of [{state: 'uploaded', size: 123}, {state: 'new', size: 0}]) {
    const data = {...release, assets: [{name: 'Client.pak', state: 'uploaded', size: 123}, {name: 'Server.pak', ...second}]};
    for (const asset of [undefined, 'Client.pak']) {
      await assert.rejects(prepareRequest(source(data), repository, release.tag_name, {kind: 'mod', asset}), /exactly one/);
    }
  }
  const data = {...release, assets: [{name: 'Client.pak', state: 'uploaded', size: 123}]};
  const request = await prepareRequest(source(data), repository, release.tag_name, {kind: 'mod', asset: 'Client.pak'});
  assert.equal(parseRequest(request.body).dll_file, '');
  await assert.rejects(prepareRequest(source({...data, assets: [{...data.assets[0], name: 'Client.PAK'}]}), repository, release.tag_name, {kind: 'mod'}));
});
test('direct recovery rejects conflicting or malformed fenced payloads rather than returning the wrong issue', async () => {
  const request = await prepareRequest(source(release), repository, release.tag_name, {kind: 'plugin', asset: 'UnchainedPlugin.dll'});
  for (const body of [request.body.replace('add-dll-release', 'add-package-release'), request.body.replace('v1.0.0-RC3"', 'v2.0.0"'), request.body.replace('https://github.com/Chiv2-Community/UnchainedPlugin', 'https://github.com/Other/Plugin'), request.body.replace('UnchainedPlugin.dll', 'Other.dll'), `${request.marker}\n\n\`\`\`json\n{bad}\n\`\`\``]) {
    const github = {rest: {issues: {listForRepo: 'list', create: async () => {throw new Error('Unexpected duplicate');}}}, paginate: async () => [{body, html_url: 'wrong'}]};
    await assert.rejects(submitRequest(github, registry, request));
  }
});
test('reruns reuse open and closed issues but never pull requests', async () => {
  const request = await prepare(release);
  for (const state of ['open', 'closed']) {
    const existing = { state, body: request.body, html_url: 'existing' };
    const github = {
      rest: { issues: { listForRepo: 'list', create: async () => { throw new Error('Unexpected duplicate'); } } },
      paginate: async () => [{ body: request.body, pull_request: {}, html_url: 'not-an-issue' }, existing],
    };
    assert.equal(await submitRequest(github, registry, request), existing);
  }
});
test('API errors propagate', async () => {
  await assert.rejects(prepareRequest({ rest: { repos: { getReleaseByTag: async () => { throw new Error('release unavailable'); } } } }, repository, release.tag_name, {kind: 'plugin'}), /release unavailable/);
  await assert.rejects(submitRequest({rest: {issues: {listForRepo: 'list'}}}, registry, {marker: 'marker'}), /paginate/);
});
test('issue parsing rejects malformed or incomplete requests', () => {
  for (const body of [null, '', '```json\n{bad}\n```', '```\nnull\n```', '```\n[]\n```', '```\n{}\n```']) assert.throws(() => parseRequest(body));
  for (const fields of [{action: 'remove'}, {repo_url: ''}, {release_tag: 1}, {dll_file: null}, {dll_file: ''}]) {
    assert.throws(() => parseRequest(`\`\`\`json\n${JSON.stringify({action: 'add-dll-release', repo_url: 'https://github.com/a/b', release_tag: 'v1.0.0', ...fields})}\n\`\`\``));
  }
});
test('repository inputs reject URLs and control characters', () => {
  assert.deepEqual(repositoryParts('Org/Repo'), {owner: 'Org', repo: 'Repo'});
  for (const value of ['', 'a', 'a/b/c', 'https://github.com/a/b', 'a/b\n']) assert.throws(() => repositoryParts(value));
});

test('mixed DLL and single PAK release creates two independent requests in either order, including legacy recovery', async () => {
  const data = {...release, assets: [...release.assets, {name: 'Other.dll', state: 'uploaded', size: 123}, {name: 'Mod.pak', state: 'uploaded', size: 123}]};
  const requests = {
    plugin: await prepareRequest(source(data), repository, release.tag_name, {kind: 'plugin', asset: 'UnchainedPlugin.dll'}),
    mod: await prepareRequest(source(data), repository, release.tag_name, {kind: 'mod', asset: 'Mod.pak'}),
  };
  for (const order of [['plugin', 'mod'], ['mod', 'plugin']]) {
    for (const legacy of [false, true]) {
      const issues = [];
      const github = {rest: {issues: {listForRepo: 'list', create: async args => {
        const issue = {body: args.body, html_url: `issue-${issues.length}`};
        issues.push(issue);
        return {data: issue};
      }}}, paginate: async () => [...issues].reverse()};
      const first = await submitRequest(github, registry, requests[order[0]]);
      if (legacy) first.body = first.body.replace(requests[order[0]].marker, requests[order[0]].legacyMarker);
      const second = await submitRequest(github, registry, requests[order[1]]);
      assert.notEqual(first.html_url, second.html_url);
      if (legacy) second.body = second.body.replace(requests[order[1]].marker, requests[order[1]].legacyMarker);
      assert.equal(await submitRequest(github, registry, requests[order[0]]), first);
      assert.equal(await submitRequest(github, registry, requests[order[1]]), second);
      assert.equal(issues.length, 2);
      assert.equal(parseRequest(issues.find(issue => parseRequest(issue.body).action === 'add-dll-release').body).dll_file, 'UnchainedPlugin.dll');
      assert.equal(parseRequest(issues.find(issue => parseRequest(issue.body).action === 'add-package-release').body).dll_file, '');
    }
  }
});

test('legacy recovery still rejects malformed and conflicting identity and DLL selection', async () => {
  const request = await prepareRequest(source(release), repository, release.tag_name, {kind: 'plugin', asset: 'UnchainedPlugin.dll'});
  const legacy = request.body.replace(request.marker, request.legacyMarker);
  for (const body of [legacy.replace('UnchainedPlugin.dll', 'Other.dll'), legacy.replace('v1.0.0-RC3"', 'v2.0.0"'), legacy.replace('https://github.com/Chiv2-Community/UnchainedPlugin', 'https://github.com/Other/Plugin'), legacy.replace('add-dll-release', 'add-package-release'), `${request.legacyMarker}\n\n\`\`\`json\n{bad}\n\`\`\``]) {
    const github = {rest: {issues: {listForRepo: 'list'}}, paginate: async () => [{body, html_url: 'wrong'}]};
    await assert.rejects(submitRequest(github, registry, request));
  }
});
