import logging
import re

from bs4 import BeautifulSoup

from jail_roster.scrapers.base import Inmate, http_get

log = logging.getLogger(__name__)

URL = "https://www.parkcountymt.gov/Government-Departments/Sheriff-s-Office/Inmates-Housed/"
JAIL_NAME = "Park County"


def _parse_name(raw: str) -> tuple[str, str, str]:
    raw = raw.strip()
    if "," not in raw:
        return raw, "", ""
    last, rest = raw.split(",", 1)
    parts = rest.strip().split()
    first = parts[0] if parts else ""
    middle = " ".join(parts[1:]) if len(parts) > 1 else ""
    return last.strip(), first.strip(), middle.strip()


def _parse_charge_bond(td) -> tuple[str, str]:
    paragraphs = [p.get_text(strip=True) for p in td.find_all("p")]
    charges = []
    bonds = []
    for p in paragraphs:
        if not p:
            continue
        bond_match = re.match(r"^\$[\d,.]+ Bond", p)
        if bond_match:
            bonds.append(p)
        elif p.lower() in ("ice hold", "hold"):
            charges.append(p)
        else:
            charges.append(p)
    return "; ".join(charges), "; ".join(bonds)


def _parse_agency_date(text: str) -> str:
    text = text.strip()
    match = re.search(r"(\d{1,2}-\d{1,2}-\d{4})", text)
    return match.group(1) if match else text


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)
    resp = http_get(URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    tables = soup.find_all("table")
    data_table = None
    for table in tables:
        headers = table.get_text()
        if "INMATE" in headers and "CHARGE" in headers:
            data_table = table
            break

    if not data_table:
        log.warning("Could not find inmate table on Park County page")
        return []

    inmates = []
    for row in data_table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        name_text = cells[0].get_text(strip=True)
        if not name_text or "INMATE" in name_text.upper():
            continue

        last, first, middle = _parse_name(name_text)
        charges, bond = _parse_charge_bond(cells[1])
        booking_date = _parse_agency_date(cells[2].get_text(strip=True))

        inmate = Inmate(
            jail=JAIL_NAME,
            last_name=last,
            first_name=first,
            middle_name=middle,
            booking_date=booking_date,
            charges=charges,
            bond=bond,
        )
        inmates.append(inmate.to_dict())

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
