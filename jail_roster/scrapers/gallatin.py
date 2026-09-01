import json
import logging
import os
import random
import re
from datetime import date

import httpx

from jail_roster.scrapers.base import Inmate, http_client

log = logging.getLogger(__name__)

PORTAL = "https://portal-mt-gallatin-so.centralsquarecloudgov.com"
BASE_URL = f"{PORTAL}/api/portal/inmates"
JAIL_NAME = "Gallatin County"
PAGE_SIZE = 50

SCRAPER_API = "https://api.scraperapi.com"


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
        # CentralSquare format: "New Arrest: CODE - Description; ..." or "Warrant: ..."
        charge_match = re.match(r"(?:New Arrest|Warrant|Charge)[:\s]+(.+?)(?:;\s*Arrest Date|$)", block)
        if charge_match:
            charges.append(charge_match.group(1).strip().rstrip(";"))
        elif not block.startswith("Bond"):
            desc = block.split(";")[0].strip()
            if desc:
                charges.append(desc)
        bond_match = re.search(r"Bond\s*-\s*(?:Cash/Surety,\s*)?\$([0-9,.]+)", block)
        if bond_match:
            bond_parts.append(f"${bond_match.group(1)}")

    return "; ".join(dict.fromkeys(charges)), ", ".join(dict.fromkeys(bond_parts))


def _scrape_via_proxy(api_key: str) -> list[dict]:
    """Route requests through ScraperAPI to avoid datacenter IP blocks."""
    session_num = random.randint(1, 999999)
    params = {
        "api_key": api_key,
        "session_number": session_num,
        "keep_headers": "true",
    }

    with httpx.Client(timeout=90, follow_redirects=True) as client:
        xsrf_resp = client.get(
            SCRAPER_API,
            params={**params, "url": f"{PORTAL}/api/portal/config/xsrf_token"},
        )
        xsrf_resp.raise_for_status()

        csrf_token = xsrf_resp.cookies.get("XSRF-TOKEN")
        if not csrf_token:
            log.warning("%s: no XSRF-TOKEN cookie received", JAIL_NAME)
            return []

        session_cookie = xsrf_resp.cookies.get("session", "")
        cookie_str = f"XSRF-TOKEN={csrf_token}; session={session_cookie}"
        today = date.today().isoformat()

        all_records: dict[str, dict] = {}
        start = 0
        while True:
            resp = client.post(
                SCRAPER_API,
                params={**params, "url": f"{BASE_URL}/load"},
                headers={
                    "X-CSRF-TOKEN": csrf_token,
                    "Content-Type": "application/json",
                    "Cookie": cookie_str,
                },
                content=json.dumps({
                    "name": "",
                    "race": "all",
                    "sex": "all",
                    "cell_block": "all",
                    "held_for_agency": "any",
                    "in_custody": today,
                    "paging": {"start": start, "count": PAGE_SIZE},
                    "sorting": {"sort_by_column_tag": "name", "sort_descending": False},
                }),
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

    return list(all_records.values())


def _scrape_direct() -> list[dict]:
    """Direct requests without proxy (works from residential IPs)."""
    with http_client() as client:
        xsrf_resp = client.get(f"{PORTAL}/api/portal/config/xsrf_token")
        xsrf_resp.raise_for_status()

        csrf_token = client.cookies.get("XSRF-TOKEN")
        if not csrf_token:
            log.warning("%s: no XSRF-TOKEN cookie received", JAIL_NAME)
            return []

        today = date.today().isoformat()

        all_records: dict[str, dict] = {}
        start = 0
        while True:
            resp = client.post(
                f"{BASE_URL}/load",
                headers={"X-CSRF-TOKEN": csrf_token},
                json={
                    "name": "",
                    "race": "all",
                    "sex": "all",
                    "cell_block": "all",
                    "held_for_agency": "any",
                    "in_custody": today,
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

    return list(all_records.values())


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)

    api_key = os.environ.get("SCRAPER_API_KEY")
    if api_key:
        log.info("Using ScraperAPI proxy for %s", JAIL_NAME)
        raw_records = _scrape_via_proxy(api_key)
    else:
        raw_records = _scrape_direct()

    inmates = []
    for record in raw_records:
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
