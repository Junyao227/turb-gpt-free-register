# iCloud Batch Inbox JSON Integration Design

## Scope

Extend `kuozhan/icloud-hme-local-toolkit/extracted/mail-code-dashboard` so the existing dashboard can consume per-mailbox JSON inbox feeds such as:

- `open.php?mail=...&pwd=...&limit=...` for human web viewing
- `feed.php?mail=...&pwd=...&limit=...` for machine JSON polling

The implementation must keep the existing iCloud Hide My Email generator, forwarded IMAP polling, Outlook IMAP/Graph polling, local grouping, preview, and export flows working.

## Architecture

Use the existing single-file dashboard architecture:

- Backend owner: `server.mjs`
  - Adds a JSON-feed adapter API.
  - Owns external feed fetching, validation, timeout, JSON decoding, HTML-to-text normalization, and verification-code extraction.
  - Reuses existing `fetchWithRetry`, `normalizeBodyText`, `extractCode`, `applyScanOverlap`, and `mapWithConcurrency` patterns.
- Frontend owner: `mail-code-dashboard.html`
  - Stores JSON-feed metadata on the existing `state.accounts[]` records.
  - Imports/export open/feed URL records.
  - Calls the backend JSON-feed check endpoint and applies results through the existing `applyIncomingCode` path.
  - Adds card actions to open the web inbox URL and copy/open the JSON feed URL.

No database or migration is required because this dashboard already persists account state in browser `localStorage`.

## Data contracts

### Account extensions

Existing account records remain valid. JSON feed support adds optional fields:

```js
{
  source: "json-feed" | existingSource,
  jsonOpenUrl: string,
  jsonFeedUrl: string,
  jsonFeedPassword: string,
  jsonFeedLimit: number
}
```

For an existing iCloud-generated account, adding JSON feed metadata should not overwrite `source: "icloud-hme"` because iCloud stock counting depends on source/label semantics.

### Backend check request

`POST /api/json-feed/check`

```json
{
  "accounts": [{
    "email": "user@icloud.com",
    "feedUrl": "https://host/console/feed.php?mail=user%40icloud.com&pwd=secret&limit=15",
    "openUrl": "https://host/console/open.php?mail=user%40icloud.com&pwd=secret&limit=15",
    "password": "secret",
    "limit": 15,
    "lastReceivedAt": "2026-08-12T00:00:00.000Z",
    "force": false
  }]
}
```

Response follows the existing mailbox check shape:

```json
{
  "updates": [{
    "email": "user@icloud.com",
    "code": "338944",
    "subject": "OpenAI verification code",
    "preview": "plain text preview",
    "receivedAt": "2026-08-12T00:00:00.000Z",
    "method": "JSON feed",
    "noCodeReason": ""
  }],
  "errors": [{ "email": "user@icloud.com", "message": "..." }],
  "checked": [{ "email": "user@icloud.com", "checkedAt": "..." }]
}
```

### Backend message-list request

`POST /api/json-feed/messages`

Accepts one account/feed config and returns normalized feed messages for modal preview and debugging. It preserves the parsed HTML in each returned message as `html` while also returning `text`, `preview`, and extracted `code`.

## External feed normalization

Expected external JSON shape:

```json
{
  "status": "success",
  "data": [{
    "body": "<!DOCTYPE html>...",
    "from": "...",
    "saved_at": "...",
    "subject": "...",
    "to": "..."
  }]
}
```

Normalization rules:

- Accept only `http:` and `https:` URLs.
- If only `open.php` is supplied, derive `feed.php` by replacing the final path segment.
- Ensure `mail`, `pwd`, and `limit` query parameters are present when possible.
- Decode `data[].body` as raw HTML.
- Convert HTML to plain text with the existing normalizer.
- Extract verification code with the existing `extractCode` helper.
- Sort messages by normalized received time descending.
- For the check endpoint, return the newest message with a code; if none has a code, return the newest message.

## Compatibility

- Old 4-column Outlook imports remain supported.
- Old account exports remain importable.
- New JSON URL imports support:
  - `email----openUrl`
  - `email----feedUrl`
  - `email----openUrl----feedUrl`
  - combined copied text containing both open and feed URLs.
- Existing iCloud HME and forwarded IMAP polling are unchanged.
- JSON feed accounts are not included in iCloud stock counting unless they also carry the existing iCloud source/label metadata.

## Rollback

The feature is isolated to:

- `server.mjs`
- `mail-code-dashboard.html`

Rollback is a targeted revert of those changes plus deletion of these optional task artifacts. Existing localStorage entries remain safe; unsupported optional JSON fields are ignored by older frontend logic.
