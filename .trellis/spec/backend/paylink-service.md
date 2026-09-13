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
  response: { "ok": true, "config": { provider, fallback, pool, stages, visible_stages } }
  fallback: { env_key, configured, masked_value }
  pool: { env_key, configured, count, masked_values }
  stages: [{
    stage: "checkout" | "promotion" | "provider" | "approve",
    label: string,
    role: string,
    region: string,
    fallback: { env_key, configured, masked_value },
    pool: { env_key, configured, count, masked_values }
  }]

PUT /api/config/proxy
  request:  { "provider": string, "stage"?: "checkout" | "promotion" | "provider" | "approve", "fallbackProxy"?: string, "proxyPool"?: string }
  response: { "ok": true, "config": <masked projection> }

POST /api/config/proxy/test
  request:  { "provider": string, "stage"?: "checkout" | "promotion" | "provider" | "approve" }
  response: { "ok": boolean, "provider": string, "stage": string, "duration_ms": integer, "message": string }

GET /api/config/provider?provider=paypal
  response: { "ok": true, "config": { provider, country, locale, currency, choices, locale_choices } }

PUT /api/config/provider
  request:  { "provider": "paypal", "country": "US" | "TH" | "BR", "locale"?: "en" | "th" | "pt-BR" }
  response: { "ok": true, "config": <credential-free profile projection> }

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
- Payment-method implementation references are intentionally one-primary-source
  per provider to prevent duplicate project drift. PayPal follows
  `kuozhan/PayPal-Global-Rotation-Sanitized-Source`; UPI follows
  `py/upi-source-sanitized-20260719`; PIX, iDEAL, and Kakao Pay follow their
  matching directories/files under
  `py/plus/_extracted/提链脚本/ideal-link-extractor-open-source-20260712`;
  GCash follows `py/gcash_from_token.py`. Other extracted PayPal, PIX, or UPI
  packages are diagnostics-only unless this contract is deliberately updated.
- The operator UI style reference is intentionally separate from payment
  implementation references. `py/gpt-upi` is UI-only inspiration for the
  Paylink console: light shadcn-like surfaces, rounded cards, subtle borders,
  compact pill navigation, muted helper text, and understated primary buttons.
  Its API routes, queue logic, proxy selection, billing rules, and extraction
  code must not be imported or mirrored by the maintained Paylink backend.
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
  load or save. The settings UI visibly edits stage proxy pools only. Legacy
  fallback proxy fields may still appear in API projections for compatibility,
  but they are not rendered as editable operator controls.
- Proxy configuration keeps the internal four-stage model:
  `checkout`, `promotion`, `provider`, and `approve`. The API also returns a
  provider-specific `visible_stages` projection for the operator page. PayPal
  visibly exposes only `provider` as the main Checkout/PayPal pool plus
  `promotion` as the checkout-update trial pool. The first-release complete
  providers UPI, PIX, iDEAL, Kakao Pay, and GCash visibly expose
  `checkout`, `promotion`, and `provider`; `approve` remains an internal
  override/fallback contract. The legacy top-level `fallback` and `pool`
  fields remain a backward-compatible alias of the `provider` stage, while
  the operator page saves only `proxyPool` for the selected visible stage.
  `PUT /api/config/proxy` validates changed values, preserves unrelated `.env`
  lines, atomically replaces that file, and updates the current process.
  Omitted fields stay unchanged; selected empty fields clear their setting.
- `POST /api/config/proxy/test` uses only a configured dedicated candidate for
  the requested provider stage against a neutral IP-echo target. It does not
  select a generic fallback, create Checkout state, or report the tested proxy
  value.
- Checkout HTTP errors are stored only as compact summaries: HTML bodies record
  the HTTP status and `HTML response`, while JSON bodies are redacted and
  bounded. Raw provider response bodies must not enter exceptions, task
  snapshots, events, or logs.
- Runtime proxy selection follows the stage route `checkout -> promotion ->
  provider -> approve`. Reference-compatible country routes are PIX
  `BR/VN/BR/BR`, UPI `IN/VN/IN/IN`, Kakao Pay `KR/VN/KR/KR`, Twint
  `CH/VN/CH/CH`, iDEAL `NL/VN/NL/NL`, GCash `PH/VN/PH/PH`, GrabPay
  `PH/VN/PH/PH`, and GoPay `ID/VN/JP/JP`. A stage-specific env key wins for
  that phase. If it is absent, `checkout` falls back to the legacy checkout
  source, `promotion` falls back to the provider seed rewritten to VN when
  possible, `provider` falls back to the legacy provider source, and `approve`
  falls back to provider stage. GCash keeps its existing PH provider keys and
  must not reuse the GoPay pool. GrabPay keeps its dedicated PH provider keys
  and must not reuse either GoPay or GCash proxy settings. GoPay keeps its
  established JP provider/approve fallback; billing `ID` must not rewrite that
  provider-stage fallback.
