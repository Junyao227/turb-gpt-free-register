# Ant Browser Driver Contract

## Scenario: Managed or Existing Local Profile Launch and Selenium Attach

### 1. Scope / Trigger

- Trigger: a registration driver creates a disposable Ant Browser profile or launches/reuses a configured existing profile through its LaunchServer API.
- This spans WebUI configuration, environment loading, a local HTTP API, Selenium CDP attach, and account persistence.

### 2. Signatures

```python
class AntBrowserClient:
    def open_profile(self, proxy: str | None = None) -> AntBrowserOpenResult: ...
    def build_driver(self, opened: AntBrowserOpenResult): ...
    def cleanup_profile(self, opened: AntBrowserOpenResult | None) -> None: ...

def run_ant_browser_registration(
    email: str,
    name: str,
    birthday: str,
    proxy: str | None = None,
    otp_code: str | None = None,
    batch_dir: Path | None = None,
) -> dict: ...
```

### 3. Contracts

- `ANT_BROWSER_API_BASE` defaults to `http://127.0.0.1:19876`.
- `ANT_BROWSER_PROFILE_MODE` is `managed` by default. `existing` requires `ANT_BROWSER_PROFILE_ID` and selects one exact profile; do not resolve by profile name, tag, or a multi-match selector.
- `managed` creates a distinct profile per registration with `POST /api/profiles`. The request body contains a non-email `profileName`, `tags: ["gpt-registrar", "managed"]`, and the task proxy in `profile.proxyConfig`.
- `run_ant_browser_registration` preserves an explicit task proxy. When none is supplied, it calls `config.proxy.pick_proxy()` exactly once and passes that value to `open_profile`, matching the Roxy profile-creation pattern.
- A managed profile explicitly uses `proxyId: "__direct__"` and `proxyConfig: "direct://"` only when the supplied proxy and the proxy-pool selection are both empty.
- Use the ID returned by the profile-create response directly in `POST /api/launch`; never query again by name. Do not set `autoLaunch` on creation, because a failed launch must still be cleaned up by ID.
- `ANT_BROWSER_API_KEY` is a secret and must use `ANT_BROWSER_API_KEY_HEADER`, defaulting to `X-Ant-Api-Key`.
- `GET /api/profiles/{id}/status` returns `running`, `debugReady`, `directDebugUrl`, `debugPort`, and `cdpUrl`.
- A stopped profile is started with `POST /api/launch` and `{"profileId": id}`. The registration layer performs the single navigation to `ANT_BROWSER_START_URL` after Selenium attaches.
- Selenium receives a local `host:port` debugger address, derived from `directDebugUrl`, `debugPort`, or `cdpUrl` in that order.
- `AntBrowserOpenResult` records both `started_by_run` and `created_by_run`. Persist only profile ID, name, CDP URL, and these ownership flags under `extra.ant_browser`; never persist the API key, task proxy, or an unfiltered Ant profile payload.
- `ANT_BROWSER_KEEP_BROWSER_OPEN=True` prevents managed-profile stop and deletion. Otherwise, managed profiles stop first and then delete when `ANT_BROWSER_DELETE_MANAGED_PROFILE=True` (the default). Existing profiles are never deleted.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| `existing` mode without Profile ID | Raise `AntBrowserError` before any API request. |
| Invalid profile mode | Raise `AntBrowserError` explaining the valid `managed` and `existing` values. |
| API transport, HTTP, or JSON failure | Raise a diagnostic `AntBrowserError` without API-key text. |
| Registration task has no explicit proxy | Select one normalized proxy from `PROXY_POOL` before Profile creation. |
| Explicit proxy and empty `PROXY_POOL` | Preserve the explicit proxy; only an empty selection uses direct mode. |
| Managed create response has no Profile ID | Reject before launch. |
| Launch response differs from the requested or just-created Profile ID | Reject the response. |
| `debugReady` is false or no valid endpoint exists | Reject before Selenium starts. |
| CDP host is not loopback or contains credentials | Reject it. |
| Profile already running | Reuse it and mark `started_by_run=False`. |
| Existing profile started by this run and keep-open is false | Stop it after Selenium cleanup; never delete it. |
| Managed launch or Selenium attach fails after creation | Best-effort stop then delete the created profile, without replacing the original error. |
| Managed profile completes and keep-open is false | Stop it after Selenium cleanup, then delete it when deletion is enabled. |

### 5. Good/Base/Bad Cases

