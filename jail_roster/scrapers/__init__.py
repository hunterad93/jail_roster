import logging
import time
from datetime import datetime, timezone

from jail_roster.scrapers.missoula import scrape as scrape_missoula
from jail_roster.scrapers.flathead import scrape as scrape_flathead
from jail_roster.scrapers.ravalli import scrape as scrape_ravalli
from jail_roster.scrapers.gallatin import scrape as scrape_gallatin
from jail_roster.scrapers.park import scrape as scrape_park
from jail_roster.scrapers.lake import scrape as scrape_lake
from jail_roster.scrapers.lewis_clark import scrape as scrape_lewis_clark
from jail_roster.scrapers.deer_lodge import scrape as scrape_deer_lodge
from jail_roster.scrapers.wheatland import scrape as scrape_wheatland
from jail_roster.scrapers.jefferson import scrape as scrape_jefferson
from jail_roster.scrapers.broadwater import scrape as scrape_broadwater
from jail_roster.scrapers.glacier import scrape as scrape_glacier
from jail_roster.scrapers.yellowstone import scrape as scrape_yellowstone

log = logging.getLogger(__name__)

SCRAPERS = [
    ("Missoula", scrape_missoula, "https://webapps.missoulacounty.us/jailroster/Inmates"),
    ("Flathead", scrape_flathead, "https://apps.flathead.mt.gov/jailroster/"),
    ("Ravalli", scrape_ravalli, "https://ravalli-so-mt.zuercherportal.com/"),
    ("Gallatin", scrape_gallatin, "https://portal-mt-gallatin-so.centralsquarecloudgov.com/inmates"),
    ("Park", scrape_park, "https://www.parkcountymt.gov/Government-Departments/Sheriff-s-Office/Inmates-Housed/"),
    ("Lake", scrape_lake, "https://www.lakemt.gov/DocumentCenter/View/816/Jail_Roster"),
    ("Lewis & Clark", scrape_lewis_clark, "https://www.lccountymt.gov/Sheriff/Detention-Center"),
    ("Deer Lodge", scrape_deer_lodge, "https://www.adlc.us/DocumentCenter/View/248/Jail-Roster-PDF"),
    ("Wheatland", scrape_wheatland, "https://wheatlandcomt.gov/sheriff/"),
    ("Jefferson", scrape_jefferson, "https://jefferson-so-mt.zuercherportal.com/#/inmates"),
    ("Broadwater", scrape_broadwater, "https://www.broadwatercountysheriff.org/roster.php"),
    ("Glacier", scrape_glacier, "https://glaciercountymt.gov/"),
    ("Yellowstone", scrape_yellowstone, "https://www.yellowstonecountymt.gov/sheriff/detention/dcsearch.asp"),
]


EXPECTED_MIN_COUNTS = {
    "Missoula": 100, "Flathead": 30, "Ravalli": 15, "Gallatin": 50,
    "Yellowstone": 200, "Lewis & Clark": 40,
}


def _dedup_inmates(inmates: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for i in inmates:
        key = (i.get("jail", ""), i.get("last_name", ""), i.get("first_name", ""),
               i.get("middle_name", ""), i.get("booking_date", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(i)
    if len(deduped) < len(inmates):
        log.info("Deduplication removed %d duplicates", len(inmates) - len(deduped))
    return deduped


def scrape_all() -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    metadata: list[dict] = []
    for name, scraper, url in SCRAPERS:
        started = datetime.now(timezone.utc)
        last_err = None
        inmates = None
        for attempt in range(3):
            if attempt > 0:
                log.info("Retrying %s in 60s (attempt %d/3)...", name, attempt + 1)
                time.sleep(60)
            try:
                inmates = scraper()
                last_err = None
                break
            except Exception as e:
                last_err = e
                log.warning("Failed to scrape %s (attempt %d/3): %s", name, attempt + 1, e)
        if last_err is not None:
            log.error("Failed to scrape %s after 3 attempts", name)
            metadata.append({
                "county": name,
                "status": "error",
                "count": 0,
                "last_success": "",
                "error": str(last_err),
                "url": url,
            })
        else:
            min_expected = EXPECTED_MIN_COUNTS.get(name, 0)
            if min_expected > 0 and len(inmates) < min_expected:
                log.error(
                    "Possible structure change in %s: got %d inmates, expected at least %d",
                    name, len(inmates), min_expected,
                )
            status = "ok" if inmates else "warning"
            metadata.append({
                "county": name,
                "status": status,
                "count": len(inmates),
                "last_success": started.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "error": "0 inmates returned" if not inmates else "",
                "url": url,
            })
            results.extend(inmates)
    return _dedup_inmates(results), metadata
