import logging
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


def scrape_all() -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    metadata: list[dict] = []
    for name, scraper, url in SCRAPERS:
        started = datetime.now(timezone.utc)
        try:
            inmates = scraper()
            results.extend(inmates)
            status = "ok" if inmates else "warning"
            metadata.append({
                "county": name,
                "status": status,
                "count": len(inmates),
                "last_success": started.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "error": "0 inmates returned" if not inmates else "",
                "url": url,
            })
        except Exception as e:
            log.exception("Failed to scrape %s", name)
            metadata.append({
                "county": name,
                "status": "error",
                "count": 0,
                "last_success": "",
                "error": str(e),
                "url": url,
            })
    return results, metadata
