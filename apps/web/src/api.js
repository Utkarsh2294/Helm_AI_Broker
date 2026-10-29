let csrf = decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('helm_csrf='))?.split('=')[1] || '');
let refreshInFlight = null;
export async function api(path, options = {}) {
  const { retried = false, ...requestOptions } = options;
  const response = await fetch(`/api/v1${path}`, {
    ...requestOptions, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...options.headers },
    ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
  });
  const data = await response.json();
  if (response.status === 401 && data.detail === 'Sign in to continue' && !retried && path !== '/auth/refresh') {
    refreshInFlight ||= api('/auth/refresh', { method: 'POST' }).finally(() => { refreshInFlight = null; });
    await refreshInFlight;
    return api(path, { ...options, retried: true });
  }
  if (!response.ok) {
    const message = typeof data.detail === 'string' ? data.detail : 'Please check the information and try again.';
    const error = new Error(message); error.status = response.status; error.requires_step_up = Boolean(data.requires_step_up); throw error;
  }
  if (data.csrf) csrf = data.csrf;
  return data;
}
export const money = pence => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 }).format(pence / 100);
export const label = value => String(value || '').replaceAll('_', ' ').toLowerCase().replace(/^./, c => c.toUpperCase());
