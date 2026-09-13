# UI Refresh Design

## Scope

Improve the existing single-file `mail-code-dashboard` UI by borrowing the visual language from `gpt-upi` without migrating the app to Next.js.

The work also completes the server-facing public inbox URLs that support the UI requirement:

- `/console/open.php?mail=...&pwd=...&limit=...` for buyer-facing HTML inbox.
- `/console/feed.php?mail=...&pwd=...&limit=...` for buyer-facing JSON inbox.

## Architecture

- `server.mjs`
  - Owns public URL routing, mailbox password validation, forwarded IMAP lookup, JSON response rendering, and public HTML rendering.
  - Persists public mailbox credentials in `runtime/public-mailboxes.json`.
  - Never logs raw passwords, cookies, or IMAP credentials.
- `mail-code-dashboard.html`
  - Keeps the single-file HTML/CSS/JS architecture.
  - Adds `publicOpenUrl` / `publicFeedUrl` fields separate from existing `jsonOpenUrl` / `jsonFeedUrl`.
  - Uses gpt-upi-inspired cards, metric tiles, badges, and cleaner action grouping.
  - Registers generated/synced iCloud accounts with the backend so public URLs work after server deployment.

## Data Flow

```text
iCloud generator/sync
  -> frontend account record with local random public password
  -> POST /api/public-mailbox/register
  -> runtime/public-mailboxes.json
  -> buyer URL open.php/feed.php
  -> backend validates mail/pwd
  -> backend checks configured forwarding IMAP mailbox
  -> HTML or JSON response
```

## Compatibility

- Existing `jsonOpenUrl/jsonFeedUrl` stays for external feed imports.
- New `publicOpenUrl/publicFeedUrl` is for this server's buyer-facing URLs.
- Existing generated accounts keep their existing random password when present.
- Existing imports/exports remain valid; new export dedicated to buyer URLs is additive.

## Sensitive Data

- Public registry stores per-hidden-mailbox public lookup passwords only.
- It must not store iCloud cookies, IMAP app passwords, SSH credentials, or server passwords.
- Error messages should not include raw `pwd=` values.

## UI Direction

Borrow from `gpt-upi`:

- soft page background;
- sticky topbar;
- rounded metric cards;
- status badges with small colored dots;
- rounded white panels with subtle borders/shadows;
- grouped management actions;
- cleaner card hierarchy for each mailbox.

Do not add dark mode in the first pass.
