import logging
import os

from jail_roster.sheets import get_client, sync_to_sheet, sync_metadata
from jail_roster.scrapers import scrape_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run():
    spreadsheet_id = os.environ["SPREADSHEET_ID"]

    log.info("Scraping jail rosters...")
    inmates, metadata = scrape_all()
    log.info("Found %d inmates across all jails", len(inmates))

    log.info("Syncing to Google Sheet...")
    client = get_client()
    sync_to_sheet(client, spreadsheet_id, inmates)
    sync_metadata(client, spreadsheet_id, metadata)
    log.info("Done.")


if __name__ == "__main__":
    run()
