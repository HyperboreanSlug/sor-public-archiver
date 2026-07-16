"""SQLite lock retry helper tests."""
from __future__ import annotations

import sqlite3
import unittest

from scraper.database.db_retry import is_db_locked_error, retry_on_db_lock


class DbRetryTests(unittest.TestCase):
    def test_is_db_locked_error(self):
        self.assertTrue(
            is_db_locked_error(sqlite3.OperationalError("database is locked"))
        )
        self.assertTrue(
            is_db_locked_error(sqlite3.OperationalError("database is busy"))
        )
        self.assertFalse(
            is_db_locked_error(sqlite3.OperationalError("no such table: x"))
        )
        self.assertFalse(is_db_locked_error(ValueError("something else")))
        # Message-based fallback for wrapped errors
        self.assertTrue(is_db_locked_error(RuntimeError("database is locked")))

    def test_retry_succeeds_after_locks(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        logs: list[str] = []
        out = retry_on_db_lock(
            flaky,
            attempts=5,
            base_delay=0.01,
            max_delay=0.05,
            log=logs.append,
            what="test write",
        )
        self.assertEqual(out, "ok")
        self.assertEqual(calls["n"], 3)
        self.assertTrue(any("locked" in m for m in logs))

    def test_retry_gives_up(self):
        def always_locked():
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError):
            retry_on_db_lock(
                always_locked,
                attempts=3,
                base_delay=0.01,
                max_delay=0.02,
            )

    def test_non_lock_raises_immediately(self):
        calls = {"n": 0}

        def other_error():
            calls["n"] += 1
            raise sqlite3.OperationalError("no such table: foo")

        with self.assertRaises(sqlite3.OperationalError):
            retry_on_db_lock(other_error, attempts=5, base_delay=0.01)
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
