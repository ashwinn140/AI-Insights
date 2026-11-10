"""Regression coverage for the public favicon response."""
import unittest
from main import favicon


class FaviconTests(unittest.TestCase):
    def test_favicon_is_served_as_svg(self):
        response = favicon()
        self.assertEqual(response.media_type, "image/svg+xml")
        self.assertIn("<svg", response.body.decode("utf-8"))
        self.assertEqual(response.headers.get("cache-control"), "public, max-age=86400")


if __name__ == "__main__":
    unittest.main()
