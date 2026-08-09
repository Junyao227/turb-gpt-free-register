# GoPay Paylink Provider Implementation Plan

1. Add `gopay` to the public provider registry and `providers.ini` with
   `ID` / `id`, using `/?provider=gopay&view=tasks` instead of `/id-qr`.
2. Expose the maintained `OPENAI_PAY_GOPAY_PROVIDER_PROXY` and
   `OPENAI_PAY_GOPAY_PROVIDER_PROXY_POOL` through the existing masked proxy
   configuration API and `.env.example`.
3. Add GoPay to root extract-link validation and operator help without changing
   its POST payload or SSE event contract.
4. Confirm the shared console retains native GoPay selection and routes
   Generate, Tasks, and Settings through registry metadata.
5. Add fixture-only registry, facade, proxy, task-filtering, console, and root
   validation tests. Preserve the existing approval-only tests and explicitly
   reject provider-pending queue usage.
6. Compile, run the Paylink and root extract-link suites, restart the local
   service, and verify GoPay navigation without a live provider submission.

## Validation

```powershell
D:\Python38\python.exe -m compileall services\paylink core\extract_link_service.py
D:\Python38\python.exe -m pytest services\paylink\tests -q
D:\Python38\python.exe -m unittest tests.test_extract_link_service
```

## Rollback

- Set `[providers.gopay] enabled = false` to remove the public provider.
- Remove `gopay` from the root valid type list to stop new facade jobs while
  preserving historical native task snapshots.
