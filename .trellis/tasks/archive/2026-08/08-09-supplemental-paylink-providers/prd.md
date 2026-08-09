# Supplemental Paylink Providers

## Goal

Expand the maintained local Paylink facade after GCash and PayPal without
copying provider-specific standalone scripts into the registration project.

## Confirmed Facts

- `services/paylink/app.py` already has maintained native paths for Swiss/Twint,
  GoPay, and GrabPay.
- Swiss/Twint already has CH proxy selection and the `/ch-qr` operator page.
- GoPay and GrabPay already use the wallet-approval implementation. The current
  maintained queue set excludes GoPay, so an obsolete Indonesia queue must not
  be reinstated without separate evidence and a later product decision.
- BLIK is only represented by an independent extractor. MoMo has channel
  probing but no complete maintained continuation/result parser. Regional
  PayPal projects use separate OTP/CAPTCHA/account state machines.

## Requirements

1. The parent task SHALL have no direct implementation changes. It owns the
   release order, shared boundaries, and integration review for its children.
2. Child tasks SHALL be implemented in this order: Twint, GoPay, then GrabPay.
3. Each child SHALL expose one public facade type through the existing provider
   registry, provider INI, root type validation, shared console, masked proxy
   configuration, task filtering, and test suites.
4. Each child SHALL reuse its maintained native path. It SHALL NOT import or
   execute scripts under `py/plus/` as production dependencies.
5. Provider proxy credentials SHALL remain confined to `services/paylink/.env`;
   API responses, task snapshots, logs, tests, and committed configuration use
   only redacted values or fixtures.
6. BLIK, MoMo, and country-specific PayPal protocols are explicitly deferred.
   They require separate research and a new task before entering this program.
7. No child SHALL perform a live payment confirmation in automated tests.

## Acceptance Criteria

- [ ] `08-09-twint-paylink-provider` is planned, implemented, verified, and
  archived before GoPay implementation starts.
- [ ] `08-09-gopay-paylink-provider` is planned, implemented, verified, and
  archived before GrabPay implementation starts.
- [ ] `08-09-grabpay-paylink-provider` is planned, implemented, verified, and
  archived with an isolated Philippines proxy configuration.
- [ ] All enabled supplemental providers render through registry-driven
  navigation and retain the existing facade event/result contract.
- [ ] The full Paylink suite and root extract-link suite pass after the final
  child is complete.

## Out Of Scope

- BLIK, MoMo, and standalone regional PayPal implementations.
- A new payment gateway, payment confirmation workflow, or credential editor.
- Direct implementation work in this parent task.
