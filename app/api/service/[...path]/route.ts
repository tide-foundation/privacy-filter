import { NextRequest } from 'next/server';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const route = path.join('/');
  if (!/^(health|documents(?:\/[a-f0-9-]{36}(?:\/preview|\/download\/(pdf|docx|txt))?)?)$/.test(route))
    return Response.json({ detail: 'Not found' }, { status: 404 });
  const host = request.headers.get('host');
  if (!/^(localhost|127\.0\.0\.1):[0-9]{1,5}$/.test(host || ''))
    return Response.json({ detail: 'Host not allowed' }, { status: 403 });
  const origin = request.headers.get('origin');
  const allowed = [`http://${host}`];
  if ((origin && !allowed.includes(origin)) || request.headers.get('sec-fetch-site') === 'cross-site')
    return Response.json({ detail: 'Origin not allowed' }, { status: 403 });
  try {
    let body: Uint8Array | undefined;
    if (request.method === 'POST') {
      const chunks: Uint8Array[] = []; let size = 0;
      const reader = request.body?.getReader();
      if (reader) while (true) {
        const { done, value } = await reader.read(); if (done) break;
        size += value.length;
        if (size > 20 * 1024 * 1024) { await reader.cancel(); return Response.json({ detail: 'The upload limit is 20 MB.' }, { status: 413 }); }
        chunks.push(value);
      }
      body = Buffer.concat(chunks);
    }
    const response = await fetch(`http://127.0.0.1:8000/${route}${request.nextUrl.search}`, {
      method: request.method, body: body as BodyInit | undefined, cache: 'no-store', signal: AbortSignal.timeout(30000),
    });
    const headers = new Headers({ 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    for (const key of ['content-type', 'content-disposition']) { const value = response.headers.get(key); if (value) headers.set(key, value); }
    return new Response(response.body, { status: response.status, headers });
  } catch { return Response.json({ detail: 'The local Python service is unavailable. Start it using the README instructions.' }, { status: 503 }); }
}
export { proxy as GET, proxy as POST, proxy as DELETE };
