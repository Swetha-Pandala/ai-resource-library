# Maintenance

`catalog/repositories.json` is the source of truth. `categories.json` configures category names and keyword suggestions. Add any safe lowercase-hyphen slug there, then assign it to records and regenerate. No five-category limit exists. Initial categories retain the owner's grouping; future classification is conservative keyword matching, not an LLM. Ambiguous cases go to Other for review. Auto-suggested records require review before their classification is considered approved.

```bash
python scripts/sync_metadata.py
python scripts/classify_repositories.py
python scripts/generate_readme.py
python scripts/validate_repositories.py
python -m unittest discover -s tests -v
```

Refresh looks up stable GitHub IDs, retaining old URLs on transfers and renames. HTTP 404/410 means unavailable to that caller, not proven deletion. Network, authorization and rate-limit failures retain the previous verified state and last successful timestamp. `last_attempted` and `metadata_error` disclose stale data. `upstream_changed` detects changes in GitHub's pushed timestamp; it does not compare every file or merge commits. Nonarchived status does not prove active maintenance; README caveats belong in notes.

Progress is saved after each repository. Retries are bounded; waits over 60 seconds stop that operation with a resumable error. Re-run after reset. Authenticated GitHub requests are recommended for large collections. Run only one local writer at a time. GitHub workflows share a concurrency group; conflicting external pushes fail rather than force-push. Rebase and rerun after inspecting conflicts.

Refresh is manually dispatched by default. Uncomment its weekly schedule only if wanted and within your quotas. Intake does not automatically create forks; use the authenticated fork command. Validation runs within each write workflow because bot-token commits may not trigger a second workflow.

No source code from cataloged projects is executed. Issue bodies are parsed from the event file and never interpolated into shell code. Only owner-authored intake issues run. There are no PR-target privileged workflows. Review all changes to scripts/workflows before merging third-party PRs. Never execute arbitrary code taken from a catalog README.
