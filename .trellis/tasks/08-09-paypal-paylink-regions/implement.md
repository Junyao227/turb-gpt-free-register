# PayPal Regional Profile Implementation Plan

1. Add `th` locale support and a shared PayPal country-profile helper that
   validates country/locale, maps the checkout currency, and defines the
   legacy US plus dynamic country-scoped proxy environment keys.
2. Change PayPal request normalization to honor the explicit registry profile
   rather than forcing US/en. Route Checkout proxy candidate selection through
   the profile country; do not infer country from proxy text.
3. Extend the masked proxy configuration boundary so PayPal reads, writes, and
   tests the active country's dedicated environment pair. Preserve existing US
   key names as compatibility aliases.
4. Add a narrow PayPal profile configuration API that atomically updates only
   `providers.paypal` country/locale, validates profile combinations, and
   reloads runtime settings without exposing proxy values.
5. Add the PayPal profile selector to the existing Settings page. Reuse the
   shared shell and reload the masked proxy state after a profile change.
6. Update `.env.example`, README, root configuration validation/help, and the
   Paylink contract. Do not copy files from `kuozhan/` into production.
7. Add fixture-only tests for US compatibility, TH/BR profile propagation,
   regional proxy precedence, configuration validation/rollback, console
   rendering, task results, and the absence of provider confirmation calls.

## Validation

```powershell
D:\Python38\python.exe -m compileall services\paylink core\extract_link_service.py
D:\Python38\python.exe -m pytest services\paylink\tests -q
D:\Python38\python.exe -m unittest tests.test_extract_link_service
```

## Risks And Rollback

- Do not change the PayPal result lifecycle beyond Checkout URL generation.
- The selected profile, not a proxy string, owns billing country and locale.
- Keep US aliases functional throughout rollout.
- Revert by setting `[providers.paypal]` back to `US` / `en`; credentials stay
  in `.env` and require no source rollback.
