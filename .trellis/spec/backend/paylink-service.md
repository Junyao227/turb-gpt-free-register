# Paylink Service Contract

## Scenario: Local OPLL2 Paylink Facade

### 1. Scope / Trigger

- Trigger: the registration service delegates link generation to the maintained
  `services/paylink/` subproject.
- The contract crosses WebUI, root extract-link client, FastAPI job facade,
  OPLL2 progress storage, and account result persistence.

### 2. Signatures

```text
POST /api/extract
  request:  { "token": string, "link_type": "pix" | "upi" | "kakao_pay" | "ideal" }
  response: { "ok": true, "job_id": string }

GET /api/jobs/{job_id}/events
  events: log -> result | error -> done

GET /api/providers
  response: {
    "ok": true,
    "providers": [{
      "public_type": string,
      "native_type": string,
      "display_name": string,
      "country": string,
      "locale": string,
      "queue_path": string
    }]
  }

GET /?provider=<public_type>&view=tasks
  response: the maintained home console with its existing task workspace active

payment_page_terminal_failure(payload: object) -> string
  response: empty for non-terminal states; otherwise a redacted state/error summary
```

`kakao_pay` is mapped only by `paylink.provider_registry` to OPLL2's native
`korea` provider. The root client submits no query parameters to the event
endpoint.

### 3. Contracts

- `EXTRACT_LINK_API_BASE` is the only root-service connection setting.
- `config/providers.ini` owns provider `enabled`, `country`, and `locale`.
- `paylink.provider_registry` owns provider public/native identity, display
  name, and queue route. `GET /api/providers` returns enabled definitions in
  registry order and is the only provider catalog consumed by the console.
- Secrets and proxy credentials come from `services/paylink/.env`; they are
  redacted before logs and progress snapshots are persisted.
- Checkout and provider stages use region-scoped proxy pools. The first-release
  route is PIX `BR -> VN -> BR`, UPI `IN`, Kakao Pay `KR`, and iDEAL `NL`.
  Pool values are comma- or semicolon-separated URLs and must remain only in
  `.env`; tests use fixture proxy URLs.
- Checkout creation may rotate to the next regional proxy after a challenge or
  transport exception. Once Stripe returns a terminal submission state, the
  provider flow must preserve the Stripe error code and stop immediately rather
  than retrying a stateful payment operation or reporting a QR timeout.
- A terminal result has exactly these normalized fields: `long_url`,
  `copy_paste`, `image_url_png`, `image_url_svg`, `payment_method`,
  `payment_link_type`, and `expires_at`.
- The submitted access token is request-only. It must not appear in a task
  snapshot, an event, a log entry, or a persisted account result.
- The operator console uses shared `assets/app-shell.css` and
  `assets/app-shell.js` resources. Global navigation is stable across pages;
  provider tabs are generated from `/api/providers` and never duplicated as a
  hard-coded frontend provider list.
- Provider tabs preserve the active global area. `kakao_pay` is translated to
  native `korea` only at the home/debug selector boundary. Queue navigation
  uses each registry entry's `queue_path`.
- At narrow widths, both navigation rows stay single-line and scroll inside
  their own containers. Page content must not create document-level horizontal
  overflow; wide task tables scroll inside their table wrapper.
- `Generate` and `Tasks` are mutually exclusive projections of `index.html`.
  `view=tasks` activates the existing task workspace and polling code; it must
  not route to a copied task page. A legacy `#tasks` URL remains readable, but
  newly rendered navigation uses the query contract.
- Provider navigation preserves the active `view`. For example, switching from
  UPI Tasks to Kakao Pay yields `/?provider=kakao_pay&view=tasks` while the
  native home selector receives `korea`.
- Every `text/html` response carries `Cache-Control: no-store, max-age=0`,
  `Pragma: no-cache`, and `Expires: 0`. Static `/assets/*` responses are not
  modified by this HTML middleware.
- All operator pages reference the same version tag for `app-shell.css` and
  `app-shell.js`. Bump that tag across every page whenever a shared shell asset
  changes so previously loaded static assets cannot restore stale navigation.
- Shared-shell selectors must reset conflicting generic legacy-page rules.
  In particular, the brand link owns its background, padding, border radius,
  and minimum height because queue pages style all `a` elements globally.

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Unknown link type | `POST /api/extract` returns HTTP 400 before allocating a job. |
| Provider disabled or incomplete INI section | `POST /api/extract` returns HTTP 400 identifying the provider setting. |
| Empty token | A job is allocated, then its stream emits `error` followed by `done`. |
| Generator exception | Progress is marked failed with redacted text; stream emits `error`, then `done`. |
| Service restart during a job | The first stream consumer marks the unsupervised job interrupted, then receives `error`, then `done`. |
| Provider disabled | It is omitted from `GET /api/providers` and cannot appear as an active console tab. |
| Provider config missing or invalid | `GET /api/providers` returns HTTP 500 with the non-secret configuration diagnostic. |
| Provider metadata request fails in the browser | Global navigation remains usable; the shell does not invent fallback provider tabs. |
| `view=tasks` is absent or unknown | The home console renders the Generate view. |
| Legacy `#tasks` is present | The home console renders the existing Tasks view for compatibility. |
| HTML route response | Cache-prevention headers are added before the response is returned. |
| Static asset response | HTML cache middleware leaves its cache headers unchanged. |
| Checkout challenge or transport failure | Rotate through at most `MAX_CHECKOUT_PROXY_ATTEMPTS` candidates from the same provider region. |
| Stripe `submission_attempt.state` is `failed`, `canceled`, or `expired` | Return HTTP 502 immediately with a redacted state/error summary. |
| UPI terminal failure after approval | Classify it as `confirm-failed`; do not wait for the QR-resolution timeout. |

