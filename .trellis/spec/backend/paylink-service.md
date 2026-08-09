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
  request:  { "token": string, "link_type": "pix" | "upi" | "kakao_pay" | "twint" | "ideal" | "gcash" | "gopay" | "grabpay" | "paypal" }
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

GET /api/tasks?provider=<public_type>
  response: provider-filtered task snapshots, including failed tasks
  task item: { "link_type": <native_type>, ... }

GET /?provider=<public_type>&view=tasks
  response: the maintained home console with its existing task workspace active

GET /settings?provider=<public_type>
  response: administrator-only proxy configuration page for the selected public provider

GET /api/config/proxy?provider=<public_type>
  response: { "ok": true, "config": { provider, fallback, pool } }
  fallback: { env_key, configured, masked_value }
  pool: { env_key, configured, count, masked_values }

PUT /api/config/proxy
  request:  { "provider": string, "fallbackProxy"?: string, "proxyPool"?: string }
  response: { "ok": true, "config": <masked projection> }

POST /api/config/proxy/test
  request:  { "provider": string }
  response: { "ok": boolean, "provider": string, "duration_ms": integer, "message": string }

payment_page_terminal_failure(payload: object) -> string
  response: empty for non-terminal states; otherwise a redacted state/error summary
```

`kakao_pay` is mapped only by `paylink.provider_registry` to OPLL2's native
`korea` provider; `twint` is mapped only by that registry to native `swiss`.
`gopay` and `grabpay` retain the same public and native types. The root client
submits no query parameters to the event endpoint.

### 3. Contracts

- `EXTRACT_LINK_API_BASE` is the only root-service connection setting.
- `config/providers.ini` owns provider `enabled`, `country`, and `locale`.
- `paylink.provider_registry` owns provider public/native identity, display
  name, and queue route. `GET /api/providers` returns enabled definitions in
  registry order and is the only provider catalog consumed by the console.
- Twint uses public `twint`, native `swiss`, `CH` / `de`, and the maintained
  `/ch-qr` queue. Its masked proxy settings are `OPENAI_PAY_SWISS_PROXY` and
  `OPENAI_PAY_SWISS_PROXY_POOL`; the public alias never creates a new proxy
  credential surface.
- GoPay uses public/native `gopay`, `ID` / `id`, and the shared Tasks route
  `/?provider=gopay&view=tasks`. Its masked settings are
  `OPENAI_PAY_GOPAY_PROVIDER_PROXY` and
  `OPENAI_PAY_GOPAY_PROVIDER_PROXY_POOL`. The maintained approval flow does
  not create a provider-pending record or use the historical `/id-qr` page.
- GrabPay uses public/native `grabpay`, `PH` / `en`, and the shared Tasks route
  `/?provider=grabpay&view=tasks`. Its masked settings are
  `OPENAI_PAY_GRABPAY_PROXY` and `OPENAI_PAY_GRABPAY_PROXY_POOL`. The native
  approval flow creates neither a provider-pending record nor a payment
  confirmation operation.
- Secrets and proxy credentials come from `services/paylink/.env`; they are
  redacted before logs and progress snapshots are persisted.
- The administrator-only `/settings` page keeps the shared global shell and
  registry-backed provider tabs. It returns only `env_key`, configured state,
  and pool count; proxy URLs and credentials never return to the page after
  load or save.
- Proxy configuration maps every public provider to a dedicated fallback/pool
  environment-key pair. `PUT /api/config/proxy` validates changed values,
  preserves unrelated `.env` lines, atomically replaces that file, and updates
  the current process. Omitted fields stay unchanged; selected empty fields
  clear their setting.
- `POST /api/config/proxy/test` uses only a configured dedicated candidate for
  that provider against a neutral IP-echo target. It does not select a generic
  fallback, create Checkout state, or report the tested proxy value.
- Checkout HTTP errors are stored only as compact summaries: HTML bodies record
  the HTTP status and `HTML response`, while JSON bodies are redacted and
  bounded. Raw provider response bodies must not enter exceptions, task
  snapshots, events, or logs.
- Checkout and provider stages use region-scoped proxy pools. The first-release
  route is PIX `BR -> VN -> BR`, UPI `IN`, Kakao Pay `KR`, iDEAL `NL`, and
  GCash `PH`. GCash reads `OPENAI_PAY_PH_PROXY` and
  `OPENAI_PAY_PH_PROXY_POOL` before generic fallbacks; it must not reuse the
  GoPay pool. GoPay uses its dedicated approval pool first and keeps its
  established JP provider-stage fallback; billing `ID` must not rewrite that
  provider-stage fallback. GrabPay uses its dedicated PH pool and fallback
  before any generic PH-rewritten candidate at both stages. It must not reuse
  either GoPay proxy setting; GCash keeps its existing PH settings.
- PayPal is a standard US Checkout-link Provider. It reads
  `OPENAI_PAY_PAYPAL_PROXY` and `OPENAI_PAY_PAYPAL_PROXY_POOL` before generic
  US Checkout candidates, verifies that the Checkout lists `paypal`, and
  returns only the Checkout URL. It does not create a Stripe payment method,
  submit a payment, or allocate a provider-pending queue record.
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
- Each task snapshot persists its native `link_type` when the job is created.
  `GET /api/tasks` resolves an optional public `provider` through the registry
  before filtering and paginating, so a failed task remains in its originating
  provider tab even when it has no terminal result payload.
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
| Twint queue page | The public page identity stays `twint`, while queue, delete, and clear requests use native `swiss`. |
| GoPay queue request | `gopay` is rejected by provider-pending APIs; its public queue action returns the filtered Tasks view. |
| GrabPay queue request | `grabpay` is rejected by provider-pending APIs; its public queue action returns the filtered Tasks view. |
| Provider config missing or invalid | `GET /api/providers` returns HTTP 500 with the non-secret configuration diagnostic. |
| Provider metadata request fails in the browser | Global navigation remains usable; the shell does not invent fallback provider tabs. |
| `view=tasks` is absent or unknown | The home console renders the Generate view. |
| Legacy `#tasks` is present | The home console renders the existing Tasks view for compatibility. |
| HTML route response | Cache-prevention headers are added before the response is returned. |
| Static asset response | HTML cache middleware leaves its cache headers unchanged. |
| Unsupported proxy-config provider | Configuration API returns HTTP 400. |
| No changed proxy-config field | `PUT /api/config/proxy` returns HTTP 400 without writing `.env`. |
| Invalid proxy input | `PUT /api/config/proxy` returns HTTP 400 and leaves `.env` unchanged. |
| No dedicated Provider proxy | `POST /api/config/proxy/test` returns HTTP 400; it must not test a generic proxy. |
| IP-echo transport failure | Test returns `{ ok: false }` with a credential-free error class. |
| Checkout challenge or transport failure | Rotate through at most `MAX_CHECKOUT_PROXY_ATTEMPTS` candidates from the same provider region. |
| PayPal absent from Checkout methods | Return HTTP 409 before a successful facade result is persisted. |
| Stripe `submission_attempt.state` is `failed`, `canceled`, or `expired` | Return HTTP 502 immediately with a redacted state/error summary. |
| UPI terminal failure after approval | Classify it as `confirm-failed`; do not wait for the QR-resolution timeout. |