- The `promotion` stage is displayed as a trial/promo pool. Its implementation
  uses the OpenAI `/backend-api/payments/checkout/update` endpoint, but it is
  not a second Checkout creation pool.
- PayPal is a Checkout-link Provider with one explicit active profile in
  `[providers.paypal]`. US (`US` / `en` / `USD`) remains the default and uses
  the compatibility aliases `OPENAI_PAY_PAYPAL_PROXY` and
  `OPENAI_PAY_PAYPAL_PROXY_POOL`. Thailand (`TH` / `th` / `THB`) uses
  `OPENAI_PAY_PAYPAL_TH_PROXY` and `OPENAI_PAY_PAYPAL_TH_PROXY_POOL`; Brazil
  (`BR` / `pt-BR` / `BRL`) uses `OPENAI_PAY_PAYPAL_BR_PROXY` and
  `OPENAI_PAY_PAYPAL_BR_PROXY_POOL`. The profile owns billing country, payment
  locale, currency, and dedicated proxy selection; proxy text must never infer
  the profile. Billing country controls currency and proxy key selection, while
  payment locale is chosen from the fixed PayPal language whitelist
  `en` / `th` / `pt-BR`. The API returns only active profile metadata, country
  choices, locale choices, and masked proxy projections, atomically rewrites
  only PayPal's non-secret INI fields, then resolves the newly selected
  environment-key pair at runtime.
  US/TH/BR are three profiles of the same PayPal implementation, not separate
  reference projects. The PayPal settings page must label the selector as a
  billing Profile, expose both billing country and payment language controls,
  and display only the active profile's main pool and promotion pool.
  PayPal verifies that the Checkout lists `paypal` and returns only the
  Checkout URL. It does not create a Stripe payment method, submit a payment,
  or allocate a provider-pending queue record. PayPal `promotion` stage is
  optional and only runs when its stage-specific proxy is configured; the
  default Checkout-link path must not start a provider stage. Pool values are
  comma- or semicolon-separated URLs and must remain only in `.env`; tests use
  fixture proxy URLs.
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
- Visual styling should preserve the `py/gpt-upi`-inspired card language
  without coupling to its React/Tailwind implementation: use local static
  CSS, keep the two-level navigation contract, and avoid copying UI behavior
  that would duplicate existing Paylink business state.
- The global shell tabs are styled only through `assets/app-shell.css`. Top
  level tabs and provider tabs must share compact pill sizing, internal
  horizontal scrolling, active-state contrast, and page-wide cache versioning.
  The shared shell does not render a logout control in the primary navigation.
  Individual pages must not override those tab controls with legacy `button`
  or `a` rules.
- Provider tabs preserve the active global area. `kakao_pay` is translated to
  native `korea` only at the home/debug selector boundary. Queue navigation
  uses each registry entry's `queue_path`.
- Payment queue pages (`/qr`, `/in-qr`, `/kr-qr`, `/ch-qr`, `/nl-qr`,
  `/ph-qr`, and the generic provider queue fixture) share `assets/qr.css`.
  Queue content uses the same shell-aligned width, rounded title card, compact
  action buttons, pill status line, full-width empty state, and responsive
  card grid. Provider-hosted payment pages use the wider provider-frame grid
  instead of the small QR-card grid.
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
| Unsupported proxy stage | `PUT /api/config/proxy` and `POST /api/config/proxy/test` return HTTP 400 without writing `.env` or opening a test request. |
| Missing or unsupported PayPal country, or locale outside the whitelist | Profile API and direct PayPal request return HTTP 400 without rewriting `providers.ini`. |
| PayPal profile save | Only `country` and whitelisted `locale` in `[providers.paypal]` change atomically; the next proxy-config read reports the new regional key pair. |
| No changed proxy-config field | `PUT /api/config/proxy` returns HTTP 400 without writing `.env`. |
| Invalid proxy input | `PUT /api/config/proxy` returns HTTP 400 and leaves `.env` unchanged. |
| No dedicated Provider/stage proxy | `POST /api/config/proxy/test` returns HTTP 400; it must not test a generic proxy or inferred stage fallback. |
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
- Good: after selecting the TH profile, PayPal requests use THB billing,
  `th-TH` headers, and only `OPENAI_PAY_PAYPAL_TH_*` dedicated candidates;
  the BR profile follows the same contract with BRL, `pt-BR`, and
  `OPENAI_PAY_PAYPAL_BR_*`.