- Good: managed mode selects one proxy-pool entry when needed, creates a uniquely named profile with that proxy, launches the returned ID, then stops and deletes it after registration.
- Base: existing mode reports a running, debug-ready exact profile. Reuse its `directDebugUrl` and leave it running after the registration flow.
- Bad: creation returns no ID, launch reports another profile ID, or its endpoint is remote or not debug-ready. Fail before browser automation, clean up a created profile, and leave account persistence untouched.

### 6. Tests Required

- Assert the configured API-key header is sent but its value is absent from client errors.
- Mock managed create and launch; assert the task proxy, tags, and returned ID are passed correctly, while launch requests do not contain `startUrls`.
- Assert the registration entrypoint selects one pool proxy only when an explicit task proxy is absent, then forwards the selected value to `open_profile`.
- Mock managed creation without a proxy and assert explicit direct-proxy fields are used.
- Mock existing status and launch requests; assert a running profile does not call launch and a stopped profile launches with only its exact Profile ID.
- Assert malformed or remote CDP endpoints fail.
- Assert managed cleanup calls stop before delete, and that keep-open or disabled deletion preserve the profile.
- Assert existing-profile cleanup never calls delete.
- Assert a launch failure after managed creation performs best-effort cleanup.
- Assert `main.run_registration` forwards the task proxy to the Ant registration entrypoint.

### 7. Wrong vs Correct

#### Wrong

```python
driver = webdriver.Chrome(options=Options())
client.delete_profile(profile_id)
```

This starts a new browser without Ant's profile and can delete an existing user-owned profile.

#### Correct

```python
opened = client.open_profile(proxy=task_proxy)
driver = client.build_driver(opened)
try:
    driver.get(ANT_BROWSER_START_URL)
    run_browser_flow(driver)
finally:
    driver.quit()
    client.cleanup_profile(opened)
```

The client owns endpoint validation, mode selection, and ownership-aware cleanup. Managed profiles are stopped before deletion; existing profiles are never deleted.

## Scenario: Local Chromium and ChromeDriver Compatibility

### 1. Scope / Trigger

- Trigger: Selenium reports `SessionNotCreatedException` because ChromeDriver supports a different Chromium major version than the Ant Profile started through CDP.

### 2. Signatures

```text
<Ant root>/chrome/chrome-<major>/chrome.exe --version
<Selenium cache>/chromedriver.exe --version
browser_cores(core_id, core_name, core_path, is_default)
```

### 3. Contracts

- The default Ant core used by managed Profiles and the ChromeDriver selected by Selenium must have the same major version; using the identical Chrome for Testing release is preferred.
- The current required pair is Chromium `151.0.7922.77` in `chrome/chrome-151` and ChromeDriver `151.0.7922.77`.
- Register the core in both Ant `config.yaml` and SQLite `browser_cores`, with exactly one `is_default` row.
- Preserve prior core directories and Profiles explicitly bound to them. Only newly created managed Profiles inherit the new default core.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Driver supports Chrome 151 but Profile reports 148 | Do not start registration; install/register Chrome 151, then verify an attach before retrying. |
| New archive lacks `chrome-win64/chrome.exe` or its file version differs | Do not install or register it. |
| Existing Profile explicitly uses an older `core_id` | Leave it unchanged; move it to the new core only through an explicit Profile update. |
| Ant core configuration and SQLite default disagree | Repair both before restarting LaunchServer. |

### 5. Good/Base/Bad Cases

- Good: a disposable managed Profile starts with Chromium 151 and Selenium reports ChromeDriver 151, then the Profile is stopped and deleted.
- Base: legacy Profiles remain on their explicit 148 core while new managed Profiles use the 151 default.
- Bad: replacing the 148 directory before validating 151, or changing Driver alone, causes `SessionNotCreatedException` and removes a rollback path.

### 6. Tests Required

- Read the installed `chrome.exe` and `chromedriver.exe` file versions; assert both equal `151.0.7922.77`.
- Start a disposable managed Profile, attach Selenium through CDP, and assert `browserVersion` and `chrome.chromedriverVersion` have the same release number.
- Verify the test Profile is stopped before deletion; retry cleanup only after status reports it is no longer running.

### 7. Wrong vs Correct

#### Wrong

```text
Replace chrome-148 in place and assume Selenium Manager will make any driver compatible.
```

#### Correct

```text
Install chrome-151 beside chrome-148, verify its version, set core-chrome-151 as the sole default,
restart Ant, then attach Selenium to a disposable managed Profile before production registration.
```
