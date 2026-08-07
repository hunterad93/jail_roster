import io
import logging
import re

import pdfplumber

from jail_roster.scrapers.base import Inmate, http_get

log = logging.getLogger(__name__)

URL = "https://www.lakemt.gov/DocumentCenter/View/816/Jail_Roster"
JAIL_NAME = "Lake County"

INMATE_RE = re.compile(
    r"^([A-Z][A-Z'-]+),\s+([A-Z][A-Z'-]+(?:\s+[A-Z][A-Z'-]+)*)\s*"
    r"(\d{2}-\d+)\s+"
    r"(\d{1,3})\s+"
    r"(\S+(?:\s+or)?\s*\S*)\s+"  # race (may be "Black or", "American")
    r"(Male|Female)\s+"
    r"(\d+)\s+"
    r"(\d{2}/\d{2}/\d{2})\s+"
    r"(\S+)"
)

CHARGE_RE = re.compile(r"^\d{2}-\d+-\d+|^[A-Z]{2,3}\s+Hold")


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
        if not line or line.startswith("Roster Printed") or line.startswith("Last, First"):
            continue

        match = INMATE_RE.match(line)
        if match:
            if current:
                current["charges"] = "; ".join(current_charges)
                inmates.append(current)

            last_name = match.group(1).strip()
            first_middle = match.group(2).strip().split()
            first_name = first_middle[0] if first_middle else ""
            middle_name = " ".join(first_middle[1:]) if len(first_middle) > 1 else ""
            booking_date = match.group(8)

            current = Inmate(
                jail=JAIL_NAME,
                last_name=last_name,
                first_name=first_name,
                middle_name=middle_name,
                booking_date=booking_date,
            ).to_dict()
            current_charges = []

            remainder = line[match.end():].strip()
            if remainder:
                current_charges.append(remainder)
        elif current is not None:
            current_charges.append(line)

    if current:
        current["charges"] = "; ".join(current_charges)
        inmates.append(current)

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
