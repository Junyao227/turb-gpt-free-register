# Integration design

Baseline: main@9d7964f124b8944dcf6f02c05d7d5f90d457b4a6; merge base 42ace02.
Target: upstream/main@ffcda129bbabadcaaf73974bee44c64266f364ed.
origin/main remains 78c701e; no new fork-only commits.

Use Git three-way merge with --no-commit and a local baseline safety branch.
Review each conflicting hunk against both revisions. Retain local business routes,
configuration fields, email pool lifecycle, token refresh and payment integrations;
combine upstream standalone capabilities rather than select an entire file side.
Review auto-merged shared entry points and both HTML templates for consistency.
Keep .env, data, caches and external deployments out of the integration changes.
Leave merge results reviewable locally without pushing. Preserve existing authorization
for synchronization and Trellis task workflow from the prior session.

Rollback checkpoint: codex/pre-upstream-merge-20261006 points to the baseline.
Because tracked files were clean before merge, git merge --abort can restore that baseline
while preserving the unrelated untracked page and new task artifacts.
