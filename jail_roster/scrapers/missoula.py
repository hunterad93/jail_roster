import logging

from bs4 import BeautifulSoup

from jail_roster.scrapers.base import Inmate, http_client

log = logging.getLogger(__name__)

URL = "https://webapps.missoulacounty.us/jailroster/Inmates"
JAIL_NAME = "Missoula County"


def _parse_name(raw: str) -> tuple[str, str, str]:
    raw = raw.strip()
    if "," not in raw:
        return raw, "", ""
    last, rest = raw.split(",", 1)
    parts = rest.strip().split()
    first = parts[0] if parts else ""
    middle = " ".join(parts[1:]) if len(parts) > 1 else ""
    return last.strip(), first.strip(), middle.strip()


def _get_all_inmates_page() -> str:
    client = http_client()
    resp = client.get(URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    viewstate = soup.find("input", {"id": "__VIEWSTATE"})["value"]
    viewstate_gen = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})["value"]

    resp = client.post(
        URL,
        data={
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": viewstate_gen,
            "__EVENTTARGET": "ctl00$MainContent$li9",
            "__EVENTARGUMENT": "",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.text


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)
    html = _get_all_inmates_page()
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table", class_="table")
    if not table:
        log.warning("Could not find inmate table")
        return []

    inmates = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        name_tag = cells[0].find("h4")
        if not name_tag:
            continue

        raw_name = name_tag.get_text(strip=True)
        last, first, middle = _parse_name(raw_name)

        age = cells[1].get_text(strip=True).replace("\xa0", "")
        booking_id = cells[2].get_text(strip=True).replace("\xa0", "")
        booking_date = cells[4].get_text(strip=True).replace("\xa0", "")

        inmate = Inmate(
            jail=JAIL_NAME,
            last_name=last,
            first_name=first,
            middle_name=middle,
            booking_date=booking_date,
        )
        inmates.append(inmate.to_dict())

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
