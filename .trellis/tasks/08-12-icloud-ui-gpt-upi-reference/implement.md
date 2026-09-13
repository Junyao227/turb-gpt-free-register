# UI Refresh Implementation Plan

## Checklist

1. Planning
   - Treat dark mode as out of scope for this pass.
   - Keep the current single-file dashboard runtime.

2. Backend public inbox completion
   - Add public mailbox registry helpers.
   - Add `POST /api/public-mailbox/register`.
   - Complete `/console/open.php` HTML response.
   - Complete `/console/feed.php` JSON response.
   - Reuse existing forwarded IMAP parsing and verification-code extraction.

3. Frontend account/public URL support
   - Generate public open/feed URLs from current origin.
   - Add public URL fields without reusing external JSON-feed fields.
   - Register generated/synced iCloud accounts with the backend.
   - Add copy/open actions for public web and JSON URLs.
   - Add buyer URL export.

4. gpt-upi-inspired UI refresh
   - Add metric card row.
   - Refresh topbar, panels, badges, and mailbox cards.
   - Keep responsive behavior.

5. Verification
   - `node --check server.mjs`
   - Load dashboard locally.
   - Check `/api/icloud/status`.
   - Register a safe sample public mailbox and verify `feed.php` rejects wrong password.
   - Smoke check page renders without JavaScript syntax errors.

## Risky Files

- `kuozhan/icloud-hme-local-toolkit/extracted/mail-code-dashboard/server.mjs`
- `kuozhan/icloud-hme-local-toolkit/extracted/mail-code-dashboard/mail-code-dashboard.html`

## Rollback

Revert the two files above to remove UI changes and public inbox routes. Delete `runtime/public-mailboxes.json` only if the user explicitly asks because it may contain generated public lookup passwords.