### 5. Good / Base / Bad Cases

- Good: `kakao_pay` is enabled and returns one normalized `result` event then
  one `done` event.
- Base: a client only configures `EXTRACT_LINK_API_BASE` and receives normal
  progress events.
- Bad: route handlers map public provider aliases locally or place proxy
  credentials in `providers.ini`.
- Good: adding an enabled provider registry entry with a queue route makes it
  appear in the shared second-level navigation without editing every HTML page.
- Base: `/debug-generate?provider=kakao_pay` selects native `korea` while the
  tab continues to display `Kakao Pay`.
- Bad: an HTML page hard-codes `PIX / UPI / Kakao Pay / iDEAL` as its own
  provider catalog or allows a wide table to expand the document viewport.
- Good: an IN Checkout reaches UPI approval and reports
  `checkout_upcoming_invoice_mismatch` immediately when Stripe marks the
  submission failed.
- Base: a provider proxy pool contains several regional candidates and a
  transport failure during Checkout creation advances to the next candidate.
- Bad: retrying a stateful Stripe confirm after a terminal response, or hiding
  its error code behind `upi qr resolution timeout`.
- Good: `/?provider=upi&view=tasks` hides generation controls, shows the same
  task DOM used by the original home page, and keeps all task polling active.
- Base: reloading `/in-qr` shows the shared two-level shell and hides the
  legacy `.upi-nav` menu.
- Bad: creating a second task HTML page or allowing a queue page's global
  `button, a` rule to restyle shared-shell links.

### 6. Tests Required

- Registry tests assert all four public names resolve and `kakao_pay` resolves
  to `korea`.
- A disabled provider test asserts no job is started.
- Facade lifecycle tests assert a single terminal result sequence and absence
  of the supplied access token from saved state and logs.
- Proxy tests use `fixture-user:fixture-pass@proxy.example.test`; copied live
  usernames, passwords, and provider hosts are forbidden even in test data.
- Root-client tests assert the create payload contains only `token` and
  `link_type`, and the event URL has no query string.
- Copied-console tests must resolve assets from `app.PUBLIC_DIR` and specify
  UTF-8 when reading them, so Windows and container tests use the same files.
- Provider metadata tests assert registry order, public/native mapping, queue
  paths, and omission of disabled providers.
- Console shell tests assert all operator pages load the shared assets, global
  labels remain stable, provider data comes from `/api/providers`, and home /
  debug pages translate the public `kakao_pay` query value.
- Home-view tests assert Tasks links use `view=tasks`, Generate and Tasks hide
  opposite sections, and provider links preserve the active view.
- Cache tests call the HTML middleware with both `text/html` and static media
  types, asserting all three no-store headers only on the HTML response.
- Shared-shell tests assert every operator page uses the same asset version and
  that brand-link reset rules remain scoped to `.paylink-app-shell__brand`.
- Browser verification covers desktop and 390px widths, active states,
  generation/debug/queue routing, internal horizontal scrolling, document
  width, and console errors.
- Proxy tests assert PIX uses BR/VN, UPI uses IN, Kakao Pay uses KR, and iDEAL
  uses NL without including live proxy hosts or credentials.
- Payment-page tests assert terminal failure extraction keeps the nested Stripe
  error code, raises HTTP 502 on the first poll, and classifies UPI as
  `confirm-failed`.

### 7. Wrong vs Correct

#### Wrong

```python
payload = {"token": token, "link_type": link_type, "quota_code": code}
events_url = f"{base}/api/jobs/{job_id}/events?quota_code={code}"
```

#### Correct

```python
payload = {"token": token, "link_type": link_type}
events_url = f"{base}/api/jobs/{quote(job_id, safe='')}/events"
```

The facade owns provider adaptation and event translation. The root client
must remain a simple submit-and-consume consumer.

#### Wrong

```javascript
const providers = ["pix", "upi", "kakao_pay", "ideal"];
```

#### Correct

```javascript
const response = await fetch("/api/providers", { cache: "no-store" });
const { providers } = await response.json();
```

The console renders provider tabs from the registry projection so enabled
state, aliases, and queue routes cannot drift between backend and pages.

#### Wrong

```javascript
const tasksTarget = "/tasks.html?provider=" + provider;
```

#### Correct

```javascript
const tasksTarget = `/?provider=${encodeURIComponent(provider)}&view=tasks`;
```

The query view reuses the maintained home markup, API calls, polling timers,
and log modal instead of creating a second task implementation.

#### Wrong

```python
while time.time() < deadline:
    payload = response.json()
    last_err = f"state={payload['submission_attempt']['state']}"
```

#### Correct

```python
terminal_failure = payment_page_terminal_failure(payload)
if terminal_failure:
    raise HTTPException(status_code=502, detail=f"upi payment failed: {terminal_failure}")
```

Stripe terminal states are business outcomes, not proxy failures. Preserve the
redacted failure code and stop polling; only Checkout challenge/transport
failures rotate regional proxy candidates.
