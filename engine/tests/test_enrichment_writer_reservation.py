"""WAL writer must be reserved before enrichment reads (no snapshot upgrade)."""
import pathlib
import sqlite3
import tempfile
import threading
import unittest
import uc_engine as E


class WriterReservationTests(unittest.TestCase):
    def test_waits_before_reading_reference_and_preserves_outer_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'wal.db'
            first = sqlite3.connect(path)
            first.execute('PRAGMA journal_mode=WAL')
            first.execute('CREATE TABLE items(value TEXT)')
            first.execute("INSERT INTO items VALUES('old')")
            first.commit()
            first.execute('BEGIN IMMEDIATE')
            first.execute("UPDATE items SET value='new'")
            started, entered, result, errors = threading.Event(), threading.Event(), [], []

            @E._atomic_enrichment
            def enrich(conn):
                entered.set()
                result.append(conn.execute('SELECT value FROM items').fetchone()[0])
                conn.execute("UPDATE items SET value='enriched'")

            def worker():
                conn = sqlite3.connect(path, timeout=2)
                try:
                    started.set()
                    enrich(conn)
                    self.assertFalse(conn.in_transaction)
                except BaseException as error:
                    errors.append(error)
                finally:
                    conn.close()

            thread = threading.Thread(target=worker)
            thread.start()
            self.assertTrue(started.wait(2))
            try:
                self.assertFalse(entered.wait(.1), 'must wait before reading a stale snapshot')
            finally:
                first.commit()
                thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result, ['new'])
            self.assertEqual(first.execute('SELECT value FROM items').fetchone()[0], 'enriched')
            first.execute("UPDATE items SET value='caller'")

            @E._atomic_enrichment
            def fail(conn):
                conn.execute("UPDATE items SET value='failed'")
                raise ValueError('injected')

            with self.assertRaisesRegex(ValueError, 'injected'):
                fail(first)
            self.assertTrue(first.in_transaction)
            self.assertEqual(first.execute('SELECT value FROM items').fetchone()[0], 'caller')
            first.rollback()
            self.assertEqual(first.execute('SELECT value FROM items').fetchone()[0], 'enriched')
            with self.assertRaisesRegex(ValueError, 'injected'):
                fail(first)
            self.assertFalse(first.in_transaction)
            first.close()
