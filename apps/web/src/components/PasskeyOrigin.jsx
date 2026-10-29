import React from 'react';
export const passkeysAvailable = () => !/^(?:\d{1,3}\.){3}\d{1,3}$/.test(location.hostname) && !location.hostname.includes(':');
export default function PasskeyOrigin() {
  if (passkeysAvailable()) return null;
  const url = new URL(location.href); url.hostname = 'localhost';
  return <p className="muted">Passkeys require a hostname. <a href={url.href}>Open the localhost workspace</a> to use them.</p>;
}
