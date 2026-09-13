# plus cpa sub2api cdk management system

## Goal

Build a Plus-account management system with two roles:

- Buyers redeem a CDK in the form `cdk: random-string----mark@example.com`
- Admins upload and manage CPA / sub2api export files and CDK inventory

The system should make it easy to serve downloadable CPA and sub2api files to redeemed buyers.

## Confirmed Facts

- The repository already contains related tooling for exporting ChatGPT session data into CPA/sub2api formats.
- `kuozhan/GPTSession2CPAandSub2API` can already transform session JSON into CPA, sub2api, Cockpit, and 9router formats.
- `services/paylink` already demonstrates an admin/workbench-style UI and server pattern in this repo.
- The first implementation will use Python + FastAPI + SQLite + a simple static web UI.

## Requirements

1. Buyer flow
   - Accept a single CDK redemption string in the agreed `random-string----mark@example.com` format.
   - Validate the email as part of redemption.
   - Validate the CDK.
   - Mark the CDK as redeemed once used successfully.
   - On successful redemption, unlock both CPA and sub2api downloads for that buyer.
   - Keep a persistent download page so the buyer can download again later.
   - Use the redeemed CDK + email pair to reopen the download page; do not issue a separate redemption token.
   - Provide a direct download page with CPA and sub2api download buttons.

2. Admin flow
   - Upload CPA and sub2api files separately.
   - Create, edit, disable, and inspect CDKs.
   - View redemption history and file assignment state.
   - Protect the admin panel with a password loaded from `.env`.
   - Inspect and manage the CPA/sub2api/CDK trio attached to each record.

3. Data handling
   - Store CDK status, buyer email, assigned files, and redemption timestamps.
   - Prevent double redemption; each CDK is single-use.
   - Keep buyer-facing downloads separate from admin management actions.
   - Persist CPA / sub2api files ahead of time and serve them on redemption.
   - Each imported account record contains exactly one CPA file, one sub2api file, and one CDK.

4. Compatibility
   - Reuse existing export formats where possible instead of inventing new ones.
   - Keep the new project isolated under `kuozhan/` as its own workspace folder.
   - Allow GPT Registrator to import a selected account by email: it retrieves the real CPA JSON from CPA, then the CDK management service creates or completes the matching CDK record and stores the CPA file.
   - Protect this machine-to-machine import with a dedicated management key; it must not reuse or expose the administrator login password.

5. Initial stack
   - Use FastAPI for HTTP endpoints.
   - Use SQLite for persistent storage.
   - Use a simple static HTML/JS frontend for buyer and admin pages.

## Acceptance Criteria

- [ ] A new project folder exists under `kuozhan/` for this system.
- [ ] The folder contains a buyer/admin oriented project structure.
- [ ] The PRD captures buyer redemption and admin management requirements.
- [ ] The implementation plan can be derived from the documented scope.

## Out of Scope

- Rewriting the existing `GPTSession2CPAandSub2API` converter.
- Changing the maintained Paylink service.
- Designing a public marketplace or payment processor.
