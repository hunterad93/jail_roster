import io
import logging
import re

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
    resp = httpx.get(
        WP_MEDIA_URL,
        params={"search": "active_inmate_report", "per_page": 1, "mime_type": "application/pdf"},
        timeout=15,
        follow_redirects=True,
    )
    resp.raise_for_status()
    results = resp.json()
    if results:
        return results[0]["source_url"]
    raise ValueError("Could not find Glacier County jail roster PDF via WordPress API")


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)

    pdf_url = _find_pdf_url()
    log.info("Found PDF at %s", pdf_url)

    resp = httpx.get(pdf_url, timeout=30, follow_redirects=True)
    resp.raise_for_status()

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
