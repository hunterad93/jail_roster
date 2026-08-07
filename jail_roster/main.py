import logging

from jail_roster.scrapers import scrape_all
from jail_roster.storage import write_inmates, write_metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run():
    log.info("Scraping jail rosters...")
    inmates, metadata = scrape_all()
    log.info("Found %d inmates across all jails", len(inmates))

    log.info("Writing to GCS...")
    write_inmates(inmates)
    write_metadata(metadata)
    log.info("Done.")


if __name__ == "__main__":
    run()
