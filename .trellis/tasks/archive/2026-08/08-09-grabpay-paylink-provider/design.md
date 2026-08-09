# GrabPay Paylink Provider Design

## Boundaries

GrabPay is already a native `grabpay` wallet-approval path. The work exposes
that path through the same public type without importing another payment
implementation or changing the approval/result lifecycle.

```text
root EXTRACT_LINK_TYPE=grabpay
  -> POST /api/extract
  -> provider_registry[grabpay]
  -> LongLinkRequest(link_type=grabpay, PH/en)
  -> maintained GrabPay approval flow
  -> normalized facade result or redacted terminal error
  -> /?provider=grabpay&view=tasks
```

## Provider And Proxy Contract

`providers.grabpay` uses the public and native type `grabpay`, country `PH`,
locale `en`, and the shared provider-filtered Tasks view as its operator
destination. It is an approval flow: a successful run returns the maintained
provider redirect/result; no new provider-pending queue or payment
confirmation path is introduced.

GrabPay receives its own masked configuration pair:

- `OPENAI_PAY_GRABPAY_PROXY`
- `OPENAI_PAY_GRABPAY_PROXY_POOL`

For both Checkout creation and the provider approval stage, an explicit
request proxy remains highest priority. Otherwise GrabPay's dedicated pool is
tried first, then its dedicated fallback, then the existing PH-rewritten
generic fallback. GoPay's pool and fallback are never candidates for
GrabPay. Existing GCash continues to use its current PH configuration.

## Console And Root Client

The console continues to build provider tabs from `GET /api/providers`; no
hard-coded frontend provider catalog is added. The root client adds
`grabpay` to the existing validation set and sends the unchanged `{ token,
link_type }` facade payload. Secrets, submitted tokens, proxy URLs, and raw
provider bodies remain outside logs, task snapshots, events, and UI responses.

## Compatibility And Rollback

- Existing direct native `grabpay` requests keep their approval behavior.
- Existing GoPay proxy configuration stops influencing GrabPay after rollout.
- Disabling `[providers.grabpay]` removes the public tab and rejects new facade
  requests without rewriting historical native task records.
- Removing the two GrabPay environment keys and its registry entry restores
  the prior exposure state; no schema migration or queue cleanup is required.

## Test Strategy

- Registry tests cover public/native identity, PH/en metadata, Tasks route,
  and omission when disabled.
- Proxy tests prove GrabPay's dedicated fallback and pool precede GoPay and
  generic candidates at Checkout and provider stages, and that the config API
  masks credentials.
- Facade and task-filter tests cover native task persistence, normalized
  outcomes, terminal errors, and provider-scoped task visibility.
- Console and root-client tests cover provider tabs, Tasks/Settings context,
  root type validation, and fixture-only execution.