### 5. Good / Base / Bad Cases

- Good: `kakao_pay` is enabled and returns one normalized `result` event then
  one `done` event.
- Good: `gcash` is enabled, creates native `gcash` requests with PH/PHP
  billing, and routes pending sessions to `/ph-qr`.
- Good: `twint` is enabled, creates native `swiss` requests with CH/de
  billing, and its Twint-labelled `/ch-qr` page uses native `swiss` queue APIs.
- Good: `gopay` is enabled, creates ID/id native approval requests, returns a
  provider redirect only after approval, and directs operators to filtered
  Tasks instead of a provider queue.
- Good: `grabpay` is enabled, creates PH/en native approval requests, uses its
  dedicated PH proxy settings, and directs operators to filtered Tasks instead
  of a provider queue.
- Good: `paypal` is enabled, creates a US/en Checkout, returns a normalized
  PayPal Checkout URL, and its queue tab routes to `view=tasks`.
- Good: GCash config shows `OPENAI_PAY_PH_PROXY_POOL` and a pool count without
  exposing any configured entry, then writes validated replacements atomically.
- Base: a client only configures `EXTRACT_LINK_API_BASE` and receives normal
  progress events.
- Bad: route handlers map public provider aliases locally or place proxy
  credentials in `providers.ini`.
