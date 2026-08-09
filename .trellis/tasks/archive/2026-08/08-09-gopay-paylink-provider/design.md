# GoPay Paylink Provider Design

## Boundaries

The public GoPay name and OPLL2's native type are both `gopay`; its provider
definition exists to centralize enabled state, ID billing settings, display
metadata, proxy configuration, and console navigation.

```text
root EXTRACT_LINK_TYPE=gopay
  -> POST /api/extract
  -> provider_registry[gopay]
  -> LongLinkRequest(link_type=gopay, ID/id)
  -> existing GoPay approval flow
  -> normalized facade result or redacted terminal error
  -> ?provider=gopay&view=tasks
```

## Provider Contract

`providers.gopay` uses `ID` / `id`. It maps to the native `gopay` type and
uses `/?provider=gopay&view=tasks` as its operator destination. This is an
approval-only flow: successful output is a provider redirect, while terminal
approval failures remain errors. It does not allocate a provider-pending
record or route new work to `/id-qr`.

`PROVIDER_PROXY_ENV_KEYS` exposes the existing
`OPENAI_PAY_GOPAY_PROVIDER_PROXY` and
`OPENAI_PAY_GOPAY_PROVIDER_PROXY_POOL` values through the masked settings
API. The checkout and provider paths keep their established selection:
dedicated GoPay candidates first; otherwise the wallet flow falls back to the
configured JP region. `ID` is the billing region, not a request to rewrite the
maintained provider-stage proxy region.

## Console And Root Client

The shared shell renders GoPay from `GET /api/providers`. Because the public
and native names match, no frontend alias mapping is added. Existing home and
debug controls already understand the native GoPay choice; switching provider
tabs preserves the active Generate, Tasks, or Settings area.

The root facade accepts `gopay` in the same `EXTRACT_LINK_TYPE` whitelist and
uses the unchanged payload `{ token, link_type }`. It never exposes proxy
values, stores the submitted token, or claims a payment completion beyond the
maintained approval outcome.

## Compatibility And Rollback

- Existing direct GoPay use retains native `gopay` behavior.
- Disabling `[providers.gopay]` hides the tab and rejects new facade jobs.
- No payment confirmation, queue schema, stored session record, or standalone
  source tree is added.

## Test Strategy

- Registry/config tests assert public/native `gopay`, ID/id, queue path, and
  disabled omission.
- Facade tests assert native persisted type, normalized public result, and
  redacted terminal error events.
- Proxy tests assert dedicated GoPay candidates precede fixture generic
  fallbacks, config reads stay masked, and JP fallback remains intact.
- Console and root tests assert task-view navigation, filtered tasks, visible
  help, and root type acceptance without live submission.
