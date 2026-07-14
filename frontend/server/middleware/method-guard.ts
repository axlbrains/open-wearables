import { defineHandler } from 'nitro';

// The dashboard is a read-only SPA: every legitimate request is GET/HEAD.
// Reject anything else before it reaches the router/SSR so bot scanners
// can't trigger SSR side effects or 5xx noise (axlbrains/open-wearables#37).
export default defineHandler((event) => {
  const { method } = event.req;
  if (method !== 'GET' && method !== 'HEAD') {
    return new Response('Method Not Allowed', {
      status: 405,
      headers: { Allow: 'GET, HEAD' },
    });
  }
});
