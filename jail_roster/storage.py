import csv
import gzip
import io
import logging
from datetime import datetime, timezone

from google.cloud import storage

log = logging.getLogger(__name__)

BUCKET_NAME = "jail-roster-data-magnetic-mender"
INMATES_BLOB = "inmates.csv"
METADATA_BLOB = "sync_status.csv"

INMATE_HEADERS = ["jail", "last_name", "first_name", "middle_name", "booking_date", "charges", "bond", "status"]
META_HEADERS = ["county", "status", "count", "last_success", "error", "url"]


def _get_bucket():
    client = storage.Client()
    return client.bucket(BUCKET_NAME)


def _archive_blob(bucket, blob_name: str):
    blob = bucket.blob(blob_name)
    if not blob.exists():
        return
    now = datetime.now(timezone.utc)
    day_prefix = now.strftime("archive/%Y-%m-%d")
    timestamp = now.strftime("%H%M%S")
    base = blob_name.replace(".csv", "")
    archive_name = f"{day_prefix}/{base}_{timestamp}.csv.gz"

    csv_bytes = blob.download_as_bytes()
    compressed = gzip.compress(csv_bytes)

    archive_blob = bucket.blob(archive_name)
    archive_blob.upload_from_string(compressed, content_type="application/gzip")
    log.info("Archived %s -> gs://%s/%s (%d bytes)", blob_name, BUCKET_NAME, archive_name, len(compressed))


def read_inmates() -> list[dict]:
    bucket = _get_bucket()
    blob = bucket.blob(INMATES_BLOB)
    if not blob.exists():
        return []
    text = blob.download_as_text()
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def read_metadata() -> list[dict]:
    bucket = _get_bucket()
    blob = bucket.blob(METADATA_BLOB)
    if not blob.exists():
        return []
    text = blob.download_as_text()
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def write_inmates(inmates: list[dict]):
    bucket = _get_bucket()
    _archive_blob(bucket, INMATES_BLOB)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=INMATE_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(inmates)

    blob = bucket.blob(INMATES_BLOB)
    blob.upload_from_string(buf.getvalue(), content_type="text/csv")
    log.info("Wrote %d inmates to gs://%s/%s", len(inmates), BUCKET_NAME, INMATES_BLOB)


def write_metadata(metadata: list[dict]):
    bucket = _get_bucket()
    _archive_blob(bucket, METADATA_BLOB)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=META_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(metadata)

    blob = bucket.blob(METADATA_BLOB)
    blob.upload_from_string(buf.getvalue(), content_type="text/csv")
    log.info("Wrote %d metadata rows to gs://%s/%s", len(metadata), BUCKET_NAME, METADATA_BLOB)
