self.addEventListener('push', (event) => {
  let payload = {};
  try { payload = event.data?.json() || {}; } catch { /* Ignore malformed provider data. */ }
  event.waitUntil(self.registration.showNotification('Helm workspace update', {
    body: 'Sign in to review your saved workspace notifications.',
    tag: 'helm-workspace-update',
    data: { url: payload.url === '/notifications' ? payload.url : '/notifications' },
  }));
});
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow('/notifications'));
});
