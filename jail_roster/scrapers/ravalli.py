import logging
import re
from datetime import datetime, timezone

import httpx

from jail_roster.scrapers.base import Inmate

log = logging.getLogger(__name__)

BASE_URL = "https://ravalli-so-mt.zuercherportal.com/api/portal/inmates"
JAIL_NAME = "Ravalli County"
PAGE_SIZE = 50


def _parse_name(raw: str) -> tuple[str, str, str]:
    raw = raw.strip()
    if "," not in raw:
        return raw, "", ""
    last, rest = raw.split(",", 1)
    parts = rest.strip().split()
    first = parts[0] if parts else ""
    middle = " ".join(parts[1:]) if len(parts) > 1 else ""
    return last.strip(), first.strip(), middle.strip()


def _parse_hold_reasons(html: str) -> tuple[str, str]:
    charges = []
    bond_parts = []
    for block in html.split("<br />"):
        block = block.strip()
        if not block:
            continue
        charge_match = re.search(r"Charge:.*?\((.+?)\)", block)
        if charge_match:
            charges.append(charge_match.group(1))
        bond_match = re.search(r"Bond.*?,\s*\$([0-9,.]+)", block)
        if bond_match:
            bond_parts.append(f"${bond_match.group(1)}")

    return "; ".join(dict.fromkeys(charges)), ", ".join(dict.fromkeys(bond_parts))


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)

    with httpx.Client(timeout=30) as client:
        client.get(f"{BASE_URL}/init")

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        all_records: dict[str, dict] = {}
        start = 0
        while True:
            resp = client.post(
                f"{BASE_URL}/load",
                json={
                    "name": "",
                    "race": "all",
                    "sex": "all",
                    "cell_block": "all",
                    "held_for_agency": "any",
                    "in_custody": now,
                    "paging": {"start": start, "count": PAGE_SIZE},
                    "sorting": {"sort_by_column_tag": "name", "sort_descending": False},
                },
            )
            resp.raise_for_status()
            data = resp.json()

            records = data.get("records", [])
            for r in records:
                key = (r.get("name", ""), r.get("arrest_date", ""))
                all_records[key] = r

            total = data.get("total_record_count", 0)
            start += PAGE_SIZE
            if start >= total or not records:
                break

    inmates = []
    for record in all_records.values():
        last, first, middle = _parse_name(record.get("name", ""))
        hold_reasons = record.get("hold_reasons") or ""
        charges, bond = _parse_hold_reasons(hold_reasons)

        inmate = Inmate(
            jail=JAIL_NAME,
            last_name=last,
            first_name=first,
            middle_name=middle,
            booking_date=record.get("arrest_date", ""),
            charges=charges,
            bond=bond,
        )
        inmates.append(inmate.to_dict())

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
