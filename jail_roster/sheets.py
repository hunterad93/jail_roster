import json
import os

import google.auth
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_client() -> gspread.Client:
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds, _ = google.auth.default(scopes=SCOPES)
    return gspread.authorize(creds)


def sync_to_sheet(client: gspread.Client, spreadsheet_id: str, inmates: list[dict]):
    sheet = client.open_by_key(spreadsheet_id)
    worksheet = sheet.sheet1

    headers = [
        "Jail",
        "Last Name",
        "First Name",
        "Middle Name",
        "Booking Date",
        "Charges",
        "Bond",
        "Status",
    ]

    rows = [headers]
    for inmate in inmates:
        rows.append([
            inmate.get("jail", ""),
            inmate.get("last_name", ""),
            inmate.get("first_name", ""),
            inmate.get("middle_name", ""),
            inmate.get("booking_date", ""),
            inmate.get("charges", ""),
            inmate.get("bond", ""),
            inmate.get("status", ""),
        ])

    worksheet.clear()
    worksheet.update(range_name="A1", values=rows)


def sync_metadata(client: gspread.Client, spreadsheet_id: str, metadata: list[dict]):
    sheet = client.open_by_key(spreadsheet_id)

    try:
        ws = sheet.worksheet("Sync Status")
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title="Sync Status", rows=50, cols=6)

    headers = ["County", "Status", "Inmate Count", "Last Sync", "Error", "Source URL"]
    rows = [headers]
    for m in metadata:
        rows.append([
            m.get("county", ""),
            m.get("status", ""),
            str(m.get("count", 0)),
            m.get("last_success", ""),
            m.get("error", ""),
            m.get("url", ""),
        ])

    ws.clear()
    ws.update(range_name="A1", values=rows)
