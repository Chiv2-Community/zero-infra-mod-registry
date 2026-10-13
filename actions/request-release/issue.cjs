function parseRequest(body) {
  const block = body?.match(/^```(?:json)?\s*\n([\s\S]*?)^```\s*$/m);
  if (!block) throw new Error('Include a fenced JSON registration request.');
  const payload = JSON.parse(block[1]);
  if (!payload || Array.isArray(payload) || typeof payload !== 'object') throw new Error('Request must be an object.');
  if (!['add-package-release', 'add-dll-release'].includes(payload.action)) throw new Error('Invalid registration action.');
  for (const field of ['repo_url', 'release_tag']) {
    if (typeof payload[field] !== 'string' || !payload[field].trim()) throw new Error(`${field} must be a nonempty string.`);
  }
  if (payload.dll_file !== undefined && (typeof payload.dll_file !== 'string' || !payload.dll_file.trim())) throw new Error('dll_file must be a nonempty string.');
  return { action: payload.action, repo_url: payload.repo_url, release_tag: payload.release_tag, dll_file: payload.dll_file || '' };
}
module.exports = { parseRequest };
