"""Regression tests for the shared, bounded read-only shipment connection pool."""
import os
import unittest
from unittest.mock import Mock, patch

import main


class ScopedEnginePoolTests(unittest.TestCase):
    def setUp(self):
        main.scoped_engine.cache_clear()
        self.env = patch.dict(os.environ, {
            "SHIPMENT_DB_USER": "ai_insights_reader",
            "SHIPMENT_DB_PASSWORD": "test-only",
            "SHIPMENT_DB_HOST": "localhost",
            "SHIPMENT_DB_PORT": "5432",
            "SHIPMENT_DB_NAME": "test_db",
        })
        self.env.start()

    def tearDown(self):
        main.close_scoped_engine()
        self.env.stop()

    def test_engine_is_reused_between_requests(self):
        engine = Mock()
        with patch.object(main, "create_engine", return_value=engine) as factory:
            first = main.scoped_engine()
            second = main.scoped_engine()

        self.assertIs(first, second)
        factory.assert_called_once()
        kwargs = factory.call_args.kwargs
        self.assertEqual(kwargs["pool_size"], 2)
        self.assertEqual(kwargs["max_overflow"], 2)
        self.assertEqual(kwargs["pool_timeout"], 5)
        self.assertEqual(kwargs["connect_args"]["connect_timeout"], 5)
        self.assertIn("default_transaction_read_only=on", kwargs["connect_args"]["options"])
        self.assertIn("statement_timeout=10000", kwargs["connect_args"]["options"])

    def test_shutdown_disposes_and_clears_shared_pool(self):
        engine = Mock()
        with patch.object(main, "create_engine", return_value=engine):
            self.assertIs(main.scoped_engine(), engine)
            main.close_scoped_engine()

        engine.dispose.assert_called_once()
        self.assertEqual(main.scoped_engine.cache_info().currsize, 0)


if __name__ == "__main__":
    unittest.main()
