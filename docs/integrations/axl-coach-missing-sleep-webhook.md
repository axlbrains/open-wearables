# axl-api isn't receiving `sleep.created` webhooks

Follow-up from `axl-coach-sync-pattern.md`. The webhook plumbing on
the axl-api side is wired and verified, but **no `sleep.created`
events are arriving** in production despite Oura sleep data being
available for the user.

## What axl-api expects

axl-api's `wearables-webhook.controller.ts` handles three event
types from OW:

- `workout.created` → triggers a workouts-only sync for that athlete.
- `sleep.created` → enqueues `MORNING_WORKOUT_WEBHOOK` background
  job, which auto-creates a fresh "Какая тренировка сегодня?"
  conversation with every coach the athlete is connected to. Real
  user-visible feature — replaces the legacy poll-and-postpone
  scheduled-message flow.
- everything else → ignored, returns `200 OK`.

Endpoint URL on prod: `https://api.axl.coach/v1/wearables/webhook`.
Svix signature verification active (secret in
`OPEN_WEARABLES_WEBHOOK_SECRET`).

## What we observed (2026-05-04)

User `slavarosin@gmail.com` (test athlete, has Oura connected via OW
provider mapping) had:

- Oura ring data clearly synced (the user's Oura app showed an
  updated readiness/sleep score at 05:44 Berlin = 03:44 UTC).
- Zero entries in axl-api Cloud Run logs matching
  `Received OW webhook` between 02:00 UTC and 05:30 UTC.
- The cron `processScheduledMessages` is firing every 5 min as
  expected, never finds anything to do (no scheduled-message rows).

Conclusion: the webhook simply didn't fire. axl-api side is fine —
zero `Received OW webhook ...` lines means OW didn't send anything.

## What to check on OW side

In rough order of likelihood:

### 1. Is the prod webhook endpoint registered with `sleep.created`?

`axl-coach-sync-pattern.md` listed the action item as "register one
endpoint per environment via `POST /v1/webhooks/endpoints` with
`filter_types` ['workout.created', 'sleep.created', …]". Verify
the **prod** endpoint subscription includes `sleep.created`.
A common slip is that `workout.created` was added at some point but
sleep wasn't.

```
GET /v1/webhooks/endpoints
# look for the axl-api prod URL, check filter_types
```

### 2. Did the Svix message actually leave OW for this user?

Svix dashboard → message log → filter by event type
`sleep.created`, recipient endpoint = axl-api prod, time range
2026-05-04 02:00–05:00 UTC. Two outcomes:

- **No messages at all** → OW upstream didn't generate the event
  (jump to #3).
- **Messages exist but failed delivery** → check the response codes.
  If 4xx/5xx, the response body Svix captured will show what
  axl-api complained about (signature mismatch, body parse, etc).

### 3. Did Oura provider deliver a sleep event into OW for this user?

Check the OW backend logs for the user's
`open-wearables` user id (we can hand it over) around 02:00–05:00
UTC. We're looking for a Garmin/Apple-style event ingestion log
that should fan out into the Svix `sleep.created` event.

If Oura delivered the data via polling instead of push, the
provider adapter may not have triggered the
`SleepCreated` event downstream — that's an OW provider-adapter
question.

## What we'd like back

Either:

- "Yes, endpoint subscription was missing `sleep.created` — fixed,
  please retry tomorrow" (most likely).
- "Provider adapter for Oura doesn't emit `sleep.created` for
  push-style sync — need to add it" (would need an OW change).
- "Webhook fired but signature verification rejected on axl-api
  side" (would point us back at our verification path — unlikely
  since we don't see *any* request hitting our handler, but worth
  ruling out).

No urgency-pager from us — the user falls back to the legacy
poll-and-postpone flow if the webhook misses, just delayed.

## Contacts

- axl-api owner: Slava (slavarosin@gmail.com)
- Webhook endpoint code: `src/wearables/wearables-webhook.controller.ts`
- Background job that creates the conversation:
  `src/events/events.service.ts` `handleMorningWorkoutWebhook`
- Test user that triggered today's investigation: athlete id
  `b08458fc-1bf6-4396-bc52-db2ae5a34d56` (slavarosin@gmail.com)
