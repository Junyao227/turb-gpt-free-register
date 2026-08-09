# GCash Paylink Provider Implementation Plan

1. Add the `gcash` registry/config entry and PH proxy environment variables.
2. Route GCash Checkout and provider stages through the dedicated PH proxy
   selector while preserving existing GoPay behavior.
3. Add GCash to the home console line map, create the PH queue rendering
   surface, and register it with the shared shell.
4. Add `gcash` to the root client whitelist and visible configuration/action
   guidance.
5. Extend registry, proxy, facade, console, and root-client tests using only
   fixture proxy URLs and synthetic results.
6. Compile, run focused Paylink/root tests, restart the local service, and
   verify GCash generation and Tasks navigation without performing a live
   provider submission.
7. Add the registry-driven proxy configuration page and administrator-only
   masked read/save/test APIs, then cover validation and redaction with fixtures.
8. Restart the local service and verify GCash configuration navigation and
   proxy form behavior without submitting a payment.
9. Add standard PayPal to the registry, root validation, provider navigation,
   masked proxy settings, and dedicated US Checkout proxy selection. Reuse the
   existing Checkout-link path only.
10. Extend registry/proxy/facade/root/UI tests, compile, run the full Paylink
    and root suites, then verify the PayPal Tasks/configuration navigation
    without executing a standalone protocol or payment confirmation.

## Validation

```powershell
D:\Python38\python.exe -m compileall services\paylink core\extract_link_service.py
D:\Python38\python.exe -m pytest services\paylink\tests -q
D:\Python38\python.exe -m unittest tests.test_extract_link_service
```

## Rollback Points

- Disable `[providers.gcash]` to remove the service UI/API provider.
- Restore the previous root valid-type list to prevent new root jobs while
  preserving historical result records.
- Disable `[providers.paypal]` to remove the generic PayPal entry while leaving
  standalone regional protocol projects untouched.
