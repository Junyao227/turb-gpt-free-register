# Design: Plus CPA / sub2api CDK Management System

## 1. Overview

Build a standalone FastAPI + SQLite app under `kuozhan/plus-cpa-sub2api-cdk-management/` with two roles:

- Buyer: redeem a single-use CDK with an email, then download CPA and sub2api files.
- Buyer: redeem a single-use CDK string in the form `random-string----email@example.com`, then download CPA and sub2api files.
- Admin: upload/manage one CPA file, one sub2api file, and one generated CDK per account record.

The buyer must be able to revisit the download page later using the redeemed CDK + email pair. No extra redemption token is issued.

## 2. Core Product Decisions

- One account record maps to exactly one CPA file, one sub2api file, and one CDK.
- CDKs are single-use.
- Buyer redemption requires both CDK and email validation.
- Successful redemption unlocks both file downloads for later reuse.
- The redemption page no longer asks the buyer to choose file kinds; it opens a download page with CPA and sub2api buttons.
- Admin login password is read from `.env`.
- Files are uploaded separately, not as a bundle.

## 3. Suggested Project Layout

```text
kuozhan/plus-cpa-sub2api-cdk-management/
├── app/
│   ├── main.py
│   ├── db.py
│   ├── models.py
│   ├── auth.py
│   ├── settings.py
│   ├── services/
│   │   ├── inventory.py
│   │   ├── redeem.py
│   │   └── files.py
│   ├── templates/
│   └── static/
├── admin/
├── buyer/
├── shared/
├── data/
└── docs/
```

## 4. Data Model

### `account_records`

One row per account bundle.

- `id`
- `buyer_email`
- `cdk_code`
- `status` (`draft`, `available`, `redeemed`, `disabled`)
- `cpa_path`
- `sub2api_path`
- `cpa_filename`
- `sub2api_filename`
- `created_at`
- `updated_at`
- `redeemed_at`
- `redeemed_by_email`
- `notes`

### `redeem_events`

Immutable audit trail.

- `id`
- `record_id`
- `email`
- `action` (`lookup`, `redeem`, `download`)
- `result`
- `created_at`

## 5. Request Flow

### Buyer flow

1. Buyer opens `/`.
2. Buyer submits `random-string----email@example.com`.
3. Server parses and validates code + email.
4. Server checks that the record exists and is not already redeemed.
5. On first success, the record transitions to `redeemed`.
6. Buyer sees a persistent download page with CPA and sub2api buttons.
7. The same pair can be used later to reopen the download page.

### Admin flow

1. Admin opens `/admin`.
2. Admin logs in with the password from `.env`.
3. Admin uploads CPA and sub2api files separately.
4. Admin creates or updates the record and auto-generates the CDK random string.
5. Admin can disable a record or inspect redemption history.

## 6. API Surface

- `POST /api/admin/login`
- `POST /api/admin/logout`
- `GET /api/admin/records`
- `POST /api/admin/records`
- `PUT /api/admin/records/{id}`
- `POST /api/admin/records/{id}/upload-cpa`
- `POST /api/admin/records/{id}/upload-sub2api`
- `POST /api/admin/records/{id}/generate-cdk`
- `POST /api/buyer/redeem`
- `POST /api/buyer/lookup`
- `GET /api/buyer/records/{id}/download/{kind}`

`kind` is `cpa` or `sub2api`.

## 7. Storage / File Handling

- SQLite stores only metadata and paths.
- Uploaded files are saved under `data/records/<id>/`.
- Filenames are sanitized before saving.
- A record is not redeemable until both files and the CDK are present.

## 8. Security

- Admin auth uses a password from `.env`.
- Buyer lookup is limited to matching CDK + email.
- No extra redemption token is issued.
- Download endpoints verify record state before streaming files.
- Secrets, raw file contents, and full CDKs are not logged.

## 9. Trade-offs

- Reusing the CDK + email pair is simpler than issuing a second token.
- Persisting files ahead of time makes retry/re-download easy.
- Separate uploads reduce file-association mistakes.
- SQLite is enough for the first version because the workflow is record-centric and local.

## 10. Acceptance Mapping

- Buyer can redeem with CDK + email.
- Buyer can choose CPA, sub2api, or both.
- Both files become available after redemption.
- Download page can be revisited later with the same CDK + email pair.
- Admin can upload/manage records and CDKs.
- Admin password comes from `.env`.

## 11. GPT Registrator Integration

- GPT Registrator stores `CDK_MGMT_MANAGEMENT_URL`, `CDK_MGMT_MANAGEMENT_KEY`, and a request timeout in its local `.env` through the existing runtime configuration UI.
- The CDK management service stores the same key as `CDK_MGMT_MANAGEMENT_KEY`; it accepts the key through `Authorization: Bearer` or `X-Management-Key` only on `POST /api/management/import-cpa`.
- The caller first resolves the selected local credential's email, downloads the matching real CPA JSON from CPA auth-files, then submits a multipart request containing the email and CPA file.
- The management service validates that the CPA JSON email matches the request email. It creates a record only when no record exists; an existing CPA record is idempotently reported without issuing a new CDK. Redeemed and disabled records cannot be changed.
- The import API returns only record metadata needed by the caller, never the CDK or raw credential content. sub2api conversion remains an explicit management-side action.
