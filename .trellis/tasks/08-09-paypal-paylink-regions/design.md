# PayPal Regional Profile Design

## Boundaries

The maintained Paylink service continues to create a Checkout, assert that its
advertised payment methods contain `paypal`, and return the Checkout URL. The
regional feature changes only the request profile and regional proxy source.
It does not import `PayPal-Global-Rotation-Sanitized-Source`, create a Stripe
PaymentMethod, call a confirmation endpoint, or follow a PayPal approval URL.

```text
Settings: PayPal country profile (US | TH | BR | supported future country)
  -> providers.paypal country + locale
  -> PayPal profile API returns masked region-specific proxy state
  -> facade constructs LongLinkRequest(paypal, country, locale)
  -> Checkout request uses country + mapped currency
  -> Checkout method list must contain paypal
  -> normalized result returns Checkout URL
```

## Regional Configuration Contract

`[providers.paypal]` remains the single public PayPal provider. Its existing
non-secret values are the active profile:

```ini
[providers.paypal]
enabled = true
country = US
locale = en
```

The settings API validates the selected country against the maintained country
and locale catalogue. It normalizes country codes to uppercase and resolves a
default locale when the user does not provide one. The first release exposes:

| Profile | Country | Locale | Checkout currency | Proxy env prefix |
| --- | --- | --- | --- | --- |
| US | `US` | `en` | `USD` | `OPENAI_PAY_PAYPAL_US_` |
| Thailand | `TH` | `th` | `THB` | `OPENAI_PAY_PAYPAL_TH_` |
| Brazil | `BR` | `pt-BR` | `BRL` | `OPENAI_PAY_PAYPAL_BR_` |

For every profile, the dedicated settings are
`OPENAI_PAY_PAYPAL_<CC>_PROXY` and
`OPENAI_PAY_PAYPAL_<CC>_PROXY_POOL`. Existing
`OPENAI_PAY_PAYPAL_PROXY` and `OPENAI_PAY_PAYPAL_PROXY_POOL` remain the US
compatibility aliases. Reads, saves, and connectivity tests use only masked
projections.

## Runtime Flow

The facade already passes registry country and locale to `LongLinkRequest`.
PayPal stops overriding those fields to US/en. The engine validates the
explicit request profile, uses its country to obtain checkout currency, and
selects its dedicated regional proxy candidates before a generic proxy
rewritten to the same country. Proxy text is never parsed to infer country.

The task record remains `paypal`, preserving current Tasks filtering and the
root facade contract. The selected country is included only in the normalized,
credential-free result metadata needed for task visibility and diagnosis.

## Settings API

The existing Settings page gains a small PayPal profile editor, backed by a
provider configuration endpoint. It returns only the active country and
locale. Saving rewrites only `[providers.paypal]`'s non-secret fields, reloads
the current process configuration, and causes proxy reads to resolve the newly
selected country prefix. Other providers remain read-only on this endpoint.

## Compatibility And Rollback

- Existing callers that submit `link_type=paypal` retain US/en behavior when
  no PayPal profile has been changed.
- Existing US proxy keys remain valid and are not moved or exposed.
- Switching country does not mutate historical snapshots; it applies only to
  later Checkout attempts.
- Rollback restores `[providers.paypal]` to US/en and removes optional TH/BR
  proxy keys. No persistence migration is required.

## Test Strategy

- Unit tests cover US compatibility plus TH and BR checkout country, locale,
  currency, and dedicated proxy precedence.
- Configuration tests cover profile reads, valid saves, invalid country/locale
  rollback, masked proxy values, and runtime profile switching.
- Facade tests confirm the result remains Checkout-link-only and has no
  payment-method or confirmation artifacts.
- Console tests verify the selected profile context and responsive Settings
  page. All network boundaries use fixtures.
