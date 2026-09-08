# Google Scholar publication sync

The Publications page renders `_data/scholar_publications.json` with year groups, author emphasis, venue details, and links to individual Google Scholar records. Profile: https://scholar.google.com/citations?user=Qv2IRBkAAAAJ&hl=en.

The `Sync Google Scholar publications` workflow checks once daily at 22:17 UTC (06:17 China Standard Time), on relevant implementation changes, or through manual dispatch. It uses only Python's standard library and the repository's built-in GitHub token; no paid API, private credentials, or browser session is required. After saving the verified snapshot, it explicitly requests a GitHub Pages build because commits made with GITHUB_TOKEN do not trigger one automatically.

One public profile request with pagesize=100 is made per run. The script does not crawl pagination, bypass challenges, or use proxies. It requires the expected profile name/ID, complete pagination state, valid metadata, unique IDs, and a nonempty list. Network failures, blocked responses, incomplete lists, and an unexpected loss of more than 20% of entries preserve the last valid snapshot and fail the workflow for review. If the profile eventually exceeds 100 entries or a large removal is intentional, review the source and adjust the import deliberately; do not disable these guards merely to make a failing run pass.

`checked_on` records the last successful daily check in China Standard Time; `updated_on` records the last metadata change. Google Scholar can block automated access, and GitHub can delay scheduled jobs; this is daily polling, not an immediate push notification. GitHub can disable schedules after 60 days without repository activity; successful daily snapshot updates provide normal activity. Review failed workflow notifications if updates stop.

Run `python scripts/sync_scholar.py`, or pass `--html path/to/profile.html` for an already downloaded complete profile. Run `python -m unittest discover -s tests -p 'test_scholar_sync.py'` for the parser and preservation tests.
