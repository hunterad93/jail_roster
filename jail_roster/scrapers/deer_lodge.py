import io
import logging
import re

import httpx
import pdfplumber

from jail_roster.scrapers.base import Inmate

log = logging.getLogger(__name__)

URL = "https://www.adlc.us/DocumentCenter/View/248/Jail-Roster-PDF"
JAIL_NAME = "Deer Lodge County"

INMATE_RE = re.compile(
    r"^([A-Z][A-Z' -]+),\s+([A-Z][A-Z ]+?)\s+"
    r"(\d{10})\s+"  # booking number
    r"([A-Z])\s+"  # race
    r"([MF])\s+"  # sex
    r"(\d{2}/\d{2}/\d{4})\s+"  # DOB
    r"(\S+)\s+"  # cell
    r"(\d{2}/\d{2}/\d{4})\s+"  # booking date
)


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)
    resp = httpx.get(URL, timeout=30, follow_redirects=True)
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
    in_charges = False

    for line in all_lines:
        line = line.strip()
        if not line or line.startswith("Facility Roster") or line.startswith("Inmate ") or line.startswith("Name ") or line.startswith("____"):
            continue
        if re.match(r"^\d+$", line):
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
            booking_date = match.group(8)

            bond_match = re.search(r"\$[\d,.]+", line[match.end():])
            bond = bond_match.group(0) if bond_match else ""

            current = Inmate(
                jail=JAIL_NAME,
                last_name=last_name,
                first_name=first_name,
                middle_name=middle_name,
                booking_date=booking_date,
                bond=bond,
            ).to_dict()
            current_charges = []
            in_charges = False
        elif line.startswith("Charges:"):
            in_charges = True
        elif in_charges and current is not None:
            charge = line.lstrip("- ").strip()
            if charge:
                current_charges.append(charge)

    if current:
        current["charges"] = "; ".join(c for c in current_charges if c)
        inmates.append(current)

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
