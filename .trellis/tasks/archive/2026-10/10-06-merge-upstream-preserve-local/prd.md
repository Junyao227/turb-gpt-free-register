# October upstream synchronization

## Requirements
- Integrate upstream/main at ffcda129bbabadcaaf73974bee44c64266f364ed into the local main working tree.
- Preserve local CDK management, email pool, Pay153, payment/Paylink features and existing configuration/data.
- Preserve unrelated untracked pelican-cycle.html.
- Resolve both textual conflicts and behavioral integration mismatches.
- Validate upstream additions and local extension compatibility. Do not push remote changes.

## Acceptance
- No unresolved Git entries or conflict markers in source files.
- Upstream proxy, 2FA, account export, pagination, liveness and browser changes are present alongside local features.
- Root and Paylink tests pass, or exact environment/test limitations are documented.
- Record baseline, target, resolutions and verification for review.
