# Affiliate Content QA — runnable starter framework

A Streamlit application for auditing **publicly reachable buyer-intent articles**. It provides a full link inventory, Amazon URL/associate-tag checks, simple discrepancy warnings, and downloadable Excel/JSON reports. Supports up to 30 article URLs per batch.

## Run on Windows / Mac / Linux

1. Install Python 3.10 or newer.
2. Open a terminal inside this folder.
3. Install dependencies: `python -m pip install -r requirements.txt`
4. Launch: `python -m streamlit run app.py`
5. Paste article URLs, one per line, optionally enter the expected Amazon Associates tag, and run.

## Included checks

- All `<a href>` links in the article's `<main>` element (or `<article>`, falling back to `<body>`); inventory includes original URL, absolute destination, label, nearest preceding heading, category, detected ASIN and affiliate tag.
- Amazon links missing `tag=`; unexpected tag when an expected tag is provided; missing ASIN in direct product URLs (warning only).
- Identical descriptive anchor text pointing to different ASINs; explicit ASIN in a section heading differing from link ASIN.
- Presence of an affiliate disclosure phrase, H1 and meta description.
- Optional live HTTP status checks, capped and limited to five concurrent workers. Bot blocks (403/429) are **warnings requiring review**, not proof of broken links.
- Summary and two report sheets: full link inventory and issues.

## Important limitations

- This is **not** a complete Amazon Associates compliance certification. Verify current program policy yourself.
- Does not verify product availability, pricing, actual listing identity, or product-to-article name correspondence. Those need trusted product catalog data or manual review. Amazon shortened links may obscure tags/ASINs.
- Parses server-delivered HTML, not JavaScript-rendered links. JS-only CTAs or cloaked redirect plugins may need browser-based rendering or site integrations.
- Link-status requests can be blocked by Amazon, Cloudflare and other anti-bot services, so distinguish *unverified* from *broken*.
- Run only against sites you own or have permission to audit. Respect rate limits. No credentials are requested.
- Server-side fetching blocks private/local destinations and validates redirect destinations; for deployment on a public server, also apply network-level egress controls and authentication.

## Tests

`python -m pytest -q`
