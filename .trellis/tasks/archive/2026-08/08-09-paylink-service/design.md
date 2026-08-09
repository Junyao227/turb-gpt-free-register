# Unified Paylink Service Design

## Boundaries

`services/paylink/` becomes a maintained copy of the OPLL2 baseline. It owns
provider execution, its operator console, provider configuration, job state,
and the compatibility facade. The root registration application remains a
consumer: it submits an account access token, listens for progress, and stores
only the normalized final result.

The source archives under `py/plus/_extracted` remain untouched. They are
reference material for later adapters, not an import path or runtime
dependency.

## Service Layout

```text
services/paylink/
  app.py                         # OPLL2 baseline application
  paylink/
    provider_registry.py          # public type -> native OPLL2 provider map
    provider_config.py            # INI loader and validation
    compat_facade.py              # async jobs and facade routes
    redact.py                     # tokens, secrets, and proxy credential masking
  config/providers.ini            # non-secret provider switches/settings
  public/                         # copied OPLL2 console assets
  runtime/                        # ignored persisted task state and event data
  .env.example                    # secret and proxy variable documentation
  Dockerfile
  docker-compose.yml
  tests/
```

The copied baseline will remove any inline proxy default. A proxy is optional
and comes only from the service environment.

## Provider Registry

The registry is the sole source of truth for a provider's public name, OPLL2
native name, display name, enable key, non-secret settings section, and queue
route.

| Public type | Native OPLL2 type | Config key |
| --- | --- | --- |
| `pix` | `pix` | `providers.pix` |
| `upi` | `upi` | `providers.upi` |
| `kakao_pay` | `korea` | `providers.kakao_pay` |
| `ideal` | `ideal` | `providers.ideal` |

`providers.ini` controls enabled state and documented non-secret defaults.
The registry validates an incoming public type before a job is allocated.
Disabled modules return a deterministic error without calling the OPLL2
generation path.

## Compatibility Facade

The root application uses the following first-release contract:

```text
POST /api/extract
  request:  { token, link_type }
  response: { ok: true, job_id }

GET /api/jobs/{job_id}/events
  SSE: log -> result | error -> done
```

The service has no quota counter or credit deduction endpoint.

On creation, the facade generates a safe job ID and submits a background call
to OPLL2's existing `generate_long_link_core`. It builds a `LongLinkRequest`
with the received token, the registry's native type, and the generated job ID.
OPLL2's existing `set_progress` and `runtime_store` persist progress. The SSE
route polls the same snapshot, emits a `log` when visible progress changes,
then emits exactly one terminal `result` or `error` event followed by `done`.

The facade converts `LongLinkResponse` into the main application's stored
result shape:

| Consumer field | OPLL2 source |
| --- | --- |
| `long_url` | `long_url`, then provider redirect, then checkout URL |
| `copy_paste` | provider QR value, UPI QR data, or PIX QR code |
| `image_url_png` | PIX or UPI PNG URL |
| `image_url_svg` | PIX SVG or provider SVG |
| `payment_method` | `payment_method_type` |
| `payment_link_type` | requested public type |
| `expires_at` | provider or PIX expiration timestamp |

The supplied access token is request-only. It is never written to a task
snapshot, event, log, error, or console page. Errors pass through the redactor
before persistence or SSE emission.

## Console Navigation

The console uses one shared shell loaded by existing static pages. Its first
row contains the stable global areas `Generate`, `Tasks`, `Payment Queues`,
`Debug Tools`, and `Runtime Statistics`. Its second row contains provider tabs
loaded from `GET /api/providers`.

`GET /api/providers` serializes enabled and valid first-release definitions
from `paylink.provider_registry`. Each item includes the public type, native
OPLL2 type, display name, country, locale, and queue route. The frontend does
not maintain a second provider catalog.

Existing OPLL2 pages remain the rendering surfaces. The shared shell maps the
active provider into each area using query parameters and existing queue
routes. The home and debug pages translate the public `kakao_pay` value back to
the native `korea` selector. Existing specialized UPI pages remain directly
accessible, but their duplicated top-level menu no longer defines the console
information architecture.

The provider row never wraps. At narrow widths it scrolls horizontally while
the content container retains stable dimensions. If the metadata request
fails, the shell keeps global navigation usable and shows no fabricated
provider entries.

The maintained home page owns both generation and task markup, but exposes
them as mutually exclusive query-driven views. `view=tasks` hides generation
controls and expands the existing task workspace; the default view hides the
task workspace. Provider links are derived with the current global area, so a
provider change inside Tasks keeps `view=tasks`. Legacy `#tasks` URLs are read
as Tasks for compatibility but newly rendered links use the query contract.

An application middleware adds `Cache-Control: no-store`, `Pragma: no-cache`,
and `Expires: 0` only to `text/html` responses. This prevents stale copied
OPLL2 pages from bypassing the shared shell after an upgrade without disabling
normal caching for versioned `/assets/*` files.

## Root Integration

`core/extract_link_service.py` submits only the token and link type, then
subscribes to the job event endpoint. Its existing queue, account lock, result
persistence, and WebUI status rendering remain intact.

## Configuration and Operation

The default process bind is `127.0.0.1:8787`. Compose binds the host port to
loopback and mounts `runtime/`. This preserves a separately operated local
service while preventing unintentional network exposure. The root application
sets `EXTRACT_LINK_API_BASE=http://127.0.0.1:8787`.

Non-secret provider state is source-controlled in `config/providers.ini`.
Secrets and proxy credentials are supplied through `.env`, documented by
`.env.example`, and removed from observable outputs. A console configuration
editor is deliberately deferred until the first four providers are stable.
Provider identity and queue routing exposed to the console remain owned by
`paylink.provider_registry`.

## Failure and Rollback

- Unsupported or disabled providers return an error before any generation call.
- Invalid or empty tokens return an error event and terminal `done`.
- Generation exceptions mark the OPLL2 snapshot failed and emit redacted
  terminal errors.
- Restarted services retain OPLL2 task snapshots; an interrupted in-flight
  task is shown as failed rather than retried automatically.
- Rollback consists of restoring the previous `EXTRACT_LINK_API_BASE` and
  stopping the separate service. The root application remains operational.
