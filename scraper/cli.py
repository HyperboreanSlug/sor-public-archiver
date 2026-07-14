"""CLI entry re-export (commands live in cli_cmds_*)."""
from __future__ import annotations

from scraper.cli_parser import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