- Good: UPI settings show visible checkout/promotion/provider stages where
  provider remains `OPENAI_PAY_INDIA_PROXY_POOL`, promotion is
  `OPENAI_PAY_INDIA_PROMOTION_PROXY_POOL`, and no configured proxy value is
  returned to the page.
- Good: GCash config shows `OPENAI_PAY_PH_PROXY_POOL` and a pool count without
  exposing any configured entry, then writes validated replacements atomically.
- Good: a configured iDEAL checkout-stage pool overrides the legacy iDEAL
  provider pool only for Checkout creation; Stripe/provider and approve keep
  their stage-specific or provider-stage candidates.
- Base: a client only configures `EXTRACT_LINK_API_BASE` and receives normal
  progress events.
- Bad: route handlers map public provider aliases locally or place proxy
  credentials in `providers.ini`.
- Bad: loading a raw proxy URL into a configuration form, logging it, or
  testing a generic fallback when the selected provider has no dedicated proxy.
- Bad: implementing a provider-specific promotion update path when the shared
  stage-aware `update_checkout_promotion` contract covers the same request.
- Bad: selecting a PayPal billing country from a proxy string, accepting an
  arbitrary locale for a selected country, or adding payment confirmation to
  the Checkout-link lifecycle.
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
- Good: debug-generation task cards stay compact enough to show several
  entries in the progress panel by truncating long IDs and clamping long error
  summaries, while the modal remains the place for full logs/details.

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
- Proxy tests assert PIX uses BR/VN/BR/BR, UPI uses IN/VN/IN/IN, Kakao Pay
  uses KR/VN/KR/KR, Twint uses CH/VN/CH/CH, iDEAL uses NL/VN/NL/NL, GCash
  uses PH/VN/PH/PH, GrabPay uses PH/VN/PH/PH, and GoPay keeps ID checkout
  with JP provider/approve fallback. Stage tests must cover masked
  `stages[]` projection, stage-specific `.env` writes, checkout-stage
  precedence over provider-stage pools, approve-stage override/fallback, and
  absence of live proxy hosts or credentials. Visible-stage tests assert
  PayPal exposes provider/promotion, while UPI, PIX, iDEAL, Kakao Pay, and
  GCash expose checkout/promotion/provider.
- Twint queue-page tests assert public `data-provider-page="twint"` maps to
  native `swiss` before any queue API request and retains Twint labels.
- PayPal tests assert US alias compatibility plus TH/BR country, locale,
  currency, regional proxy precedence, masked configuration, atomic profile
  updates that preserve unrelated INI lines, Facade profile propagation, task
  filtering, and HTTP 409 when Checkout methods do not include `paypal`.
- GoPay tests assert the masked dedicated proxy settings, ID/id facade request,
  Tasks route, normalized redirect result, and provider-pending rejection.
- GrabPay tests assert masked dedicated proxy settings, PH/en facade request,
  Tasks route, normalized redirect result, and provider-pending rejection.
- Tests that patch one proxy selection path must explicitly clear every more
  specific pool used by that path. Module globals load `.env` at import time,
  so a local configured pool must never influence a fixture assertion.
- Proxy-configuration tests assert masked reads, atomic `.env` writes that
  preserve unrelated lines, runtime updates, invalid-input rollback, and
  credential-free dedicated IP-echo testing for a requested stage only.
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
renderProxyPool(config.pool);
await fetch("/api/config/proxy/test", { body: JSON.stringify({ provider }) });
```

#### Correct

```javascript
for (const stage of config.visible_stages || config.stages) renderProxyStage(stage);
await fetch("/api/config/proxy/test", { body: JSON.stringify({ provider, stage }) });
```

The settings page treats `checkout`, `promotion`, `provider`, and `approve` as
separate backend stage contracts, but renders the provider-specific visible
projection. The top-level `fallback` and `pool` are only the legacy
provider-stage alias.

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

#### Wrong

```python
country = country_from_proxy(proxy)
request.billing_country = country
```

#### Correct

```python
profile = paypal_profile(request.billing_country, request.payment_locale)
pool, fallback = paypal_proxy_source(profile["country"])
```

The explicit PayPal profile is the single source of truth for billing and
dedicated proxy selection. This preserves deterministic US compatibility and
allows a new country to be added through the profile catalogue without copying
the Checkout lifecycle.
