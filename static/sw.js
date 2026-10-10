/* CHRYSPHARMACY browser push worker. Generic message only: privacy on lock screens. */
self.addEventListener('push', function(event) {
  let data = {title: 'CHRYSPHARMACY', body: 'Έχετε νέο μήνυμα στο φαρμακείο.', url: '/client#messages'};
  try { if (event.data) data = Object.assign(data, event.data.json()); } catch (_) {}
  // Do not accept arbitrary external destinations from push data.
  const destination = '/client#messages';
  event.waitUntil(self.registration.showNotification('CHRYSPHARMACY', {
    body: data.body || 'Έχετε νέο μήνυμα στην προσωπική καρτέλα.',
    tag: 'chryspharmacy-message', icon: '/static/favicon.svg',
    data: {url: destination}
  }));
});
self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  event.waitUntil(clients.openWindow('/client#messages'));
});
