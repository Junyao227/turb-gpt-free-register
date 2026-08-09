# Assess BLIK Paylink Provider

## Goal

Determine whether BLIK can become a supported Paylink provider without
expanding the maintained service from payment-link generation into payment
submission or confirmation.

## Confirmed Facts

- `services/paylink/` has no native BLIK implementation, provider-registry
  entry, or configured BLIK flow.
- The only local BLIK implementation is an independent script under
  `py/plus/_extracted/`; it is not a maintained production dependency.
- That script requires a six-digit BLIK code, submits it to Stripe with Polish
  billing data, and polls the resulting payment state. Its reported success
  value is a `blik://` internal identifier rather than a reusable provider
  redirect URL.
- The current Paylink contract supports provider links and approval redirects,
  and deliberately excludes payment confirmation and credential editors.

## Requirements

1. The task SHALL establish whether a BLIK result can meet the existing
   normalized Paylink result contract without importing or executing the
   standalone script.
2. The task SHALL document the product boundary created by a BLIK-code input:
   it is a one-time payment authorization input, not a generic configuration
   value or proxy setting.
3. No BLIK code, access token, payment-method data, or raw Stripe response
   SHALL be persisted in task records, logs, tests, or committed configuration.
4. No production implementation SHALL start until the product owner chooses
   between a strict link-only boundary and an explicit BLIK submission flow.

## Acceptance Criteria

- [ ] The repository evidence and existing Paylink contract are recorded.
- [ ] The decision on handling BLIK codes is recorded before a design or
  implementation plan is created.
- [ ] If the strict link-only boundary is retained, the task closes with no
  provider-registry or UI changes.
- [ ] If BLIK submission is approved, a separate implementation design defines
  the input lifetime, redaction, terminal outcome handling, and fixture-only
  tests before any code is changed.

## Decision

The product retains its link-only boundary. BLIK is deferred because the
available implementation requires a one-time BLIK code and performs payment
submission and status polling.

## Out Of Scope

- BLIK-code collection, storage, submission, or payment-state polling.
- MoMo provider work. It remains deferred with BLIK until a separate product
  decision and maintained native flow exist.
