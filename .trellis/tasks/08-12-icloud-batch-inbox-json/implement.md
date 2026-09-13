# iCloud Batch Inbox JSON Integration Implementation Plan

## Checklist

1. Backend adapter
   - Add `POST /api/json-feed/check`.
   - Add `POST /api/json-feed/messages`.
   - Add feed URL normalization/derivation from `open.php` to `feed.php`.
   - Add external JSON decoding and `data[]` normalization.
   - Reuse existing text normalization and verification-code extraction.
   - Return the same `updates/errors/checked` shape used by current polling APIs.

2. Frontend account metadata
   - Extend import parsing to recognize open/feed URL rows without breaking old 4-column rows.
   - Extend export rows to include optional JSON open/feed URLs after existing fields.
   - Preserve existing iCloud source semantics for generated addresses.

3. Frontend polling and list integration
   - Route accounts with `jsonFeedUrl` through `/api/json-feed/check`.
   - Apply feed updates through existing `applyIncomingCode`.
   - Keep forward IMAP auto-polling intact.
   - Add manual card actions for opening web inbox URL and JSON feed URL.

4. Preview support
   - Use `POST /api/json-feed/messages` for JSON-feed accounts in `openMail`.
   - Keep existing summary fallback when a feed message cannot be loaded.

5. Verification
   - Run Node syntax/import check against `server.mjs`.
   - Run focused helper tests with a mocked local feed if practical.
   - Start the dashboard and smoke-check `http://127.0.0.1:4173/`.

## Risky files and rollback points

- `kuozhan/icloud-hme-local-toolkit/extracted/mail-code-dashboard/server.mjs`
  - Risk: external fetch error handling or malformed feed payloads.
  - Rollback: remove `/api/json-feed/*` handlers and helper functions.
- `kuozhan/icloud-hme-local-toolkit/extracted/mail-code-dashboard/mail-code-dashboard.html`
  - Risk: import/export compatibility and card action routing.
  - Rollback: remove JSON-feed parsing/actions and keep existing account fields.

## Validation commands

```powershell
node --check server.mjs
node --input-type=module -e "import('./server.mjs').then(() => console.log('server import ok'))"
npm start
```

Manual smoke checks:

- Existing dashboard loads.
- Existing iCloud-generated records still render and count normally.
- Importing a row with `open.php`/`feed.php` creates or updates one account.
- Manual receive on that account calls JSON feed and fills code/preview when the feed contains a code.
- Export includes the JSON URLs.
