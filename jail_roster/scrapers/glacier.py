import io
import logging
import re
import time

import httpx
import pdfplumber

from jail_roster.scrapers.base import Inmate

log = logging.getLogger(__name__)

WP_MEDIA_URL = "https://glaciercountymt.gov/wp-json/wp/v2/media"
JAIL_NAME = "Glacier County"

INMATE_RE = re.compile(
    r"^\((\d+)\)\s+(.+?)\s+(\d+)\s+([\d,]+)\s+(\d{2}/\d{2}/\d{4})$"
)


def _find_pdf_url() -> str:
    for attempt in range(3):
        if attempt > 0:
            time.sleep(2)
        resp = httpx.get(
            WP_MEDIA_URL,
            params={"search": "active_inmate_report", "per_page": 1, "mime_type": "application/pdf"},
            timeout=20,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            log.warning("%s: WP media API returned %d (attempt %d)", JAIL_NAME, resp.status_code, attempt + 1)
            continue
        content_type = resp.headers.get("content-type", "")
        if "json" not in content_type:
            log.warning("%s: WP media API returned non-JSON content-type %s (attempt %d)", JAIL_NAME, content_type, attempt + 1)
            continue
        try:
            results = resp.json()
        except Exception:
            log.warning("%s: WP media API returned invalid JSON (attempt %d)", JAIL_NAME, attempt + 1)
            continue
        if results and isinstance(results, list):
            return results[0]["source_url"]
    raise ValueError("Could not find Glacier County jail roster PDF after 3 attempts")


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)

    pdf_url = _find_pdf_url()
    log.info("Found PDF at %s", pdf_url)

    resp = httpx.get(pdf_url, timeout=30, follow_redirects=True)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
        raise ValueError(f"Expected PDF but got content-type: {content_type}")

    pdf = pdfplumber.open(io.BytesIO(resp.content))

    all_lines = []
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            all_lines.extend(text.split("\n"))

    inmates: list[dict] = []

    for line in all_lines:
        line = line.strip()
        if not line:
            continue

        match = INMATE_RE.match(line)
        if not match:
            continue

        raw_name = match.group(2).strip()
        bond = match.group(4).replace(",", "")
        booking_date = match.group(5)

        if "," in raw_name:
            last, rest = raw_name.split(",", 1)
            parts = rest.strip().split()
            first = parts[0] if parts else ""
            middle = " ".join(parts[1:]) if len(parts) > 1 else ""
        else:
            parts = raw_name.split()
            last = parts[-1] if parts else ""
            first = parts[0] if parts else ""
            middle = ""

        bond_str = f"${bond}" if bond != "0" else ""

        inmate = Inmate(
            jail=JAIL_NAME,
            last_name=last.strip(),
            first_name=first.strip(),
            middle_name=middle.strip(),
            booking_date=booking_date,
            bond=bond_str,
        )
        inmates.append(inmate.to_dict())

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
