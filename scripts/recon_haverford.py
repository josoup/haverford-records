#!/usr/bin/env python3
"""
Recon for haverfordathletics.com.

Answers the four things we need before a single parser gets written:
  1. What platform runs the site (Sidearm / PrestoSports / something else)?
  2. What does robots.txt permit, and is there a sitemap?
  3. What are the sport + roster URL patterns?
  4. How far back do the season archives actually go?

Every page it fetches is saved under <out>/fixtures/ so the parsers can be
built and regression-tested against real HTML instead of guesswork.

Stdlib only -- no pip install.

    python3 recon_haverford.py
    python3 recon_haverford.py --out ./recon --delay 2.0
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://haverfordathletics.com"

# Identify ourselves honestly. If anyone in the athletics department wonders
# what this traffic is, the UA should answer the question.
UA = (
    "HaverfordAthleticsRecon/0.1 "
    "(athletics communications committee; internal records project)"
)

PLATFORM_SIGNATURES = [
    ("Sidearm Sports", [r"sidearmsports\.com", r"sidearm[-_]?sports", r"/sidearm"]),
    ("PrestoSports", [r"prestosports\.com", r"presto[-_]?sports", r"pssite"]),
    ("WMT Digital", [r"wmtdigital\.com", r"wmt[-_]?digital"]),
    ("Streamline/NeuLion", [r"neulion\.com", r"streamline"]),
]

# Only used as fallbacks if nav discovery comes up empty.
GUESS_SPORT_CODES = [
    "msoc", "wsoc", "mbkb", "wbkb", "bsb", "sball", "mlax", "wlax", "fh",
    "mxc", "wxc", "mtrack", "wtrack", "mten", "wten", "mswim", "wswim",
    "vball", "mfen", "wfen", "msquash", "wsquash", "cricket", "golf",
]


class LinkParser(HTMLParser):
    """Pulls hrefs plus a few fingerprint-y bits out of a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []  # (href, anchor text)
        self.generator = ""
        self.title = ""
        self._in_title = False
        self._pending_href: str | None = None
        self._text_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._pending_href = a["href"]
            self._text_buf = []
        elif tag == "meta" and a.get("name", "").lower() == "generator":
            self.generator = a.get("content", "")
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "a" and self._pending_href is not None:
            text = " ".join("".join(self._text_buf).split())
            self.links.append((self._pending_href, text))
            self._pending_href = None
            self._text_buf = []
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._pending_href is not None:
            self._text_buf.append(data)


class Fetcher:
    def __init__(self, out: Path, delay: float) -> None:
        self.fixtures = out / "fixtures"
        self.fixtures.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.log: list[dict] = []
        self._last = 0.0

    def get(self, url: str, *, save: bool = True) -> tuple[int, str]:
        """Returns (status, body). Never raises on HTTP errors."""
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                status = resp.status
                body = raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            status, body = e.code, ""
        except Exception as e:  # network died, DNS, timeout, TLS...
            print(f"    !! {url} -> {type(e).__name__}: {e}", file=sys.stderr)
            self.log.append({"url": url, "status": None, "error": str(e)})
            return 0, ""

        self.log.append({"url": url, "status": status, "bytes": len(body)})
        if save and body:
            name = (
                re.sub(r"[^A-Za-z0-9._-]+", "_", urllib.parse.urlparse(url).path.strip("/") or "index")[:80]
                + "-"
                + hashlib.sha256(url.encode()).hexdigest()[:8]
                + ".html"
            )
            (self.fixtures / name).write_text(body, encoding="utf-8")
        return status, body


def detect_platform(html: str, generator: str) -> list[str]:
    hits = []
    for name, patterns in PLATFORM_SIGNATURES:
        for p in patterns:
            if re.search(p, html, re.I):
                hits.append(name)
                break
    if generator:
        hits.append(f"meta[generator]={generator!r}")
    return hits or ["UNKNOWN -- inspect the saved homepage fixture by hand"]


