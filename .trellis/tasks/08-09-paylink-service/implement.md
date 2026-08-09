# Unified Paylink Service Implementation Plan

1. Create `services/paylink/` by copying the OPLL2 runtime source, public
   assets, requirements, and Dockerfile. Do not copy runtime state, extracted
   archives, or embedded proxy defaults.
2. Add `.env.example`, `.gitignore`, loopback-only `docker-compose.yml`, and
   `config/providers.ini` with the four first-release provider entries.
3. Implement the provider configuration loader and provider registry. Add
   validation for unknown, disabled, and missing-required-configuration
   providers.
4. Implement the redaction utility and remove inline sensitive defaults from
   the maintained OPLL2 baseline.
5. Add the compatibility facade: create asynchronous jobs, call the existing
   OPLL2 generator, map final responses, and stream snapshot changes as SSE.
6. Register the facade in the FastAPI application without changing existing
   OPLL2 console routes or native APIs.
7. Remove the former quota configuration and update the root extract-link
   client to use the facade's request and SSE endpoints directly.
8. Update the root configuration editor copy and add launch/configuration
   documentation for the separate service.
9. Add unit tests for provider lookup, INI settings, redaction, facade job
   lifecycle, terminal SSE sequences, and the no-quota client contract.
10. Verify the copied service starts, health-check it, exercise a disabled
    provider without network generation, run focused root and service tests,
    then run the project regression suite.
11. Extend the provider registry with queue routes and an enabled-provider
    metadata projection. Expose it through `GET /api/providers` and test both
    registry and route contracts.
12. Add shared console shell CSS and JavaScript. Render stable global tabs and
    registry-backed provider tabs, hide duplicated legacy main menus, and keep
    the provider row horizontally scrollable without wrapping.
13. Wire provider query parameters into the home and debug selectors, add the
    first-release iDEAL home configuration, and map public `kakao_pay` to native
    `korea` in one frontend boundary.
14. Load the shared shell on existing operator pages, preserve direct legacy
    routes, then verify active states, provider routing, desktop layout, narrow
    viewport overflow, and browser console errors.
15. Replace the Tasks hash target with `?provider=<type>&view=tasks`. Toggle
    the existing home generation/task sections as exclusive views and preserve
    the view while switching providers; keep legacy `#tasks` recognition.
16. Add one FastAPI HTML-response cache middleware so copied console pages are
    always revalidated after upgrades while static assets retain their normal
    cache behavior. Add focused middleware and navigation regressions.
17. Restart the service and verify Generate, Tasks, provider switching, and
    `/in-qr` through normal navigation and reload on desktop and narrow widths.

## Validation Commands

```powershell
D:\Python38\python.exe -m compileall services\paylink core\extract_link_service.py
D:\Python38\python.exe -m unittest discover -s services\paylink\tests -p "test_*.py"
D:\Python38\python.exe -m unittest tests.test_extract_link_service
D:\Python38\python.exe -m unittest discover -s tests -p "test_*.py"
```

## Rollback Points

- `services/paylink/` is self-contained and can be stopped without changing
  the root registration service.
- Keeping `EXTRACT_LINK_API_BASE` empty or restoring its prior value returns
  the root application to its former external-service behavior.
- Provider modules are independently disabled through `providers.ini` without
  modifying the facade contract.
