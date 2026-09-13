# Logging Guidelines

> How logging is done in this project.

---

## Overview

<!--
Document your project's logging conventions here.

Questions to answer:
- What logging library do you use?
- What are the log levels and when to use each?
- What should be logged?
- What should NOT be logged (PII, secrets)?
-->

(To be filled by the team)

---

## Scenario: redeem event logs stay human-readable and Chinese

### 1. Scope / Trigger
- Trigger: admin-visible event history needs to explain what happened without opening raw database rows.
- Scope: `redeem_events.detail`, `redeem_events.payload_json`, and the admin event list projection.

### 2. Signatures
- `log_event(record_id: int, event_type: str, detail: str, payload: dict[str, Any] | None = None, *, conn: sqlite3.Connection | None = None) -> None`
- `GET /api/admin/events?limit=...`

### 3. Contracts
- `detail` is the primary human-readable message.
- `payload_json` must include the stable machine fields needed for replay/debug:
  - `buyer_email`
  - `redeem_code`
  - `redeem_string`
  - `filename` for uploads
  - `choice` for redemption
- Admin UI should render the human summary first and the raw event type second.

### 4. Validation & Error Matrix
- Create event -> show `记录已创建：邮箱 ...，兑换字符串 ...`.
- CDK regen -> show `兑换字符串已重新生成：邮箱 ...，兑换字符串 ...`.
- CPA/sub2api upload -> show `... 文件已上传：邮箱 ...，兑换字符串 ...，文件 ...`.
- Redeem -> show `买家已兑换：邮箱 ...，兑换字符串 ...，选择 ...`.

### 5. Good/Base/Bad Cases
- Good: an operator can read the admin timeline without opening the database.
- Base: payload still carries structured fields for later debugging or filtering.
- Bad: leaving only English placeholder text such as `record created` or `code generated`.

### 6. Tests Required
- Event list test should assert the API returns joined record metadata with the event row.
- UI test should confirm the admin timeline shows the Chinese summary for create/upload/redeem events.
- Regression test should ensure upload events include the originating email and redeem string.

### 7. Wrong vs Correct
#### Wrong
```python
log_event(record_id, "create", "record created", {"buyer_email": email}, conn=conn)
```

#### Correct
```python
log_event(
    record_id,
    "create",
    f"记录已创建：邮箱 {email}，兑换字符串 {code}----{email}",
    {"buyer_email": email, "redeem_code": code, "redeem_string": f"{code}----{email}"},
    conn=conn,
)
```

---

## Log Levels

<!-- When to use each level: debug, info, warn, error -->

(To be filled by the team)

---

## Structured Logging

<!-- Log format, required fields -->

(To be filled by the team)

---

## What to Log

<!-- Important events to log -->

(To be filled by the team)

---

## What NOT to Log

<!-- Sensitive data, PII, secrets -->

(To be filled by the team)