class Tee:
    """Everything printed also lands in run.log, so nothing is lost to scrollback."""

    def __init__(self, stream, path: Path) -> None:
        self.stream = stream
        self.fh = path.open("w", encoding="utf-8")

    def write(self, data: str) -> int:
        self.stream.write(data)
        self.fh.write(data)
        self.fh.flush()
        return len(data)

    def flush(self) -> None:
        self.stream.flush()
        self.fh.flush()


def _flush(out: Path, report: dict, f: "Fetcher") -> None:
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "fetch_log.json").write_text(json.dumps(f.log, indent=2), encoding="utf-8")


def banner() -> None:
    print("=" * 68)
    print("  haverford-records site recon  v0.2")
    print(f"  python     : {sys.version.split()[0]}  ({sys.executable})")
    print(f"  platform   : {sys.platform}")
    print("=" * 68)
    if sys.version_info < (3, 9):
        print("  !! Needs Python 3.9+. Try python3.11 or python3.12 explicitly.")
        raise SystemExit(2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="./recon", type=Path)
    ap.add_argument("--delay", default=2.0, type=float,
                    help="seconds between requests (be polite; default 2.0)")
    ap.add_argument("--earliest", default=1995, type=int,
                    help="oldest season year to probe")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out / "run.log"
    tee = Tee(sys.__stdout__, log_path)
    sys.stdout = tee
    sys.stderr = tee          # the !! failure lines matter most; capture them too
    banner()
    f = Fetcher(args.out, args.delay)
    report: dict = {"base": BASE}

    # ---- 1. robots.txt -------------------------------------------------
    print("\n=== 1. robots.txt ===")
    status, robots = f.get(f"{BASE}/robots.txt", save=False)
    print(f"  status {status}")
    sitemaps: list[str] = []
    if robots:
        (args.out / "robots.txt").write_text(robots, encoding="utf-8")
        for line in robots.splitlines():
            line = line.strip()
            if re.match(r"(?i)^(user-agent|disallow|allow|crawl-delay)", line):
                print(f"    {line}")
            if re.match(r"(?i)^sitemap:", line):
                sm = line.split(":", 1)[1].strip()
                sitemaps.append(sm)
                print(f"    SITEMAP -> {sm}")
    report["robots_status"] = status
    report["sitemaps"] = sitemaps

    # ---- 2. homepage + platform ---------------------------------------
    print("\n=== 2. Homepage / platform ===")
    status, home = f.get(f"{BASE}/index.aspx")
    print(f"  status {status}, {len(home)} bytes")
    parser = LinkParser()
    if home:
        parser.feed(home)
    platform = detect_platform(home, parser.generator)
    print(f"  title: {parser.title.strip()[:90]}")
    for p in platform:
        print(f"  platform signal: {p}")
    report["platform"] = platform
    report["title"] = parser.title.strip()

    # ---- 3. sport + roster URL discovery -------------------------------
    print("\n=== 3. Sport / roster URL patterns ===")
    hrefs = []
    for href, text in parser.links:
        absolute = urllib.parse.urljoin(BASE, href)
        if urllib.parse.urlparse(absolute).netloc.endswith("haverfordathletics.com"):
            hrefs.append((absolute, text))

    roster_links = sorted({u for u, _ in hrefs if re.search(r"roster", u, re.I)})
    sport_links = sorted({u for u, _ in hrefs if re.search(r"/sports?/", u, re.I)})

    print(f"  {len(hrefs)} internal links, {len(sport_links)} sport-ish, {len(roster_links)} roster-ish")
    for u in roster_links[:15]:
        print(f"    ROSTER  {u}")
    for u in sport_links[:25]:
        print(f"    SPORT   {u}")

    # What path shape does this site use? Count the segment after /sports/.
    codes = Counter()
    for u in sport_links:
        m = re.search(r"/sports?/([A-Za-z0-9_-]+)", u)
        if m:
            codes[m.group(1)] += 1
    if codes:
        print(f"  sport path segments seen: {', '.join(sorted(codes))}")
    report["roster_links"] = roster_links
    report["sport_links"] = sport_links
    report["sport_codes"] = sorted(codes)

    # ---- 4. how far back do archives go? -------------------------------
    print("\n=== 4. Archive depth probe ===")
    # Sidearm mixes dated article paths (/sports/2025/5/16/...) in with real
    # sport slugs. Numeric segments are never sports.
    real = [c for c in sorted(codes) if not c.isdigit()]
    probe_code = real[0] if real else None
    if not probe_code:
        for guess in GUESS_SPORT_CODES:
            st, _ = f.get(f"{BASE}/sports/{guess}", save=False)
            if st == 200:
                probe_code = guess
                print(f"  nav discovery failed; guessed sport code {guess!r}")
                break

    if not probe_code:
        print("  !! Could not identify a sport code. Inspect fixtures/ by hand.")
        report["archive"] = None
    else:
        print(f"  probing sport {probe_code!r} backwards from 2026 to {args.earliest}")
        # Both common shapes; whichever returns 200s is the site's convention.
        templates = [
            f"{BASE}/sports/{probe_code}/roster/{{y}}",          # Sidearm
            f"{BASE}/sports/{probe_code}/{{y}}-{{yy}}/roster",   # PrestoSports
        ]
        found: dict[str, list[int]] = {t: [] for t in templates}
        for year in range(2026, args.earliest - 1, -1):
            for t in templates:
                url = t.format(y=year, yy=str((year + 1) % 100).zfill(2))
                st, body = f.get(url, save=(year in (2026, 2025, 2015, 2005)))
                if st == 200 and len(body) > 2000:
                    found[t].append(year)
                    print(f"    OK  {year}  {url}")
                    break
        for t, years in found.items():
            if years:
                print(f"  pattern {t}")
                print(f"    -> {len(years)} seasons, {min(years)}..{max(years)}")
        report["archive"] = {t: yrs for t, yrs in found.items() if yrs}

    # ---- 5. JSON / API discovery -----------------------------------------
    # Worth doing FIRST on every new site. Modern athletics platforms render
    # from JSON their own frontend fetches; if that endpoint is reachable,
    # scraping the HTML is doing it the hard way. A JSON feed is stable,
    # structured, and survives redesigns that shatter CSS selectors.
    print("\n=== 5. JSON / API surface ===")
    api_hints: set[str] = set()
    for pat in (
        r'["\'](/[A-Za-z0-9_/.-]*api[A-Za-z0-9_/.-]*)["\']',
        r'["\'](/[A-Za-z0-9_/.-]+\.json[A-Za-z0-9_?=&.-]*)["\']',
        r'["\'](https?://[A-Za-z0-9._-]+/[A-Za-z0-9_/.-]*api[A-Za-z0-9_/.-]*)["\']',
    ):
        api_hints.update(m.group(1) for m in re.finditer(pat, home))

    if 'application/ld+json' in home:
        print("  page embeds JSON-LD structured data (grep the homepage fixture)")
    if api_hints:
        for h in sorted(api_hints)[:20]:
            print(f"    HINT  {h}")
    else:
        print("  no inline API hints in the homepage markup")

    for probe in ("/api", "/api/v2", "/services/adaptive_components.ashx", "/sitemap.xml"):
        st, body = f.get(f"{BASE}{probe}", save=False)
        marker = "JSON" if body.strip()[:1] in "{[" else ("XML" if body.strip()[:1] == "<" else "")
        print(f"    probe {probe:45s} -> {st} {marker}")
    report["api_hints"] = sorted(api_hints)

    # ---- wrap up --------------------------------------------------------
    _flush(args.out, report, f)
    n = len(list((args.out / "fixtures").glob("*.html")))
    print(f"\nDone. {n} HTML fixtures in {args.out / 'fixtures'}")
    print(f"Report: {args.out / 'report.json'}")
    print("\nSend me report.json + a couple of the roster fixtures and I'll write the parsers.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted -- partial results kept in the out directory")
        raise SystemExit(130)
