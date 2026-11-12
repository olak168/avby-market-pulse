"""Diagnose why cars.av.by refuses a request: ``py scripts/probe-avby.py``.

The site sits behind a bot filter that answers unfamiliar clients with a
non-standard HTTP 468. Locally the scraper works, so the interesting question
is *what exactly* the filter dislikes about the caller. This probe compares two
transports that differ in TLS/HTTP fingerprint but share the same headers:

* ``urllib`` - what ``scraper/avby.py`` uses (Python's TLS stack, HTTP/1.1);
* ``curl``   - available on GitHub runners (OpenSSL + HTTP/2 by default).

If urllib is blocked while curl succeeds, the filter keys on the transport
fingerprint, not on the IP address, and the scraper can shell out to curl.
Both being blocked points at the datacenter IP range instead.

The script always exits 0: it is diagnostics, not a gate.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.error
import urllib.request

URL = "https://cars.av.by/filter?page=1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def _short(text: str, limit: int = 220) -> str:
    return " ".join(text.split())[:limit]


def probe_urllib() -> dict[str, str]:
    request = urllib.request.Request(URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read()
            return {
                "result": f"HTTP {response.status}",
                "size": str(len(body)),
                "server": response.headers.get("server") or "-",
                "body": _short(body.decode("utf-8", "replace")),
            }
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(400).decode("utf-8", "replace")
        except Exception:  # pragma: no cover - body already consumed
            body = ""
        return {
            "result": f"HTTP {exc.code} {exc.reason}".strip(),
            "size": "-",
            "server": exc.headers.get("server") if exc.headers else "-",
            "body": _short(body),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostics
        return {"result": f"{type(exc).__name__}: {exc}", "size": "-", "server": "-", "body": "-"}


def probe_curl() -> dict[str, str]:
    curl = shutil.which("curl")
    if not curl:
        return {"result": "curl not installed", "size": "-", "server": "-", "body": "-"}

    command = [
        curl,
        "--silent",
        "--show-error",
        "--max-time",
        "30",
        "--write-out",
        "%{http_code} %{size_download} %{content_type}",
        "--output",
        "-",
    ]
    for name, value in HEADERS.items():
        command += ["--header", f"{name}: {value}"]
    command.append(URL)

    try:
        completed = subprocess.run(command, capture_output=True, timeout=40)
    except subprocess.TimeoutExpired:
        return {"result": "curl timed out", "size": "-", "server": "-", "body": "-"}

    # --output - keeps the body in stdout, so the write-out lands at the end.
    body = completed.stdout.decode("utf-8", "replace")
    status = completed.stderr.decode("utf-8", "replace").strip()
    return {
        "result": f"exit {completed.returncode} {status}".strip(),
        "size": str(len(body)),
        "server": "-",
        "body": _short(body),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("== probe cars.av.by ==")
    for name, probe in (("urllib", probe_urllib), ("curl", probe_curl)):
        report = probe()
        print(f"\n[{name}] {report['result']}")
        print(f"  size: {report['size']}  server: {report['server']}")
        print(f"  body: {report['body']}")
    print("\n== end probe ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
