# Public SOR Data Archiver

Tools for archiving and searching **publicly available** U.S. sex offender registry data.

> **Legal / ethical note:** This project only targets data that jurisdictions already publish for public safety. Respect each site’s terms of use, rate limits, and robots rules. Do not mass-scrape NSOPW or other services that prohibit automated access. Scraped/exported files can contain sensitive personal data — keep them private and never commit them to git.

## Features

- **Direct bulk downloads** for jurisdictions that publish files (AZ, DC, GA)
- **Best-effort HTML scrapers** for other states (often return little without site-specific work)
- **SQLite search** by name, race, and state
- **Surname / race mismatch flagging** using configurable ethnic surname lists
- **GUI** (`python gui.py`) and **CLI** (`python -m scraper` / `python archiver.py`)

## Requirements

- Python 3.10+
- Dependencies in `requirements.txt`

```bash
pip install -r requirements.txt
```

## Quick start

### Simple bulk archiver (known direct URLs only)

```bash
python archiver.py list
python archiver.py download --all-direct
python archiver.py download --states AZ,DC,GA
```

Files land under `archives/YYYY-MM-DD/`.

### Full scraper + database CLI

```bash
# Bulk-download states only
python -m scraper scrape --direct-only

# Import CSVs into SQLite
python -m scraper import --input data/downloads

# Search / stats
python -m scraper search
python -m scraper search --name "Garcia"
python -m scraper search --state FL --race WHITE

# Surname/race mismatch analysis
python -m scraper misclassify --ethnicity hispanic --confidence 0.5

# Export
python -m scraper export --output results.csv --state FL
```

### GUI

```bash
python gui.py
```

### Standalone Windows EXE

```bash
pip install pyinstaller
python build_exe.py
```

Copy the entire `dist/SOR-Public-Archiver/` folder (not just the `.exe`).

## Project layout

```
├── archiver.py           # Direct-download CLI
├── core.py               # Shared download helpers
├── gui.py                # Tkinter UI
├── build_exe.py          # PyInstaller helper
├── sources.json          # Registry URLs + bulk links
├── requirements.txt
├── LICENSE
├── scraper/
│   ├── cli.py
│   ├── config.py
│   ├── database.py
│   ├── searcher.py
│   ├── ethnic_names.py
│   ├── ethnic_names.json
│   └── scrapers/         # direct | api | html | hybrid
└── tests/
    └── test_smoke.py
```

## Direct bulk sources

| Abbr | Notes |
|------|--------|
| AZ | Published CSV |
| DC | Open data portal CSV |
| GA | GBI published CSV |

Most other jurisdictions only expose interactive search pages. HTML scraping is best-effort.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Configuration

- Registry list: `sources.json` and `scraper/config.py`
- Surname lists: `scraper/ethnic_names.json` (loaded at runtime)

## License

MIT — see [LICENSE](LICENSE).
