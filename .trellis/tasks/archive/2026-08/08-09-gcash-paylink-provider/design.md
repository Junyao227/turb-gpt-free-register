# GCash Paylink Provider Design

## Boundaries

The root registration application remains a facade consumer. It submits only
`token` and a public Provider type; `services/paylink/` owns the conversion to
native flow, regional network configuration, task persistence, and console
navigation.

```text
root EXTRACT_LINK_TYPE=gcash
  -> POST /api/extract
  -> provider_registry[gcash]
  -> LongLinkRequest(link_type=gcash, PH/en-PH)
  -> existing Stripe GCash path
  -> normalized facade result + task snapshot
  -> Provider-filtered Tasks / PH queue

root EXTRACT_LINK_TYPE=paypal
  -> POST /api/extract
  -> provider_registry[paypal]
  -> LongLinkRequest(link_type=paypal, US/en)
  -> existing OpenAI Checkout-link path
  -> normalized facade result + Provider-filtered Tasks
```

## Provider Identity and Configuration

The registry gains one entry with matching public and native names:

| Public type | Native type | Country | Locale | Queue |
| --- | --- | --- | --- | --- |
| `gcash` | `gcash` | `PH` | `en-PH` | `/ph-qr` |
| `paypal` | `paypal` | `US` | `en` | `/?provider=paypal&view=tasks` |

`providers.ini` owns its enable switch and non-secret PH settings. `.env` owns
`OPENAI_PAY_PH_PROXY`, `OPENAI_PAY_PH_PROXY_POOL`, and optional provider-stage
overrides. GCash selects this PH configuration before generic proxy settings;
the existing GoPay pool remains GoPay-only.

PayPal owns `OPENAI_PAY_PAYPAL_PROXY` and
`OPENAI_PAY_PAYPAL_PROXY_POOL`. The existing Checkout flow creates no
PayPal-specific Stripe submission or pending-session record; its terminal
result is the standard Checkout URL. The task list is therefore its maintained
operator surface. The standalone Thailand/Brazil protocol projects remain
outside this process boundary.

## Console and Queue

Provider tabs are already registry-driven. The home console needs a GCash
native line configuration so it renders PH/PHP defaults for `?provider=gcash`.
The new PH queue page reuses the existing provider queue surface and shared
shell; it displays GCash task/pending sessions rather than a new standalone UI.

## Proxy Configuration View

The shared shell gains a `settings` global area. It keeps Provider tabs
registry-driven: the selected public Provider resolves to a pair of environment
keys, with GCash using `OPENAI_PAY_PH_PROXY` and
`OPENAI_PAY_PH_PROXY_POOL`. The page reads a masked projection of the current
values and saves provided replacements to the local Paylink `.env` file through
an administrator-only API.

The configuration API never returns raw proxy values. A save request may carry
raw values from the operator's browser, but the server validates and writes them
atomically; logs and responses contain only configured flags, pool counts, and
masked previews. The test endpoint creates a transient request session using
the selected proxy and calls a neutral IP-echo URL. It returns timing and a
redacted outcome, without creating a checkout or calling a payment provider.

## Compatibility

The root client's valid-type tuple and operator copy add `gcash`. Existing four
providers, facade payload shape, SSE events, and stored result fields remain
unchanged. A disabled GCash section prevents job allocation exactly as the
existing providers do.

## Rollback

Setting `[providers.gcash]` or `[providers.paypal]` `enabled = false` removes
the respective tab and rejects new facade jobs. Existing snapshots remain
readable in filtered Tasks.
Configuration rollback is an atomic rewrite of the previous `.env` content;
invalid proxy input leaves the existing file unchanged.
