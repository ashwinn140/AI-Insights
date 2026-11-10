"""Regression coverage for the public favicon asset."""
import unittest
from fastapi.testclient import TestClient


class FaviconTests(unittest.TestCase):
    def test_favicon_is_served_as_svg(self):
        from main import app
        with TestClient(app) as client:
            response = client.get("/favicon.ico")
        self.assertEqual(response.status_code, 200)
        self.assertIn("image/svg+xml", response.headers.get("content-type", ""))
        self.assertIn("<svg", response.text)
        self.assertIn("Cache-Control", response.headers)


if __name__ == "__main__":
    unittest.main()
