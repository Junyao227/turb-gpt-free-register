# Integrate GoPay Paylink Provider

## Goal

Expose the maintained Indonesia GoPay approval flow as a first-class public
Paylink provider while preserving its current approval-only behavior.

## Confirmed Facts

- `services/paylink/app.py` contains native `gopay` normalization, Indonesia
  billing defaults, wallet-approval fields, and dedicated GoPay proxy settings.
- The current maintained queue set excludes `gopay`; existing historical
  material documents a deliberate approval-only direction.
- The public provider registry and root facade do not yet expose GoPay.

## Requirements

1. `POST /api/extract` SHALL accept public `link_type=gopay` and resolve it to
   the existing native GoPay path through the provider registry.
2. The Provider SHALL use ID regional settings and a dedicated GoPay fallback
   and pool in the masked proxy configuration API.
3. The facade SHALL report the maintained approval/submission outcome and
   preserve terminal failures. It SHALL NOT claim that a GoPay payment has
   completed or create an unsupported provider-pending queue record.
4. The shared console SHALL expose GoPay through registry-backed Provider
   tabs. Its queue action SHALL use the Provider-filtered Tasks view unless
   future evidence changes the maintained approval-only contract.
5. Root validation and visible help SHALL add GoPay while retaining the
   existing submit-and-consume facade contract.
6. Tests SHALL cover registry mapping, enabled state, dedicated GoPay proxy
   priority with its maintained JP provider-stage fallback, masked
   configuration, task filtering, normalized outcomes, and terminal failure
   behavior with fixtures only.

## Acceptance Criteria

- [ ] Registry/config tests resolve `gopay` with ID settings and omit it when
  disabled.
- [ ] A facade job persists native `link_type=gopay` and emits the established
  result or explicit terminal error sequence.
- [ ] GoPay proxy tests prove its dedicated pool precedes generic fallbacks,
  retains the maintained JP provider-stage region, and never disclose
  credentials.
- [ ] Console navigation uses `?provider=gopay&view=tasks` for operator
  tracking and does not create an obsolete Indonesia queue page.
- [ ] Paylink and root extract-link test suites pass without live submission.

## Out Of Scope

- Reintroducing a GoPay provider queue or adding payment-status polling.
- Changing the maintained GoPay approval flow or importing standalone scripts.
