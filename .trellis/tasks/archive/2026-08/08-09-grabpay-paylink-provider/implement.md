# GrabPay Paylink Provider Implementation Plan

1. Add `grabpay` to the provider registry and `providers.ini` with `PH` / `en`
   metadata and `/?provider=grabpay&view=tasks` navigation.
2. Define and load dedicated `OPENAI_PAY_GRABPAY_PROXY` and
   `OPENAI_PAY_GRABPAY_PROXY_POOL` settings. Expose both exclusively through
   the existing masked proxy configuration API and `.env.example`.
3. Make Checkout and provider-stage selection choose GrabPay candidates before
   generic PH fallbacks while keeping an explicit request proxy first and
   excluding GoPay's configuration from the GrabPay path.
4. Add GrabPay to root extract-link validation and visible operator help,
   retaining the existing submit-and-consume event contract.
5. Verify registry-driven console navigation remains shared and the Provider,
   Tasks, and Settings areas preserve the selected GrabPay context.
6. Add fixture-only tests for registry/config, config masking and runtime
   updates, PH proxy precedence at both stages, normalized facade outcomes,
   task filtering, console navigation, and root validation.
7. Run the Paylink and root extract-link suites, inspect the provider pages in
   the local service, and confirm no live payment or credential is used.

## Validation

```powershell
D:\Python38\python.exe -m compileall services\paylink core\extract_link_service.py
D:\Python38\python.exe -m pytest services\paylink\tests -q
D:\Python38\python.exe -m unittest tests.test_extract_link_service
```

## Risk And Rollback

- Keep the fallback ordering branch-specific: a GrabPay configuration must not
  alter GCash or GoPay selection.
- Do not expose raw values while rendering, saving, or testing proxy settings.
- Roll back by disabling `[providers.grabpay]` and removing the GrabPay
  environment-key wiring; native historical task snapshots remain readable.
