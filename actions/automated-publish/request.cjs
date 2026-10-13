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
  const assets = release.assets.filter(a => a.name.toLowerCase().endsWith(suffix) && a.state === 'uploaded' && a.size > 0);
  if (asset && !asset.toLowerCase().endsWith(suffix)) throw new Error(`Asset must end in ${suffix}.`);
  if (asset ? !assets.some(a => a.name === asset) : !assets.length || (kind === 'plugin' && assets.length !== 1)) throw new Error('Select an uploaded, nonempty release asset; multiple DLLs require asset_name.');
  const payload = {
    action: kind === 'plugin' ? 'add-dll-release' : 'add-package-release',
    repo_url: `https://github.com/${repository.owner}/${repository.repo}`,
    release_tag: tag,
  };
  if (kind === 'plugin' && asset) payload.dll_file = asset;
  // Preserve the original marker so existing plugin requests remain idempotent.
  const marker = `<!-- c2modregistry:${repository.owner}/${repository.repo}:${tag} -->`;
  return {
    title: `[${kind === 'plugin' ? 'DLL' : 'PAK'} RELEASE] ${repository.repo} Version ${tag}`,
    body: `${marker}\n\n\`\`\`json\n${JSON.stringify(payload, null, 2)}\n\`\`\`\n`,
    marker,
  };
}

async function submitRequest(github, registry, request) {
  const issues = await github.paginate(github.rest.issues.listForRepo, { ...registry, state: 'all', per_page: 100 });
  const existing = issues.find(issue => !issue.pull_request && issue.body?.includes(request.marker));
  if (existing) return existing;
  const { data: issue } = await github.rest.issues.create({ ...registry, title: request.title, body: request.body });
  return issue;
}
module.exports = { prepareRequest, submitRequest, repositoryParts };
