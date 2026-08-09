# Integrate GrabPay Paylink Provider

## Goal

Expose the maintained Philippines GrabPay path as a first-class public Paylink
provider with its own proxy configuration and observable task outcomes.

## Confirmed Facts

- `services/paylink/app.py` already has a native `grabpay` wallet-approval
  path with Philippines billing and redirect handling.
- GrabPay currently shares GoPay provider proxy settings, which prevents an
  operator from isolating regional routing and failure diagnosis.
- The public provider registry and root facade do not yet expose GrabPay.

## Requirements

1. `POST /api/extract` SHALL accept public `link_type=grabpay` and map it to
   the existing native GrabPay flow through the provider registry.
2. GrabPay SHALL use PH regional settings and dedicated GrabPay fallback/pool
   environment keys before any generic candidates. It SHALL not reuse GoPay's
   provider-stage pool.
3. The proxy configuration API and Settings page SHALL expose only masked
   GrabPay state and use a dedicated neutral IP-echo test path.
4. The facade SHALL preserve native task link type, normalized outcome, and
   terminal failure details without recording tokens, credentials, or raw
   provider responses.
5. The shared console and root configuration/help SHALL expose GrabPay through
   the existing registry-driven navigation and Provider-filtered Tasks view.
6. Tests SHALL cover registry/config behavior, PH proxy precedence, masked
   configuration, task filtering, approval outcome, and failures with fixtures
   only.

## Acceptance Criteria

- [ ] Registry/config tests resolve `grabpay` to its native path with PH
  settings and omit it when disabled.
- [ ] Facade tests persist native `link_type=grabpay`, return a normalized
  result when applicable, and preserve terminal errors without secret data.
- [ ] GrabPay selects its dedicated PH proxy fallback/pool before GoPay and
  generic candidates in fixture tests.
- [ ] Console Provider, Tasks, and Settings navigation render GrabPay and keep
  the selected provider context.
- [ ] Paylink and root extract-link suites pass without live payment work.

## Out Of Scope

- Reusing GoPay proxy settings, adding a payment confirmation path, or
  importing standalone protocol implementations.
