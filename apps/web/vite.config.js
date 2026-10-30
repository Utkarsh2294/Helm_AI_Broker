import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
const baseHeaders = {
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
};
const csp =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    headers: {
      ...baseHeaders,
      'Content-Security-Policy': csp
        .replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")
        .replace("connect-src 'self'", "connect-src 'self' ws:"),
    },
    proxy: { '/api': process.env.HELM_API_PROXY || 'http://127.0.0.1:8010' },
  },
  preview: {
    allowedHosts: ['web'],
    headers: { ...baseHeaders, 'Content-Security-Policy': csp },
    proxy: { '/api': process.env.HELM_API_PROXY || 'http://127.0.0.1:8010' },
  },
});
