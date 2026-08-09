# Generalize PayPal Paylink Regions

## Goal

Extend the maintained PayPal Checkout-link provider so operators can select
Thailand and Brazil first, with a reusable country-profile model for future
PayPal regions.

## Confirmed Facts

- The public `paypal` provider currently resolves to `US` / `en` in
  `services/paylink/config/providers.ini` and the provider registry.
- PayPal only returns a Checkout URL after verifying that the Checkout exposes
  `paypal`; it does not create a payment method, submit a payment, or create a
  provider-pending record.
- The dedicated PayPal proxy pool is separate from generic candidates, but its
  current fallback rewrites the proxy region to `US`.
- Checkout billing country, locale, currency, and proxy region are separate
  inputs. Changing only the proxy pool leaves the facade's country profile at
  `US` / `en`, so it cannot correctly represent Thailand or Brazil.
- `kuozhan/PayPal-Global-Rotation-Sanitized-Source` demonstrates an explicit
  country-profile model: selected country drives currency, locale, billing
  data, and proxy routing. Its tests also assert that the country selection is
  explicit and is not inferred from proxy strings.
- That reference's global-rotation flow additionally creates Stripe payment
  methods, submits confirmation, polls for a redirect, and handles approval.
  Those steps are outside the existing Paylink Checkout-link contract.

## Requirements

1. Thailand and Brazil SHALL be supported through the existing PayPal
   Checkout-link lifecycle without payment confirmation.
2. Country profile selection SHALL drive Checkout billing country, locale,
   currency, and dedicated proxy candidates together; proxy selection alone
   SHALL NOT silently define the profile.
3. The implementation SHALL allow future PayPal country profiles through
   declarative configuration rather than one provider-specific code branch per
   country.
4. Proxy credentials, tokens, and raw Checkout responses SHALL remain absent
   from committed configuration, task snapshots, UI responses, and logs.
5. Fixture-only tests SHALL cover the US compatibility profile, Thailand,
   Brazil, country/profile validation, proxy precedence, and PayPal-unavailable
   terminal behavior.
6. The implementation SHALL reuse the reference project's declarative profile
   concept only. It SHALL NOT import its standalone application or copy its
   payment-method, confirmation, approval, session-pool, or token-parsing
   flows into `services/paylink/`.

## Acceptance Criteria

- [ ] A public PayPal country selector or provider variant exposes US, TH, and
  BR without duplicating the Checkout implementation.
- [ ] Switching country updates the billing and proxy profile as one explicit
  selection, while preserving the existing US default.
- [ ] Provider configuration remains masked and allows independent regional
  proxy pools.
- [ ] The existing facade event/result contract and filtered Tasks view work
  for each enabled PayPal profile.
- [ ] No test performs a live Checkout, payment submission, or confirmation.
- [ ] Thailand and Brazil use an explicitly selected profile rather than a
  country inferred from a proxy URL.

## Decision

- PayPal remains Checkout-link-only. The result is the maintained Checkout URL
  after the Checkout advertises `paypal`; the service does not create a payment
  method, submit confirmation, poll an approval result, or derive a payment
  link from an arbitrary proxy.
- The console retains one public `paypal` Provider. Its explicit country
  profile is configured from the Settings page and drives country, currency,
  locale, and a country-scoped PayPal proxy pool together.
- US remains the default profile. Thailand (`TH` / `th` / `THB`) and Brazil
  (`BR` / `pt-BR` / `BRL`) ship first. Other supported country profiles use
  the same configuration path.
