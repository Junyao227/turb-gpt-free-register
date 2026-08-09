# Unified Paylink Service

## Goal

Create a separately runnable, locally hosted paylink service using OPLL2's
FastAPI application and existing multi-page console as its foundation. The
main registration application will use it only through `EXTRACT_LINK_API_BASE`
instead of embedding payment-provider modules in its own process.

## Confirmed Facts

- OPLL2 is a FastAPI service with an existing console, page authentication,
  runtime persistence, task snapshots, logs, statistics, provider queue pages,
  and `/api/health`.
- OPLL2 already supports native generation paths for PIX, UPI, Korea/KakaoPay,
  iDEAL, Swiss, GoPay, GCash, and GrabPay behind `/api/long-link`.
- The main application treats the paylink implementation as an external
  service. Its client submits `POST /api/extract` and consumes
  `GET /api/jobs/{job_id}/events` with SSE `log`, `result`, `error`, and
  `done` events.
- The main application's current public link-type vocabulary is `pix`, `upi`,
  `kakao_pay`, and `ideal`. OPLL2 calls the Korea route `korea`, so the
  service adapter must own this compatibility mapping.
- The extracted `py/plus` packages include both standalone scripts and other
  FastAPI applications. They have separate configuration and runtime
  assumptions, so they cannot safely be imported wholesale into OPLL2.
- OPLL2 has a Dockerfile but no compose file, and does not provide a quota,
  credit, or remaining-balance endpoint.

## Decisions

- The first release covers `pix`, `upi`, `kakao_pay`, and `ideal` only.
- Later providers will be added incrementally through the module registry;
  they are not part of the first-release migration.
- `services/paylink/` is the maintained service source. It starts as a copied
  OPLL2 baseline; `py/plus/_extracted` remains read-only source evidence.
- The first release has no quota, credit, or license dependency.
- Provider switches and non-secret provider settings live in a centralized
  `services/paylink/config/providers.ini` file. Secrets and proxy credentials
  are injected through the service `.env`; the first release does not expose
  configuration editing in the OPLL2 console.

## Requirements

1. The service SHALL live as an independent subproject with its own startup
   command, dependencies, runtime directory, environment configuration, and
   compose file under `services/paylink/`.
2. The service SHALL retain OPLL2 as the initial operator-console shell rather
   than recreating its existing UI, task persistence, or authentication.
3. The service SHALL expose a compatibility facade for the current main
   application's extract-link client:
   - `POST /api/extract` accepting `token` and `link_type`
   - `GET /api/jobs/{job_id}/events` as an SSE stream.
4. A submitted extract job SHALL return a unique `job_id`, emit user-readable
   progress events, and terminate with exactly one result or error event.
5. The facade SHALL map public link types to OPLL2 provider identifiers in one
   registry. Module aliases, display names, availability, and configuration
   ownership SHALL not be scattered through route handlers or UI pages.
6. Each provider module SHALL have an enable switch and scoped configuration.
   Secret values and complete proxy credentials SHALL be loaded from the
   service environment, never emitted in API responses, logs, task snapshots,
   or UI configuration reads.
7. A disabled or misconfigured provider SHALL be rejected before creating a
   job, with a diagnostic error that identifies the provider and missing
   non-secret setting.
8. Existing main-application account-status behavior SHALL remain compatible.
   Pointing `EXTRACT_LINK_API_BASE` at this service must be sufficient for
   integration.
9. The first release SHALL include focused tests for the facade contract,
   provider registry, type aliases, job-event lifecycle, secret redaction, and
   disabled-module behavior.
10. The OPLL2 operator console SHALL add editable provider settings only after
    the four first-release providers are stable in production use.
11. The operator console SHALL use two navigation levels:
    - a stable global navigation for generation, tasks, payment queues,
      debugging, and runtime statistics;
    - a provider navigation generated from the enabled first-release provider
      registry entries.
12. Provider navigation SHALL preserve the current global area while switching
    between PIX, UPI, Kakao Pay, and iDEAL. Disabled providers SHALL not be
    presented as active navigation choices.
13. The provider navigation SHALL remain a single horizontally scrollable row
    at narrow viewport widths and SHALL not overlap or resize page content.
14. Existing OPLL2 routes SHALL remain directly accessible while their
    duplicated page-specific main menus are replaced by the shared console
    navigation.
15. `Generate` and `Tasks` SHALL be mutually exclusive views of the maintained
    home console. `?provider=<type>&view=tasks` SHALL show the task workspace
    without duplicating its markup, data loading, or log behavior into another
    page.
16. Switching provider tabs SHALL preserve the active `view`. Legacy `#tasks`
    links MAY remain readable for compatibility but SHALL resolve to the task
    view contract.
17. Operator HTML responses SHALL disable browser storage caching so a service
    upgrade cannot restore obsolete page markup or duplicated legacy tabs.
    Versioned static assets MAY retain their normal cache behavior.

## Acceptance Criteria

- [x] The service starts independently and its health endpoint responds.
- [x] OPLL2's console, authentication, task snapshot, log, and statistics
  pages remain available after the refactor.
- [x] The main application's existing extract-link client can submit a job,
  consume its SSE events, and persist either the returned result or error.
- [x] `pix`, `upi`, `kakao_pay`, and `ideal` are resolved through the registry
  and `kakao_pay` maps to the OPLL2 Korea provider.
- [x] A provider can be disabled by configuration and is rejected without any
  provider call.
- [x] Provider switches and non-secret settings load from
  `config/providers.ini`; no configuration editing form is introduced in the
  first release.
- [x] Secrets and full proxy credentials are absent from facade responses,
  events, logs, and persisted task records.
- [x] Adding a later provider requires one provider module and one registry
  entry, without modifying the facade protocol or the main application.
- [x] Global navigation consistently exposes Generate, Tasks, Payment Queues,
  Debug Tools, and Runtime Statistics on existing operator pages.
- [x] Provider tabs are sourced from the registry API, show only enabled
  first-release providers, and select the matching generation, queue, or debug
  context.
- [x] PIX, UPI, Kakao Pay, and iDEAL navigation works at desktop and narrow
  viewport widths without wrapping or overlapping.
- [x] Generate and Tasks render as distinct views using the same home-page
  markup and task-loading logic.
- [x] Provider switching preserves `view=tasks`, and `/in-qr` consistently
  loads the shared two-level navigation after a normal navigation or reload.
- [x] HTML responses include `Cache-Control: no-store` while static assets are
  not forced through the HTML cache policy.

## Out Of Scope

- Moving all extracted `py/plus` scripts into the first release.
- Replacing OPLL2's existing provider generation logic.
- Rewriting the main application's extract-link queue or WebUI.
- Exposing the service publicly without authentication and deployment controls.
- Quota accounting, credit management UI, and external authorization adapters.
