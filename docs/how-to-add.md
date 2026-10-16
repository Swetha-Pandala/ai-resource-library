# Setup and adding repositories

## Repository

The central library is https://github.com/Swetha-Pandala/ai-resource-library. Use this existing repository for all future imports; do not recreate it. Clone it to use the commands below.

GitHub Actions must be enabled with write access to repository contents for intake and refresh commits. Branch protection may require pull requests instead of direct bot commits. Fork creation is separate from publishing this library and remains pending until an authenticated fork run.

## Intake after setup
Open **Issues → New issue → Add repositories**, paste root URLs, and submit using the repository owner's account. The workflow retrieves metadata, retains history, classifies conservatively, updates generated files and commits changes. Other authors' issues do not trigger intake. Do not paste secrets into issues.

Or use Python 3.10+ from the repository root:

```bash
python -m pip install -r requirements.txt
python scripts/add_repositories.py https://github.com/owner/repository
python scripts/add_repositories.py --file links.txt
python scripts/validate_repositories.py
git add catalog categories intake README.md
git commit -m "Add resources"
git push
```

`links.txt` is one URL per line; JSON arrays are supported too. `python scripts/add_repositories.py` retries the pending queue. Stable IDs deduplicate aliases, case variants and renamed repositories. Inspection failures retain entries and error details. Submitting an existing URL may refresh its timestamp but never adds another catalog record.

## Forks
Use a securely supplied `GH_TOKEN` or `GITHUB_TOKEN` for the Swetha-Pandala account with access sufficient to list owned repositories and create forks. Do not commit tokens. The default Actions token is scoped to this library and is not assumed to have account-wide fork permissions.

```bash
python scripts/fork_repositories.py           # check existing forks only
python scripts/fork_repositories.py --create  # create missing forks; verify parent/source IDs
python scripts/validate_repositories.py
```

Commit the updated catalog and generated pages after a fork run. These commands scan paginated owned repositories to discover renamed forks, retain original names by default, and never overwrite a colliding repository. Failed or asynchronously pending forks can be retried. No automatic upstream merges occur.

Chat messages only trigger work when an authorized assistant actually invokes this intake process. There is no background connection from new ChatGPT conversations to Actions.
