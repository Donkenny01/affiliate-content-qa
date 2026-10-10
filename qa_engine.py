"""Affiliate article QA scanner. Uses public HTML; no Amazon scraping or price/stock checks."""
from __future__ import annotations
import concurrent.futures
import ipaddress
import re
import socket
from dataclasses import dataclass, asdict
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs, unquote, urldefrag

import requests
from bs4 import BeautifulSoup

UA = "AffiliateArticleQA/1.0 (+manual site audit)"
AMAZON_HOST = re.compile(r"(^|\.)(amazon\.(com|co\.uk|ca|de|fr|it|es|co\.jp|com\.au|in|com\.mx|com\.br|nl|se|pl|ae|sa|sg|com\.tr|eg|be)|amzn\.to|amzn\.eu|amzn\.asia)$", re.I)
ASIN_URL = re.compile(r"/(?:dp|gp/product|gp/aw/d|exec/obidos/ASIN)/([A-Z0-9]{10})(?:[/?#]|$)", re.I)
ASIN_TEXT = re.compile(r"\b(?:ASIN\s*[:#-]?\s*)([A-Z0-9]{10})\b", re.I)
AFFILIATE_DISCLOSURE = re.compile(r"(as an amazon associate|earn(?:s|ing)? from qualifying purchases|affiliate links?|commission (?:at no|if you)|may earn (?:a )?commission)", re.I)
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

@dataclass
class Issue:
    severity: str
    rule: str
    detail: str
    location: str = ""
    url: str = ""

@dataclass
class LinkRecord:
    number: int
    anchor: str
    href: str
    destination: str
    link_type: str
    section: str
    asin: str
    affiliate_tag: str
    rel: str
    status: str = "Not checked"
    final_url: str = ""


