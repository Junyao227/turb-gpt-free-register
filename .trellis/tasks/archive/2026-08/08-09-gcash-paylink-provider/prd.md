# Integrate GCash and PayPal Paylink Providers

## Goal

Make GCash a first-class paylink provider that the root registration project
can request through the existing local Paylink facade and operators can select
and monitor from the shared console.

Extend the same maintained facade with the standard OpenAI Checkout PayPal
line. This scope is the generic PayPal checkout link only, not any country-
specific standalone protocol implementation.

## Confirmed Facts

- `services/paylink/app.py` already contains the native `gcash` Stripe payment
  method, PH/PHP billing, redirect resolution, and terminal-failure handling.
- `py/gcash_from_token.py` is standalone source evidence. Its normal Stripe
  path overlaps the maintained service, while its `checkout_provider=open_ai`
  Adyen fallback does not.
- The first-release provider registry, provider INI, root type validation, and
  root UI copy currently restrict the facade to PIX, UPI, Kakao Pay, and iDEAL.
- GCash and GrabPay currently share the GoPay provider proxy settings. GCash
  needs an independently configurable PH checkout/provider proxy pool.
- `services/paylink/app.py` already normalizes `paypal` and can return an
  OpenAI Checkout URL, but the facade registry rejects it because there is no
  maintained Provider definition, config entry, proxy setting, or console tab.
- The independent PayPal Thailand and Brazil projects under `py/plus/` use
  their own protocol flows and are not a drop-in dependency of the facade.

## Requirements

1. `POST /api/extract` SHALL accept public type `gcash` and map it to the
   native `gcash` flow through the provider registry.
2. The service SHALL expose GCash in `/api/providers` and the shared Provider
   navigation when `[providers.gcash]` is enabled.
3. GCash SHALL use `country=PH`, `locale=en-PH`, and a dedicated PH proxy pool
   for Checkout and provider stages, without writing proxy credentials to
   snapshots, logs, API responses, or source-controlled configuration.
4. The root extract-link client SHALL accept `EXTRACT_LINK_TYPE=gcash`; manual
   and batch extract actions SHALL retain their existing queue contract.
5. The console SHALL support `?provider=gcash` for generation and Tasks, and
   route its queue tab to a maintained PH queue page.
6. The first implementation SHALL use the existing maintained Stripe path. It
   SHALL NOT import or execute `py/gcash_from_token.py`, or add its Adyen
   fallback workflow.
7. The shared console SHALL expose an administrator-only proxy configuration
   view. It SHALL keep the global navigation stable, retain the active Provider
   tab, and manage the selected Provider's dedicated proxy fallback and pool.
8. Proxy credentials SHALL be returned only as masked display values. Saving
   changes SHALL update `services/paylink/.env` atomically, and proxy testing
   SHALL use a neutral IP-echo request without creating a checkout or payment.
9. `POST /api/extract` SHALL accept public type `paypal` and map it to the
   existing native `paypal` Checkout-link path with `country=US` and
   `locale=en`.
10. PayPal SHALL appear in the shared Provider and configuration navigation
    when `[providers.paypal]` is enabled. Its queue action SHALL open its
    Provider-filtered Tasks view because the standard Checkout-link path has no
    maintained provider-pending queue.
11. PayPal SHALL use a dedicated US fallback/pool configuration before generic
    Checkout proxy candidates, without importing or executing the standalone
    Thailand or Brazil protocol projects.

## Acceptance Criteria

- [ ] Registry/config tests resolve GCash to native `gcash`, PH, `en-PH`, and
  omit it when disabled.
- [ ] Facade job creation persists `link_type=gcash` and returns the normalized
  public `payment_link_type=gcash` result.
- [ ] PH proxy selection tests prove the GCash Checkout and provider stages use
  only fixture PH candidates before generic fallback.
- [ ] Root validation and configuration-editor help accept and describe GCash.
- [ ] The shared console renders a GCash Provider tab, preserves `view=tasks`,
  and the PH queue page loads the shared navigation.
- [ ] The proxy configuration view reads and saves the selected Provider's
  proxy fallback and pool without exposing raw credentials in API responses.
- [ ] The proxy test endpoint runs only the configured proxy against a neutral
  connectivity target and reports a redacted result.
- [ ] Registry/config tests resolve PayPal to native `paypal`, `US`, `en`, and
  its queue navigation targets the Provider-filtered Tasks view.
- [ ] A PayPal facade job persists `link_type=paypal` and returns the standard
  Checkout URL with normalized `payment_method=paypal`.
- [ ] PayPal uses its dedicated US proxy pool before generic Checkout
  candidates, and the configuration API exposes only masked PayPal settings.
- [ ] Checkout responses that do not offer PayPal fail before a successful
  facade result is emitted.
- [ ] Existing Paylink and root extract-link tests remain green.

## Out Of Scope

- Porting the standalone script's `checkout_provider=open_ai` / Adyen fallback.
- Importing or adapting the standalone Thailand or Brazil PayPal protocols.
- Editing payment-method, Stripe, or account credentials from the console.
- A live provider submission during automated tests.
