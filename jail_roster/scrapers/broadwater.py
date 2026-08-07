import logging

from bs4 import BeautifulSoup

from jail_roster.scrapers.base import Inmate, http_get

log = logging.getLogger(__name__)

URL = "https://www.broadwatercountysheriff.org/roster.php"
JAIL_NAME = "Broadwater County"


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)
    resp = http_get(URL)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    inmates: list[dict] = []

    for div in soup.find_all("div", class_="inmate_div"):
        name_tag = div.find("strong", class_="ptitles")
        if not name_tag:
            continue

        raw_name = name_tag.get_text(strip=True)
        if "," in raw_name:
            last, rest = raw_name.split(",", 1)
            parts = rest.strip().split()
            first = parts[0] if parts else ""
            middle = " ".join(parts[1:]) if len(parts) > 1 else ""
        else:
            last, first, middle = raw_name, "", ""

        booking_date = ""
        charges = ""
        bond = ""

        for row in div.find_all("div", class_="row"):
            label = row.find("strong", class_="inmate_data_bold")
            if not label:
                continue
            label_text = label.get_text(strip=True).rstrip(":")
            content = row.find("span", class_="text2")
            if not content:
                continue
            value = content.get_text(" ", strip=True)

            if "Booking Date" in label_text:
                booking_date = value
            elif "Charges" in label_text:
                charges = value
            elif "Bond" in label_text:
                if "unavailable" not in value.lower():
                    bond = value

        inmate = Inmate(
            jail=JAIL_NAME,
            last_name=last.strip(),
            first_name=first.strip(),
            middle_name=middle.strip(),
            booking_date=booking_date,
            charges=charges,
            bond=bond,
        )
        inmates.append(inmate.to_dict())

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
