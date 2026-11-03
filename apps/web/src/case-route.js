export function caseIdFromPath(path) {
  const match = /^\/(?:case|policy-buying\/cases)\/([^/]+)$/.exec(path);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}
