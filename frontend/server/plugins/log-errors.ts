import { definePlugin } from 'nitro';

// Log every unhandled server error to stderr. Cloud Run only keeps request
// logs by itself — without this a 500 leaves no trace of what threw
// (axlbrains/open-wearables#37).
export default definePlugin((nitroApp) => {
  nitroApp.hooks.hook('error', (error, context) => {
    const event = context?.event;
    const where = event ? `${event.req.method} ${event.url.pathname}` : 'unknown request';
    console.error(`[nitro] unhandled error during ${where}:`, error?.stack ?? error);
  });
});
