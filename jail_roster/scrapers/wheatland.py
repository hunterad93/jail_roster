import io
import logging
import re

import pdfplumber
from bs4 import BeautifulSoup

from jail_roster.scrapers.base import Inmate, http_get

log = logging.getLogger(__name__)

SHERIFF_URL = "https://wheatlandcomt.gov/sheriff/"
JAIL_NAME = "Wheatland County"

INMATE_RE = re.compile(
    r"^[•]\s+(.+?)\s+[–-]\s+Booking Date\s+(.+?)\s+[–-]\s+Agency:\s+(.+)$",
    re.IGNORECASE,
)

CHARGE_RE = re.compile(r"^o\s+(.+)$")
BOND_RE = re.compile(r"^[▪■]\s+(.+)$")


def _find_pdf_url() -> str:
    resp = http_get(SHERIFF_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True).lower()
        if "jail roster" in text or "inmate roster" in text:
            href = link["href"]
            if href.endswith(".pdf"):
                return href
    raise ValueError("Could not find jail roster PDF link on Wheatland sheriff page")


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)

    pdf_url = _find_pdf_url()
    log.info("Found PDF at %s", pdf_url)

    resp = http_get(pdf_url)
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
    current_bonds: list[str] = []

    for line in all_lines:
        line = line.strip()
        if not line:
            continue

        inmate_match = INMATE_RE.match(line)
        if inmate_match:
            if current:
                current["charges"] = "; ".join(current_charges)
                current["bond"] = "; ".join(current_bonds)
                inmates.append(current)

            raw_name = inmate_match.group(1).strip()
            booking_date = inmate_match.group(2).strip()

            if "," in raw_name:
                last, rest = raw_name.split(",", 1)
                parts = rest.strip().split()
                first = parts[0] if parts else ""
                middle = " ".join(parts[1:]) if len(parts) > 1 else ""
            else:
                parts = raw_name.split()
                last = parts[-1] if parts else ""
                first = parts[0] if parts else ""
                middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""

            current = Inmate(
                jail=JAIL_NAME,
                last_name=last.strip(),
                first_name=first.strip(),
                middle_name=middle.strip(),
                booking_date=booking_date,
            ).to_dict()
            current_charges = []
            current_bonds = []
            continue

        charge_match = CHARGE_RE.match(line)
        if charge_match and current is not None:
            current_charges.append(charge_match.group(1).strip())
            continue

        bond_match = BOND_RE.match(line)
        if bond_match and current is not None:
            current_bonds.append(bond_match.group(1).strip())
            continue

    if current:
        current["charges"] = "; ".join(current_charges)
        current["bond"] = "; ".join(current_bonds)
        inmates.append(current)

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
