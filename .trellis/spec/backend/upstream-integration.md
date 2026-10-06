# Upstream / local integration contracts

## 1. Scope / Trigger
Apply when merging upstream changes into the locally extended registrator.
Textual auto-merge success does not establish behavior compatibility.

## 2. Signatures
- `normalize_proxy_url(value: str, default_scheme: str = "http") -> str`
- `normalize_proxy_list(values, default_scheme: str = "http") -> list[str]`
- `BrowserSession(proxy=..., detect_exit_geo=False)` exposes `proxy_target` and transport proxies.
- `post_register_dwell(email, *, label="注册后", seconds_range=None)` retains explicit overrides.
- `twofa_service.apply_settings()` updates the live logical worker and queue limits.
- `EDITABLE_FIELDS` has exactly one entry for each key.

## 3. Contracts
- Preserve local CDK, email pool lifecycle, Pay153 and Paylink routes, storage and config fields.
- Keep local provider-specific SMS settings and legacy fallback isolation when adding upstream SMSBower options.
- Proxy list normalization supports both upstream shorthand variants and local IPv6, password-colon and credential-encoding behavior.
- Explicit BrowserSession proxies initialize both target and transport; pool chains retain the original target for persistence.
- HTML controls have unique static IDs and one action binding; module-level Python functions are defined once.
- Twofa executor capacity is 16; configured active concurrency is enforced by the condition gate and can change without replacing the executor.
- Captured `sentinel/sdk.js` uses LF bytes under `.gitattributes` to preserve the upstream SHA-256 fixture on Windows.
- `.env.example` adds keys without copying deployment-specific proxy endpoints or supplier filters.

## 4. Validation & Error Matrix
| Condition | Expected behavior |
| --- | --- |
| Bare IPv6 `[::1]:8080` | `http://[::1]:8080`, never username/password reordering |
| Proxy credentials contain `@` or spaces in four-part shorthand | Encode credentials before parsing the URL |
| Explicit dwell `0,0` | No sleep, even if the default range is nonzero |
| Logical TWOFA_WORKERS increases | Existing executor remains and gate wakes waiting jobs |
| Duplicate controls, functions or editable keys after auto-merge | Resolve before accepting the integration |
| Windows checkout of captured SDK | LF content and upstream hash remain identical |

## 5. Good / Base / Bad Cases
- Good: dedicated plan proxy pools normalize legacy entries while masking credentials in API summaries.
- Base: empty plan pools retain general-pool/direct routing semantics.
- Bad: retaining both implementations makes a later Python definition silently shadow a newer signature.

## 6. Tests Required
- `tests/test_october_merge_compatibility.py`: unique fields/controls, dwell override, proxy encoding, explicit transport and plan pools.
- `tests/test_twofa_service_settings.py`: live limit updates, minimum queue capacity and executor identity.
- `tests/test_roxybrowser_client.py`: disable create-slot pacing in busy-retry unit tests to isolate retry sleep counts.
- Parse both inline JavaScript templates with Node, then smoke-test modern/legacy pages and account API.
- Run root tests and `services/paylink` tests separately.

## 7. Wrong vs Correct
Wrong: choose one side of the whole config/proxy file, discard local URL masking,
or leave duplicate `post_register_dwell` definitions after an auto-merge.

Correct: retain one normalizer, merge list support, preserve original-target metadata,
and keep the single dwell helper with `seconds_range` support. Assert behavior at
these boundaries, not merely the presence of upstream source text.
