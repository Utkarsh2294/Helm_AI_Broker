import { createServer, request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';
import { readFile, stat } from 'node:fs/promises';
import { resolve, sep, extname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { randomBytes } from 'node:crypto';

const types = {
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.html': 'text/html',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.json': 'application/json',
};

export function createWebServer({
  dist = resolve('dist'),
  apiProxy = process.env.HELM_API_PROXY || 'http://127.0.0.1:8010',
  secure = process.env.HELM_WEB_HTTPS === 'true',
} = {}) {
  const root = resolve(dist),
    target = new URL(apiProxy);
  if (!['http:', 'https:'].includes(target.protocol))
    throw new Error('Unsupported API proxy protocol');
  return createServer(async (req, res) => {
    const nonce = randomBytes(24).toString('base64');
    res.setHeader(
      'Content-Security-Policy',
      `default-src 'self'; script-src 'nonce-${nonce}' 'strict-dynamic' 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'`,
    );
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Permissions-Policy', 'geolocation=(), camera=(), microphone=(self)');
    res.setHeader('Cache-Control', 'no-store');
    if (secure)
      res.setHeader('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
    if (req.url.startsWith('/api/')) {
      const headers = { ...req.headers, host: target.host };
      delete headers.connection;
      delete headers.upgrade;
      const upstream = (target.protocol === 'https:' ? httpsRequest : httpRequest)(
        new URL(req.url, target),
        { method: req.method, headers },
        (response) => {
          res.writeHead(response.statusCode, response.headers);
          response.pipe(res);
        },
      );
      upstream.on('error', () => {
        if (res.headersSent) res.destroy();
        else {
          res.writeHead(502, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ detail: 'API temporarily unavailable' }));
        }
      });
      req.on('aborted', () => upstream.destroy());
      res.on('close', () => {
        if (!res.writableEnded) upstream.destroy();
      });
      req.pipe(upstream);
      return;
    }
    if (!['GET', 'HEAD'].includes(req.method)) {
      res.writeHead(405, { Allow: 'GET, HEAD' });
      res.end();
      return;
    }
    try {
      const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
      if (pathname.split(/[\\/]/).some((part) => part.startsWith('.'))) {
        res.writeHead(404);
        res.end();
        return;
      }
      let file = resolve(root, '.' + pathname),
        html = false;
      if (file !== root && !file.startsWith(root + sep)) {
        res.writeHead(404);
        res.end();
        return;
      }
      const info = await stat(file).catch(() => null);
      if (!info?.isFile()) {
        if (pathname.startsWith('/assets/') || extname(pathname)) {
          res.writeHead(404);
          res.end();
          return;
        }
        file = resolve(root, 'index.html');
        html = true;
      } else html = extname(file) === '.html';
      let content = await readFile(file);
      if (html)
        content = Buffer.from(
          content.toString('utf8').replace(/<script\b/g, `<script nonce="${nonce}"`),
        );
      else if (pathname.startsWith('/assets/'))
        res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
      res.setHeader(
        'Content-Type',
        (types[extname(file)] || 'application/octet-stream') +
          (['.js', '.css', '.html', '.json'].includes(extname(file)) ? '; charset=utf-8' : ''),
      );
      res.setHeader('Content-Length', content.byteLength);
      res.writeHead(200);
      res.end(req.method === 'HEAD' ? undefined : content);
    } catch (error) {
      res.writeHead(error instanceof URIError ? 400 : 500);
      res.end('The requested page could not be served.');
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const args = process.argv.slice(2),
    option = (name, fallback) => (args.includes(name) ? args[args.indexOf(name) + 1] : fallback);
  const host = option('--host', '0.0.0.0'),
    port = Number(option('--port', process.env.PORT || 5180));
  createWebServer().listen(port, host, () =>
    process.stdout.write(`Helm built web listening on port ${port}\n`),
  );
}
