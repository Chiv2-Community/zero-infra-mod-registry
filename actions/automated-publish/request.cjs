const { parseRequest } = require('./issue.cjs');

function repositoryParts(value) {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$(?![\s\S])/.test(value)) throw new Error('Repository must be owner/name.');
  const [owner, repo] = value.split('/');
  return { owner, repo };
}

async function prepareRequest(github, repository, tag, options) {
  const { kind, asset } = options;
  if (!['plugin', 'mod'].includes(kind)) throw new Error('kind must be plugin or mod.');
  if (!/^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$(?![\s\S])/.test(tag)) throw new Error('Registry requests require a semantic version tag.');
  const { data: release } = await github.rest.repos.getReleaseByTag({ ...repository, tag });
  if (release.draft || release.tag_name !== tag) throw new Error('The tagged release must be published before requesting registration.');
  const suffix = kind === 'plugin' ? '.dll' : '.pak';
  const matches = name => kind === 'plugin' ? name.toLowerCase().endsWith(suffix) : name.endsWith(suffix);
  if (kind === 'mod' && release.assets.filter(a => matches(a.name)).length !== 1) throw new Error('A mod release must contain exactly one .pak file.');
  const assets = release.assets.filter(a => matches(a.name) && a.state === 'uploaded' && a.size > 0);
  if (asset && !asset.toLowerCase().endsWith(suffix)) throw new Error(`Asset must end in ${suffix}.`);
  if (asset ? !assets.some(a => a.name === asset) : assets.length !== 1) throw new Error('Select an uploaded, nonempty release asset; multiple DLLs require asset_name.');
  const payload = {
    action: kind === 'plugin' ? 'add-dll-release' : 'add-package-release',
    repo_url: `https://github.com/${repository.owner}/${repository.repo}`,
    release_tag: tag,
  };
  if (kind === 'plugin' && asset) payload.dll_file = asset;
  const legacyMarker = `<!-- c2modregistry:${repository.owner}/${repository.repo}:${tag} -->`;
  const marker = `<!-- c2modregistry:${repository.owner}/${repository.repo}:${tag}:${kind} -->`;
  return {
    title: `[${kind === 'plugin' ? 'DLL' : 'PAK'} RELEASE] ${repository.repo} Version ${tag}`,
    body: `${marker}\n\n\`\`\`json\n${JSON.stringify(payload, null, 2)}\n\`\`\`\n`,
    marker,
    legacyMarker,
  };
}

async function submitRequest(github, registry, request) {
  const issues = await github.paginate(github.rest.issues.listForRepo, { ...registry, state: 'all', per_page: 100 });
  const incoming = parseRequest(request.body);
  for (const existing of issues) {
    if (existing.pull_request || !(existing.body?.includes(request.marker) || existing.body?.includes(request.legacyMarker))) continue;
    const recovered = parseRequest(existing.body);
    // Legacy markers were shared by both kinds; verify identity before skipping
    // the other kind. A PAK request carrying DLL selection is not compatible.
    if (!existing.body.includes(request.marker) && recovered.repo_url === incoming.repo_url && recovered.release_tag === incoming.release_tag
        && recovered.action !== incoming.action && !(recovered.action === 'add-package-release' && recovered.dll_file)) continue;
    if (Object.keys(incoming).some(key => recovered[key] !== incoming[key])) throw new Error('This tag already has a different request; edit its registry issue.');
    return existing;
  }
  const { data: issue } = await github.rest.issues.create({ ...registry, title: request.title, body: request.body });
  return issue;
}
module.exports = { prepareRequest, submitRequest, repositoryParts };
