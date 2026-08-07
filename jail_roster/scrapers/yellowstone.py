import csv
import io
import logging

from jail_roster.scrapers.base import Inmate, http_get

log = logging.getLogger(__name__)

URL = "https://www.yellowstonecountymt.gov/sheriff/detention/JailRoster/JailRoster.csv"
JAIL_NAME = "Yellowstone County"


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)
    resp = http_get(URL)
    resp.raise_for_status()

    reader = csv.DictReader(io.StringIO(resp.text))

    inmates: list[dict] = []
    for row in reader:
        bond_raw = row.get("Total Bond", "").strip()
        bond = ""
        if bond_raw:
            try:
                val = float(bond_raw)
                if val > 0:
                    bond = f"${val:,.2f}"
            except ValueError:
                bond = bond_raw

        inmate = Inmate(
            jail=JAIL_NAME,
            last_name=row.get("Last Name", "").strip(),
            first_name=row.get("First Name", "").strip(),
            middle_name=row.get("Middle Name", "").strip(),
            booking_date=row.get("Booking Date", "").strip(),
            bond=bond,
        )
        inmates.append(inmate.to_dict())

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