def allowed_url(url: str) -> bool:
    """Reject local/metadata targets (including DNS hostnames resolving to private IPs)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in ("localhost", "localhost.localdomain") or hostname.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (OSError, ValueError):
        return False


def request_public(url: str, *, method: str = "GET", timeout: int = 12):
    # Manually follow redirects to validate each hop and avoid private-address redirects.
    with requests.Session() as session:
        session.trust_env = False  # Prevent untrusted proxy environment settings
        for _ in range(6):
            if not allowed_url(url):
                raise ValueError(f"Non-public or unsupported URL blocked: {url}")
            response = session.request(method, url, headers=HEADERS, timeout=timeout, allow_redirects=False, stream=True)
            if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("Location"):
                new_url = urljoin(url, response.headers["Location"])
                response.close()
                url = new_url
                if response.status_code == 303:
                    method = "GET"
                continue
            return response
    raise ValueError("Too many redirects")


def amazon_details(url: str):
    p = urlparse(url)
    if not AMAZON_HOST.search((p.hostname or "").lower()):
        return "", ""
    match = ASIN_URL.search(unquote(p.path))
    tag = (parse_qs(p.query).get("tag") or [""])[0]
    return (match.group(1).upper() if match else ""), tag


def section_for(a):
    for prev in a.find_all_previous(["h2", "h3", "h4"], limit=1):
        return prev.get_text(" ", strip=True)[:180]
    return "Introduction / unsectioned"


def audit_article(article_url: str, expected_tag: str = "", check_status: bool = False, max_link_checks: int = 100):
    issues = []
    if not allowed_url(article_url):
        raise ValueError("Enter a publicly reachable http(s) article URL.")
    response = request_public(article_url)
    try:
        response.raise_for_status()
        ctype = response.headers.get("Content-Type", "")
        if "html" not in ctype.lower():
            raise ValueError(f"URL does not return HTML: {ctype}")
        html = response.content[:8_000_000]
        final_article_url = response.url
    finally:
        response.close()
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find("article") or soup.body or soup
    document_text = soup.get_text(" ", strip=True)
    if not AFFILIATE_DISCLOSURE.search(document_text):
        issues.append(Issue("Warning", "Disclosure", "No recognizable affiliate disclosure found in page text."))
    if not soup.find("h1"):
        issues.append(Issue("Warning", "Content", "Missing H1 heading."))
    if not soup.find("meta", attrs={"name": re.compile("^description$", re.I)}):
        issues.append(Issue("Info", "SEO", "Meta description not detected."))

    records = []
    page_host = urlparse(final_article_url).hostname or ""
    for i, a in enumerate(main.find_all("a", href=True), 1):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = urldefrag(urljoin(final_article_url, href))[0]
        scheme = urlparse(url).scheme
        if href.startswith("#"):
            kind = "Fragment"
        elif scheme not in ("http", "https"):
            kind = "Other"
        elif AMAZON_HOST.search((urlparse(url).hostname or "").lower()):
            kind = "Amazon"
        elif (urlparse(url).hostname or "").lower().removeprefix("www.") == page_host.lower().removeprefix("www."):
            kind = "Internal"
        else:
            kind = "External"
        asin, tag = amazon_details(url)
        rec = LinkRecord(i, a.get_text(" ", strip=True)[:200] or (a.get("aria-label") or "[image/empty anchor]"), href, url, kind, section_for(a), asin, tag, " ".join(a.get("rel", [])))
        records.append(rec)
        loc = f"Link #{i} · {rec.section}"
        if kind == "Amazon":
            if (urlparse(url).hostname or "").lower().startswith(("amzn.to", "amzn.eu", "amzn.asia")):
                issues.append(Issue("Info", "Short link", "Short Amazon URL: ASIN and tag cannot be verified without resolving the redirect.", loc, url))
            else:
                if not tag:
                    issues.append(Issue("Fail", "Amazon tag", "Amazon link has no affiliate tag parameter.", loc, url))
                elif expected_tag and tag.lower() != expected_tag.lower():
                    issues.append(Issue("Fail", "Amazon tag", f"Found tag '{tag}', expected '{expected_tag}'.", loc, url))
                if not asin:
                    issues.append(Issue("Warning", "Amazon ASIN", "ASIN not detectable in the link path. This may be a search/category URL.", loc, url))
            if not rec.anchor.strip() or rec.anchor == "[image/empty anchor]":
                issues.append(Issue("Warning", "CTA", "Amazon link has no readable anchor text.", loc, url))
        if scheme in ("http", "https") and not allowed_url(url):
            issues.append(Issue("Warning", "URL safety", "Destination is not a publicly resolvable URL; link status will not be checked.", loc, url))
        # Flag obvious ASIN disagreement where section heading explicitly contains an ASIN
        stated = ASIN_TEXT.search(rec.section)
        if kind == "Amazon" and asin and stated and stated.group(1).upper() != asin:
            issues.append(Issue("Fail", "ASIN discrepancy", f"Section references {stated.group(1).upper()} but link references {asin}.", loc, url))
    # Same anchor/product label linking to multiple ASINs could indicate wrong products.
    by_label = {}
    for rec in records:
        if rec.link_type == "Amazon" and rec.asin and rec.anchor and rec.anchor != "[image/empty anchor]":
            label = re.sub(r"\s+", " ", rec.anchor.strip().lower())
            if len(label) >= 8 and label not in ("check price on amazon", "view on amazon", "buy on amazon", "check price", "shop now"):
                by_label.setdefault(label, set()).add(rec.asin)
    for label, asins in by_label.items():
        if len(asins) > 1:
            issues.append(Issue("Warning", "Product discrepancy", f"Identical link text '{label[:70]}' points to different ASINs: {', '.join(sorted(asins))}. Manual review required."))

    if check_status:
        unique = list(dict.fromkeys(r.destination for r in records if r.link_type in ("Internal", "External", "Amazon")))[:max_link_checks]
        def probe(url):
            try:
                r = request_public(url, method="HEAD", timeout=8)
                status = r.status_code
                final = r.url
                r.close()
                if status in (403, 405, 429) or status >= 500:
                    # Only retry GET for unsupported or ambiguously blocked HEAD requests.
                    r = request_public(url, method="GET", timeout=8)
                    status, final = r.status_code, r.url
                    r.close()
                return url, (str(status) if status < 400 else f"HTTP {status}"), final
            except Exception as exc:
                return url, f"Unverified: {str(exc)[:100]}", ""
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = dict((u, (s, f)) for u, s, f in pool.map(probe, unique))
        for rec in records:
            if rec.destination in results:
                rec.status, rec.final_url = results[rec.destination]
                if rec.status.startswith("HTTP "):
                    issues.append(Issue("Warning", "Link status", f"Destination returned {rec.status}; confirm manually (some stores block bots).", f"Link #{rec.number}", rec.destination))
        if len(unique) >= max_link_checks:
            issues.append(Issue("Info", "Coverage", f"Checked at most {max_link_checks} unique destinations; additional links are unverified."))

    return {
        "article_url": article_url,
        "final_url": final_article_url,
        "page_title": soup.title.get_text(" ", strip=True) if soup.title else "",
        "links": [asdict(r) for r in records],
        "issues": [asdict(issue) for issue in issues],
        "summary": {
            "total_links": len(records),
            "amazon_links": sum(r.link_type == "Amazon" for r in records),
            "internal_links": sum(r.link_type == "Internal" for r in records),
            "external_links": sum(r.link_type == "External" for r in records),
            "fails": sum(i.severity == "Fail" for i in issues),
            "warnings": sum(i.severity == "Warning" for i in issues),
        },
    }