- Bad: loading a raw proxy URL into a configuration form, logging it, or
  testing a generic fallback when the selected provider has no dedicated proxy.
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

- Registry tests assert all nine public names resolve, `kakao_pay` resolves
  to `korea`, `twint` resolves to `swiss` with `CH` / `de`, `gopay` resolves
  to native `gopay` with `ID` / `id`, `grabpay` resolves to native `grabpay`
  with `PH` / `en`, and `gcash` resolves to native `gcash` with `PH` / `en-PH`.
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
  debug pages translate the public `kakao_pay` and `twint` query values.
- Home-view tests assert Tasks links use `view=tasks`, Generate and Tasks hide
  opposite sections, and provider links preserve the active view.
- Task-list tests assert provider filtering occurs before summary and pagination,
  includes failed snapshots, and can infer the public Kakao Pay alias from a
  legacy facade result that lacks the persisted field; native GoPay snapshots
  remain under the public GoPay Tasks tab.
- Cache tests call the HTML middleware with both `text/html` and static media
  types, asserting all three no-store headers only on the HTML response.
- Shared-shell tests assert every operator page uses the same asset version and
  that brand-link reset rules remain scoped to `.paylink-app-shell__brand`.
- Browser verification covers desktop and 390px widths, active states,
  generation/debug/queue routing, internal horizontal scrolling, document
  width, and console errors.
- Proxy tests assert PIX uses BR/VN, UPI uses IN, Kakao Pay uses KR, Twint
  uses its existing dedicated CH Swiss pool, GoPay puts its dedicated approval
  pool ahead of the maintained JP fallback, GrabPay's dedicated PH pool and
  fallback both precede GoPay and generic candidates, iDEAL uses NL, and GCash
  prefers its dedicated PH pool without including live proxy hosts or
  credentials.
- Twint queue-page tests assert public `data-provider-page="twint"` maps to
  native `swiss` before any queue API request and retains Twint labels.
- PayPal tests assert registry country/locale, dedicated US proxy precedence,
  masked configuration, task filtering, and HTTP 409 when Checkout methods do
  not include `paypal`.
- GoPay tests assert the masked dedicated proxy settings, ID/id facade request,
  Tasks route, normalized redirect result, and provider-pending rejection.
- GrabPay tests assert masked dedicated proxy settings, PH/en facade request,
  Tasks route, normalized redirect result, and provider-pending rejection.
- Tests that patch one proxy selection path must explicitly clear every more
  specific pool used by that path. Module globals load `.env` at import time,
  so a local configured pool must never influence a fixture assertion.
- Proxy-configuration tests assert masked reads, atomic `.env` writes that
  preserve unrelated lines, runtime updates, invalid-input rollback, and
  credential-free dedicated IP-echo testing.
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

```python
return {"proxy": os.getenv("OPENAI_PAY_PH_PROXY", "")}
```

#### Correct

```python
return {"configured": bool(value), "env_key": "OPENAI_PAY_PH_PROXY"}
```

The configuration boundary receives raw values only on a changed `PUT` field;
read, save, test, and log projections stay credential-free.

#### Wrong

```javascript
const providers = ["pix", "upi", "kakao_pay", "ideal", "gcash"];
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

#### Wrong

```python
monkeypatch.setattr(app, "PROVIDER_PROXY_POOL", [fixture_proxy])
assert app.proxy_candidates_for_link_type("", "ideal") == [fixture_proxy]
```

#### Correct

```python
monkeypatch.setattr(app, "IDEAL_PROXY_POOL", [])
monkeypatch.setattr(app, "IDEAL_STAGE_PROXY", "")
monkeypatch.setattr(app, "PROVIDER_PROXY_POOL", [fixture_proxy])
assert app.proxy_candidates_for_link_type("", "ideal") == [fixture_proxy]
```

Provider-specific pools take precedence over generic pools. Tests must reset
both dedicated values so machine-local `.env` configuration cannot change the
asserted candidate order.
