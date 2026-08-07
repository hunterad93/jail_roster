import io
import logging
import re

import pdfplumber

from jail_roster.scrapers.base import Inmate, http_get

log = logging.getLogger(__name__)

URL = "https://www.lccountymt.gov/files/assets/county/v/9999/sheriff/documents/jail-roster.pdf"
JAIL_NAME = "Lewis & Clark County"

INMATE_RE = re.compile(
    r"^([A-Z][A-Z' -]+),\s+([A-Z][A-Z ]+?)\s+"
    r"(\d{1,3})\s+"
    r"(Male|Female)\s+"
    r"(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2})\s+"
    r"(\d{2}-\d+)\s+"
    r"(.*)"
)


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)
    resp = http_get(URL)
    resp.raise_for_status()

    pdf = pdfplumber.open(io.BytesIO(resp.content))

    all_lines = []
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            all_lines.extend(text.split("\n"))

    inmates: list[dict] = []
    current: dict | None = None
    current_charges: list[str] = []

    for line in all_lines:
        line = line.strip()
        if not line or line.startswith("Jail Roster") or line.startswith("Name "):
            continue

        match = INMATE_RE.match(line)
        if match:
            if current:
                current["charges"] = "; ".join(c for c in current_charges if c)
                inmates.append(current)

            last_name = match.group(1).strip()
            first_parts = match.group(2).strip().split()
            first_name = first_parts[0] if first_parts else ""
            middle_name = " ".join(first_parts[1:]) if len(first_parts) > 1 else ""
            booking_date = match.group(5)
            hold_reasons = match.group(8).strip()

            current = Inmate(
                jail=JAIL_NAME,
                last_name=last_name,
                first_name=first_name,
                middle_name=middle_name,
                booking_date=booking_date,
            ).to_dict()
            current_charges = [hold_reasons] if hold_reasons else []
        elif current is not None:
            current_charges.append(line)

    if current:
        current["charges"] = "; ".join(c for c in current_charges if c)
        inmates.append(current)

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
