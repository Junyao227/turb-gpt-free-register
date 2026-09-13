# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

<!--
Document your project's database conventions here.

Questions to answer:
- What ORM/query library do you use?
- How are migrations managed?
- What are the naming conventions for tables/columns?
- How do you handle transactions?
-->

(To be filled by the team)

---

## Query Patterns

<!-- How should queries be written? Batch operations? -->

- JSON-backed queues and resource pools must make claim/release decisions while holding the shared storage lock.
- Email pool release logic must check both the pool row status and active registration jobs (`pending`, `running`, `stopping`). A failed or stopped job may release its own unconsumed email, but it must not mark an email `available` when another active job still references the same normalized email address.
- Batch list/read APIs should avoid per-row JSON reloads; load the relevant rows once and build lookup maps in memory.

## Scenario: Record file paths stay relative to `DATA_DIR`

### 1. Scope / Trigger
- Trigger: uploaded CPA / sub2api files must keep working when the database and data directory are relocated for tests, temp workspaces, or alternate deployments.
- Scope: `app/services/files.py`, `app/main.py`, and the `account_records.cpa_path` / `account_records.sub2api_path` columns.

### 2. Signatures
- `save_upload(record_id: int, kind: str, upload: UploadFile) -> tuple[str, str]`
- `GET /api/buyer/download/{record_id}/{kind}?code=...&email=...`
- Storage columns:
  - `cpa_path TEXT`
  - `sub2api_path TEXT`

### 3. Contracts
- Upload helpers store paths relative to `settings.DATA_DIR`, not `settings.PROJECT_ROOT`.
- Download handlers resolve relative paths against `settings.DATA_DIR`.
- The default on-disk layout remains `data/records/<id>/<kind>/<filename>`.

### 4. Validation & Error Matrix
- Path outside `DATA_DIR` on write -> fail fast in the upload helper.
- Stored relative path missing on disk -> `404 {kind} file missing`.
- Relocated `DATA_DIR` with existing records -> download still resolves correctly.

### 5. Good/Base/Bad Cases
- Good: `data/records/12/cpa/session.json` stored as a path under `DATA_DIR` and downloaded via the same record row.
- Base: default project-root `data/` layout works without special configuration.
- Bad: storing paths relative to `PROJECT_ROOT` and then overriding `DATA_DIR` in tests or deployment.

### 6. Tests Required
- Upload regression test should create a record under a temp `DATA_DIR` and confirm both file uploads succeed.
- Download regression test should fetch the stored CPA/sub2api files from the resolved path.
- Temp workspace test should prove `DATA_DIR` relocation does not break existing record rows.

### 7. Wrong vs Correct
#### Wrong
```python
rel_path = target.relative_to(settings.PROJECT_ROOT).as_posix()
abs_path = settings.PROJECT_ROOT / path_text
```

#### Correct
```python
rel_path = target.relative_to(settings.DATA_DIR).as_posix()
abs_path = Path(path_text)
if not abs_path.is_absolute():
    abs_path = settings.DATA_DIR / path_text
```

---

## Migrations

<!-- How to create and run migrations -->

(To be filled by the team)

---

## Naming Conventions

<!-- Table names, column names, index names -->

(To be filled by the team)

---

## Common Mistakes

<!-- Database-related mistakes your team has made -->

- Do not assume `used` in an email pool means only one job can reference that address. Failed/stopped jobs can race with pending/running jobs unless release paths exclude the current job and check other active jobs before returning the email to `available`.
