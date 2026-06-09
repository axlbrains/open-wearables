# axl-api wearables sync — async fan-out

Note for the Open Wearables backend team. **No code change is required on
your side** — this just documents what axl-api now does so you can plan
load and recognize the new traffic pattern.

## What changed in axl-api (2026-05-03)

axl-api previously had two cron handlers that synchronously iterated all
mapped athletes inside one HTTP request:

- `POST /v1/internal/cron/wearables/sync-workouts` — every 5 min
- `POST /v1/internal/cron/wearables/sync-body` — twice daily (02:00, 14:00 UTC)

Both fanned out to OW REST endpoints per athlete, which made the
controller request itself last ~5–30 s × N athletes. Cloud Scheduler's
180 s `attempt_deadline` started returning 504s as the athlete pool
grew (issue #33).

The cron handlers now enqueue one Redis background job per athlete and
return immediately (single-digit ms). A pool of in-process workers
(`GEN_WORKERS` env, currently 4) drains the queue and calls OW.

## What this means for OW load

- **Same total request volume**, but **temporally smoothed**. Previously
  the sync was a tight serial loop from a single worker; now it's
  parallelised by `GEN_WORKERS` (4 in prod) and spread across the
  ~5-minute cron interval.
- **Effective concurrency to OW per axl-api instance ≤ `GEN_WORKERS`**
  (default 4, may be raised to 8). Multiply by Cloud Run instance count
  for total — currently 1–2 instances during steady state.
- Endpoints affected (per athlete, per cron tick):
  - Workouts cron: `GET /v1/users/{user_id}/events/workouts`,
    `GET /v1/users/{user_id}/summaries/activity` (paged),
    `GET /v1/users/{user_id}/summaries/sleep` (paged),
    `GET /v1/users/{user_id}/timeseries` (paged).
  - Body cron: `GET /v1/users/{user_id}/timeseries` (body
    metrics window).
  - Plus the existing per-request `GET /v1/users/{user_id}/connections` lookup.

## Things that would help us long-term

These would let us reduce polling pressure further. Reviewed against the
current OW codebase on 2026-05-03 — two of the three are **already
solved upstream**, axl-api just needs to adopt them. The third remains
a real ask.

### 1. ✅ Webhook for new workout / new daily-summary events — **already exists**

OW has a full outgoing-webhooks system via Svix
(`backend/app/api/routes/v1/outgoing_webhooks.py`, mounted under
`/v1/webhooks`). Relevant event types
(`backend/app/schemas/webhooks/event_types.py`):

- `workout.created`, `sleep.created` — discrete sessions
- `connection.created` — new provider connection for a user
- Group events per category (`heart_rate.created`,
  `blood_glucose.created`, `body_composition.created`, …)
- Granular per-series events (`series.heart_rate.created`,
  `series.weight.created`, …)

**axl-api action item:** register one endpoint per environment via
`POST /v1/webhooks/endpoints` with the `filter_types` we care about
(at minimum `workout.created`, `sleep.created`, plus selected `series.*`
for body cron), then drop the 5-minute poll for those data classes.
Authenticated as a developer (JWT or API key). Tracking on axl-api side
in `src/wearables/wearables-webhook.controller.ts`.

### 2. ✅ Sync cursor — **already supported via `start_date`**

`getAllWorkouts` / `getAllSleepSummaries` / `getTimeseries` already
accept a `start_date` (or `start_time` for timeseries) ISO-8601
parameter. Passing `start_date=<last_successful_sync_at>` cuts the
per-athlete response size to only new data — no OW work needed.

The `cursor` parameter on these endpoints is for *intra-response*
pagination within a single window, not for cross-call resumption.

**axl-api action item:** persist `lastSyncedAt` per athlete and pass it
as `start_date` on the next call. Done.

### 3. ⚠️ 5xx retry budget surfaced in response — **real gap**

When OW's upstream provider (Garmin/Apple/etc.) is rate-limited, OW
internally retries with backoff (`backend/app/services/providers/api_client.py`
already handles 429 with `Retry-After` against upstream), but on
exhaustion it returns a generic 500 to the API consumer. axl-api has no
signal to back off vs. just retry immediately, so we burn worker slots
on doomed requests until upstream cools down.

**Proposed:** when the per-provider retry budget is exhausted on a 429,
return HTTP 429 to the caller with the upstream `Retry-After` header
preserved, instead of swallowing it into a 500. Caller-side is then
trivial: respect the header in our worker, requeue with delay.

Estimated effort: small (one place in `api_client.py` + plumbing
through to FastAPI's response). No urgency — file as a normal issue
when the OW team has bandwidth.

## Contacts

- axl-api side owner: Slava (slavarosin@gmail.com)
- Tracking issue (axl-deployment): #33
- Relevant code: `src/wearables/wearables-sync.service.ts`,
  `src/events/events.service.ts` (`enqueueWearablesSync`).
