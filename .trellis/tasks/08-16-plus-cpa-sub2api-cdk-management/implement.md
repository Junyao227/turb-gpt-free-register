# Implementation Plan: Plus CPA / sub2api CDK Management System

## 1. Scaffold the app

- Create the FastAPI app package under `kuozhan/plus-cpa-sub2api-cdk-management/app/`.
- Add `main.py`, `settings.py`, `db.py`, `models.py`, and service modules.
- Add basic buyer/admin templates and static assets.

## 2. Define the data layer

- Create SQLite schema for account records and redemption events.
- Add helpers for insert, lookup, update, disable, and audit logging.
- Add file-path helpers for record storage under `data/records/<id>/`.

## 3. Build admin auth

- Load admin password from `.env`.
- Add login/logout and protected admin routes.
- Verify unauthorized requests are rejected before admin actions run.

## 4. Build admin inventory management

- Add record creation/editing.
- Add separate CPA upload and sub2api upload handlers.
- Add auto CDK generation.
- Add record status controls (`draft`, `available`, `redeemed`, `disabled`).

## 5. Build buyer redemption flow

- Parse `cdk: random-string----email@example.com`.
- Validate code/email against the stored record.
- Prevent double redemption.
- Mark the record redeemed on first successful use.
- Render a persistent download page with CPA and sub2api buttons.

## 6. Build download endpoints

- Stream the stored CPA file.
- Stream the stored sub2api file.
- Re-check the pair before every download.
- Return clear errors for mismatched pair, missing file, disabled record, or already-used invalid state.

## 7. Add browser-facing UI

- Buyer page: redemption form, status, download links, reuse form.
- Admin page: login, record table, upload forms, CDK controls, audit trail.
- Keep the UI minimal and static-first.

## 8. Add tests

- Validate CDK/email parsing and normalization.
- Validate single-use redemption.
- Validate repeat download using the same CDK + email pair.
- Validate admin auth.
- Validate separate CPA/sub2api uploads and retrieval.
- Validate disabled and missing-file cases.

## 9. Verification commands

Run from the repository root:

```powershell
pytest
```

After the app exists:

```powershell
python -m uvicorn kuozhan.plus-cpa-sub2api-cdk-management.app.main:app --reload
```

Manual checks:

- Open buyer page and redeem one sample record.
- Reopen the download page with the same CDK + email pair.
- Log in as admin, upload files, and confirm downloads work.

## 10. Rollback points

- Database schema and file-path helpers.
- Redemption state transition logic.
- Download authorization checks.
- Admin upload/save handlers.

## 11. GPT Registrator Import Integration

- Add CDK management URL/key/timeout fields to the existing Codex runtime configuration UI; write the key to `.env` only.
- Add a dedicated CDK management key and a protected multipart CPA import endpoint.
- Validate CPA JSON and email before saving; preserve manual record/file actions.
- Add a Codex authorization bulk action that resolves each selected record from CPA auth-files, invokes the management endpoint, and returns per-record success/failure results.
- Test unauthorized access, first import, idempotent re-import, email mismatch, client request shape, and modern UI binding.
