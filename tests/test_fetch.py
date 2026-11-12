"""Transport-level tests for the 468 bot-filter fallback (no network)."""

from __future__ import annotations

import io
import subprocess
import urllib.error

import pytest

from scraper import avby

NEXT_DATA = '<script id="__NEXT_DATA__" type="application/json">{}</script>'


def _http_error(code: int, body: bytes = b"<html>blocked</html>") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://cars.av.by/filter?page=1", code, "Blocked", None, io.BytesIO(body)
    )


class _Opener:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def open(self, request, timeout=None):  # noqa: ARG002 - signature of urlopen
        raise self.error


def test_fetch_page_falls_back_to_curl_on_468(monkeypatch):
    monkeypatch.setattr(avby, "_opener", lambda: _Opener(_http_error(468)))
    monkeypatch.setattr(avby, "_fetch_with_curl", lambda url, timeout=25.0: NEXT_DATA)

    assert avby.fetch_page(1) == NEXT_DATA


def test_fetch_page_does_not_try_curl_on_plain_404(monkeypatch):
    monkeypatch.setattr(avby.time, "sleep", lambda *_: None)
    monkeypatch.setattr(avby, "_opener", lambda: _Opener(_http_error(404)))
    monkeypatch.setattr(
        avby, "_fetch_with_curl", lambda url, timeout=25.0: pytest.fail("curl must not run")
    )

    with pytest.raises(avby.ScrapeError, match="404"):
        avby.fetch_page(1)


def test_fetch_page_reports_both_transports(monkeypatch):
    monkeypatch.setattr(avby.time, "sleep", lambda *_: None)
    monkeypatch.setattr(avby, "_opener", lambda: _Opener(_http_error(468)))

    def curl_fails(url, timeout=25.0):
        raise avby.ScrapeError("curl exit 56: recv failure")

    monkeypatch.setattr(avby, "_fetch_with_curl", curl_fails)

    with pytest.raises(avby.ScrapeError) as error:
        avby.fetch_page(1)
    message = str(error.value)
    assert "468" in message
    assert "curl fallback" in message
    assert "recv failure" in message


def test_curl_fallback_requires_curl(monkeypatch):
    monkeypatch.setattr(avby.shutil, "which", lambda name: None)

    with pytest.raises(avby.ScrapeError, match="curl is not installed"):
        avby._fetch_with_curl("https://cars.av.by/filter?page=1")


def test_curl_fallback_rejects_page_without_next_data(monkeypatch):
    monkeypatch.setattr(avby.shutil, "which", lambda name: "curl")
    monkeypatch.setattr(
        avby.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=0, stdout=b"<html>no payload</html>", stderr=b""
        ),
    )

    with pytest.raises(avby.ScrapeError, match="__NEXT_DATA__"):
        avby._fetch_with_curl("https://cars.av.by/filter?page=1")


def test_curl_fallback_reports_exit_code(monkeypatch):
    monkeypatch.setattr(avby.shutil, "which", lambda name: "curl")
    monkeypatch.setattr(
        avby.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=56, stdout=b"", stderr=b"curl: (56) recv failure"
        ),
    )

    with pytest.raises(avby.ScrapeError, match="exit 56"):
        avby._fetch_with_curl("https://cars.av.by/filter?page=1")
