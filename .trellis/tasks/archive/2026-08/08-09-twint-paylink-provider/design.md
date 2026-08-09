# Twint Paylink Provider Design

## Boundaries

The root registration project remains a facade client. It submits only the
public `twint` type to `services/paylink`; the Paylink service resolves that
type to its existing native `swiss` flow.

```text
root EXTRACT_LINK_TYPE=twint
  -> POST /api/extract
  -> provider_registry[twint]
  -> LongLinkRequest(link_type=swiss, CH/de)
  -> existing Swiss checkout and provider-page flow
  -> normalized facade result + Swiss pending-session storage
  -> Twint console tab and /ch-qr queue
```

## Provider Contract

The public registry entry is `twint`; the native link type remains `swiss`.
Provider settings use the existing CH country/locale values. The queue action
uses `/ch-qr`, because this is already the maintained Swiss provider-session
surface.

`PROVIDER_PROXY_ENV_KEYS` maps `twint` to the existing
`OPENAI_PAY_SWISS_PROXY` and `OPENAI_PAY_SWISS_PROXY_POOL` settings. No new
environment key is introduced and no proxy value leaves the masked Settings
API.

The root validation tuple accepts `twint`. It retains the existing request
shape `{ token, link_type }` and consumes the same job event stream; it never
translates public aliases locally.

## Console Behavior

Provider navigation remains generated from `GET /api/providers`. Adding the
registry entry makes Twint visible on Generate, Tasks, and Settings without a
second hard-coded Provider catalog. Its queue link is `/ch-qr`; task filtering
uses the registry alias so native `swiss` snapshots remain visible under
`?provider=twint`.

## Compatibility And Rollback

- Existing direct `swiss` and `twint` debug aliases continue to normalize to
  native `swiss` inside the Paylink service.
- Disabling `[providers.twint]` removes the Provider tab and rejects new facade
  jobs without deleting stored Swiss sessions.
- No Stripe request, payment confirmation, queue schema, or standalone source
  tree is changed.

## Test Strategy

- Registry/config tests cover resolution, enabled state, country/locale, and
  queue path.
- Facade and task tests assert the native stored type remains `swiss` while
  public navigation/filtering uses `twint`.
- Proxy configuration and selection tests use fixture URLs and assert Swiss
  precedence plus redaction.
- Root tests cover whitelist acceptance only; no live checkout is created.
