# Integrate Twint Paylink Provider

## Goal

Expose the maintained Swiss payment flow as public `twint` in the local
Paylink facade and shared operator console.

## Confirmed Facts

- `services/paylink/app.py` already normalizes `twint` to native `swiss`.
- The maintained Swiss path already uses CH proxy selection and `/ch-qr`.
- The current public provider registry does not yet expose a `twint` entry.

## Requirements

1. `POST /api/extract` SHALL accept public `link_type=twint` and map it only
   through the registry to native `swiss`.
2. The provider definition SHALL use CH regional configuration, expose the
   existing Swiss/Twint queue route, and disappear when disabled.
3. The root extract-link whitelist and operator copy SHALL accept `twint`
   without changing the facade payload or SSE event contract.
4. Twint SHALL use the maintained Swiss checkout/provider proxy fallback and
   pool through the masked configuration surface. No raw proxy is returned or
   stored in test fixtures.
5. The console SHALL add a registry-driven Twint tab that preserves Generate,
   Tasks, and Settings context while routing queue navigation to `/ch-qr`.
6. The task SHALL reuse the maintained `swiss` implementation and SHALL NOT
   import standalone source trees.

## Acceptance Criteria

- [ ] Registry/config tests resolve `twint` to native `swiss` with CH settings
  and omit it when disabled.
- [ ] Facade lifecycle tests persist native `link_type=swiss` and return a
  normalized public Twint result without persisting the submitted token.
- [ ] Proxy tests prove dedicated Swiss candidates precede generic fallbacks
  using fixture URLs only.
- [ ] Root validation, provider navigation, task filtering, settings masking,
  and `/ch-qr` routing are covered by tests.
- [ ] The Paylink and root extract-link suites pass without a live provider
  submission.

## Out Of Scope

- Rewriting the Swiss payment flow or creating a separate Twint implementation.
- Live payment confirmation, token persistence, or proxy credential exposure.
