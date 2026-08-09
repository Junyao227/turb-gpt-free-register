# Twint Paylink Provider Implementation Plan

1. Add public `twint -> swiss` to `paylink.provider_registry` and add the CH
   provider section to `services/paylink/config/providers.ini`.
2. Map Twint to the existing Swiss proxy fallback/pool in the masked proxy
   configuration contract and environment example.
3. Ensure console metadata, provider-filtered Tasks, and `/ch-qr` queue routing
   resolve public Twint while preserving native `swiss` snapshots.
4. Add `twint` to root extract-link validation and operator copy.
5. Extend registry, facade, proxy, configuration, queue, console, and root
   tests with fixture values only.
6. Run compilation and the full Paylink plus root extract-link suites. Restart
   the local service and verify Provider, Tasks, Settings, and `/ch-qr`
   navigation without live payment submission.

## Validation

```powershell
D:\Python38\python.exe -m compileall services\paylink core\extract_link_service.py
D:\Python38\python.exe -m pytest services\paylink\tests -q
D:\Python38\python.exe -m unittest tests.test_extract_link_service
```

## Rollback

- Set `[providers.twint] enabled = false` to remove the public Provider.
- Restore the root valid type list to reject new `twint` jobs while preserving
  existing Swiss task and queue records.
