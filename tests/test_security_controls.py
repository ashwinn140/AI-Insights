"""Regression tests for same-origin mutation protection."""
import unittest

from fastapi import HTTPException
from starlette.requests import Request

from main import same_origin


def make_request(origin, host, scheme="https"):
    headers = [(b"host", host.encode("ascii"))]
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": scheme,
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "server": ("example.test", 443),
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


class SameOriginTests(unittest.TestCase):
    def test_https_same_origin_is_allowed(self):
        same_origin(make_request("https://insights.example.com", "insights.example.com"))

    def test_local_http_is_allowed_only_for_loopback(self):
        same_origin(make_request("http://localhost:8000", "localhost:8000", "http"))

    def test_cross_origin_is_rejected(self):
        with self.assertRaises(HTTPException):
            same_origin(make_request("https://attacker.example", "insights.example.com"))

    def test_localhost_origin_cannot_bypass_remote_host_check(self):
        with self.assertRaises(HTTPException):
            same_origin(make_request("http://localhost:8000", "insights.example.com:8000"))

    def test_missing_origin_is_rejected(self):
        with self.assertRaises(HTTPException):
            same_origin(make_request(None, "insights.example.com"))


if __name__ == "__main__":
    unittest.main()
