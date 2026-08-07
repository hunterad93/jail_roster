import logging
import re

from bs4 import BeautifulSoup

from jail_roster.scrapers.base import Inmate, http_get

log = logging.getLogger(__name__)

URL = "https://apps.flathead.mt.gov/jailroster/?report=inmates&sort=lastname"
JAIL_NAME = "Flathead County"


def _parse_name(h2) -> tuple[str, str, str]:
    last = h2.contents[0].strip().rstrip(",") if h2.contents else ""
    span = h2.find("span", class_="lighten-text")
    rest = span.get_text(strip=True).lstrip(",").strip() if span else ""
    parts = rest.split()
    first = parts[0] if parts else ""
    middle = " ".join(parts[1:]) if len(parts) > 1 else ""
    return last, first, middle


def _get_stat(article, label: str) -> str:
    for stat in article.find_all("div", class_="inmate-stat"):
        lbl = stat.find("span", class_="stat-label")
        if lbl and label in lbl.get_text():
            p = stat.find("p")
            return p.get_text(strip=True) if p else ""
    return ""


def _get_charges(article) -> str:
    charges = []
    for li in article.find_all("li", class_="disposition-entry"):
        severity_tag = li.find("span", class_=re.compile(r"severity-tag"))
        severity = severity_tag.get_text(strip=True) if severity_tag else ""

        desc_tag = li.find("span", class_="disposition-description")
        if desc_tag:
            code_tag = desc_tag.find("span", class_="charge-code")
            code = ""
            if code_tag:
                for hidden in code_tag.find_all("span", class_="visually-hidden"):
                    hidden.decompose()
                code = code_tag.get_text(strip=True)
                code_tag.decompose()
            desc = desc_tag.get_text(strip=True)
            if code:
                desc = f"{desc} ({code})"
            if severity:
                desc = f"[{severity}] {desc}"
            charges.append(desc)
    return "; ".join(charges)


def scrape() -> list[dict]:
    log.info("Scraping %s...", JAIL_NAME)
    resp = http_get(URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    inmates = []
    for article in soup.find_all("article", class_="inmate-entry"):
        h2 = article.find("h2")
        if not h2:
            continue

        last, first, middle = _parse_name(h2)
        bail = _get_stat(article, "Total Bail")
        court_date = _get_stat(article, "Court Date")
        charges = _get_charges(article)

        inmate = Inmate(
            jail=JAIL_NAME,
            last_name=last,
            first_name=first,
            middle_name=middle,
            charges=charges,
            bond=bail,
            status=f"Court: {court_date}" if court_date else "",
        )
        inmates.append(inmate.to_dict())

    log.info("Found %d inmates in %s", len(inmates), JAIL_NAME)
    return inmates
