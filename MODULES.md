# SOR Public Archiver 2.0 — Module Map (short)

**Full catalog:** [SOURCE.md](SOURCE.md)

**Rule:** Prefer ≤200-line production modules. Residual overs = single large methods.

## Architecture

```
gui.py → gui_app.shell.ArchiverApp
python -m scraper → scraper.cli.main

gui_app/
  shell*.py, theme, widgets*, lazy_tabs, resize_perf
  shared/ (detail_drawer/, export_card*, record_sidebar*)
  tabs/
    browse/{search,integrity,misclassify,statistics,reports,deepface_reports}/
    nsopw/, deepface/, settings/, scrape/

scraper/
  database/ (dedupe_*, csv_*, schema, …)
  nsopw/ (client_*, builder_*, search_plan, parallel)
  reports/ (fetcher_*)
  searcher_*, ethnic_names_*, cli_*, mugshot_ethnicity/
```

## Review routing

| Task | Load |
|------|------|
| Shell | `gui_app/shell*.py` |
| Browse Search | `tabs/browse/search/` |
| Reports | `tabs/browse/reports/` |
| NSOPW UI | `tabs/nsopw/` |
| NSOPW pipeline | `scraper/nsopw/builder_*.py`, `client_*.py` |
| Report fetch | `scraper/reports/fetcher_*.py` |
| Misclass engine | `searcher_*.py`, `ethnic_names_*.py` |
| Dedupe | `database/dedupe_*.py` |
| CLI | `cli_parser.py`, `cli_cmds_*.py` |

## Not from mapa

RecentlyBooked / mugshot-host arrest pipelines / arrest charge taxonomy.
