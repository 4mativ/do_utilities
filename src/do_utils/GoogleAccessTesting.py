import io
import json
import os.path
import re

from oauth2client.service_account import ServiceAccountCredentials
import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from Common import getCreds, getSchoolFromAlpha
from Constants import data_ops_drive, school_year, data_ops_drive_id, general_drive_id


def findAllTemplateValues(template_id):

    try:
        creds = oAuth()
        docs = build("docs", "v1", credentials=creds)

        template_file = (
            docs.documents()
            .get(
                documentId=template_id,
            )
            .execute()
        )

        test = template_file.get("body")["content"]

        doc_text = ""
        for i in range(len(test)):
            cur_i = test[i]
            if "paragraph" in cur_i:
                for j in range(len(cur_i["paragraph"]["elements"])):
                    cur_j = cur_i["paragraph"]["elements"][j]
                    if "textRun" in cur_j:
                        doc_text += cur_j["textRun"]["content"]

        needed_keys = re.findall(r"<<(.*?)>>", doc_text)

        needed_keys = sorted(list(set(needed_keys)))

        return needed_keys

    except HttpError as error:
        # TODO(developer) - Handle errors from drive API.
        print(f"An error occurred: {error}")
        return []


def oAuth():
    # If modifying these scopes, delete the file token.json.
    scopes = ["https://www.googleapis.com/auth/drive"]

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(os.path.dirname(__file__) + "\\token.json"):
        creds = Credentials.from_authorized_user_file(os.path.dirname(__file__) + "\\token.json", scopes)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                data_ops_drive + "/Credentials/GoogleCredentials.json", scopes
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(os.path.dirname(__file__) + "\\token.json", "w") as token:
            token.write(creds.to_json())
    return creds


def copyDataTemplateForAlpha(alpha, sy=school_year):
    try:
        service = build("drive", "v3", credentials=oAuth())

        # File ID is base template file
        template_file = (
            service.files()
            .get(supportsAllDrives=True, fileId="1dGANkkB0FoJUMhDYOkZESaG81RPvTgOXPwH__pfcpHY", fields="parents")
            .execute()
        )

        # Need to overwrite parent folder, so store this for later
        prev_parents = template_file["parents"][0]

        # The fields to change from the original, along with their new value
        copy_body = {"name": f"{alpha}_{sy}_Data_Template"}

        # Use the school's folder name in drive to find its ID
        folder_name = f"'{getSchoolFromAlpha(alpha)} ({alpha})'"
        search = f"mimeType = 'application/vnd.google-apps.folder' and name = {folder_name}"
        results = (
            service.files()
            .list(
                corpora="drive",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                driveId="0AEjNd0TBUj-JUk9PVA",
                q=search,
                fields="files(id)",
            )
            .execute()
        )
        items = results.get("files", [])
        folder_id = items[0]["id"]

        # Create a copy of the template, appears in same folder
        copy_file = (
            service.files()
            .copy(supportsAllDrives=True, fileId="1dGANkkB0FoJUMhDYOkZESaG81RPvTgOXPwH__pfcpHY", body=copy_body)
            .execute()
        )

        # Change the file's parent folder to move it to the correct location
        service.files().update(
            supportsAllDrives=True,
            fileId=copy_file["id"],
            addParents=folder_id,
            removeParents=prev_parents,
            fields="id, parents",
        ).execute()

        return copy_file["id"]

    except HttpError as error:
        # TODO(developer) - Handle errors from drive API.
        print(f"An error occurred: {error}")
        return ""


def generateExecutiveSummary(value_dict=None, test=None, save_path=os.path.dirname(__file__) + "\\Exec.pdf"):

    # Replacement values
    needed_keys = [
        "Avg ADM",
        "Avg Bus Cost per Day",
        "Cap Rate",
        "Gain Share",
        "INV Number",
        "Invoice Total",
        "Month",
        "ADM Days",
        "Bus Days",
        "Sum of above lines",
        "Total Bus Costs",
        "Total Cap",
        "Total Management Costs",
        "Total Non-Bus Pass-Through Vendor Costs",
        "Unique Bus Count",
    ]

    # Check if missing any entries
    flag = False
    for cur_key in needed_keys:
        if cur_key not in value_dict:
            print(f"Missing {cur_key}")
            flag = True
        if any(roundable in cur_key for roundable in ["Avg", "Total", "Sum", "Costs"]):
            try:
                value_dict[cur_key] = round(value_dict[cur_key], 2)
            except:
                pass
    if flag:
        raise Exception

    cap = value_dict["Has Cap"]

    # Sheet ID of template file
    summary_id = "12vIjsskJ1msRkm-cQGq-qkGtSZkvVsiyCG16I5BE-84"

    try:
        creds = oAuth()
        drive = build("drive", "v3", credentials=creds)
        docs = build("docs", "v1", credentials=creds)

        # Throwaway name, used in-case error occurs to identify correct file
        copy_body = {"name": "Exec Summary Template Temporary"}

        # Create a copy of the executive summary template file
        copy_file = drive.files().copy(supportsAllDrives=True, fileId=summary_id, body=copy_body).execute()

        # Store the id of the copied file for later
        copied_id = copy_file.get("id")

        # Create an update request for each variable and add it to the list
        updates = []

        if "1" not in test:
            updates.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "matchCase": True,
                            "text": "<<Month>> Bus Costs: <<Avg Bus Cost per Day>>/bus/day x "
                            "<<Unique Bus Count>> buses x <<Bus Days>> days = <<Total Bus "
                            "Costs>>\n",
                        },
                        "replaceText": "",
                    }
                }
            )

        if "2" not in test:
            updates.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "matchCase": True,
                            "text": "<<Month>> Other Pass-Through Vendor Costs: <<Total Non-Bus Pass-Through Vendor Costs>>\n",
                        },
                        "replaceText": "",
                    }
                }
            )

        if "3" not in test:
            updates.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "matchCase": True,
                            "text": "<<Month>> Management Costs: <<Total Management Costs>>\n",
                        },
                        "replaceText": "",
                    }
                }
            )

        if "4" in test:

            if not cap:
                updates.append(
                    {
                        "replaceAllText": {
                            "containsText": {
                                "matchCase": True,
                                "text": "<<Month>> Cap-Billed Van/Cab Costs:",
                            },
                            "replaceText": "<<Month>> Van/Cab Costs:",
                        }
                    }
                )
        else:
            updates.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "matchCase": True,
                            "text": "<<Month>> Cap-Billed Van/Cab Costs: <<Cap Rate>>/ADM/day x "
                            "<<Avg ADM>> ADM x <<ADM Days>> days = <<Total Cap>>\n",
                        },
                        "replaceText": "",
                    }
                }
            )

        if "5" not in test:
            updates.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "matchCase": True,
                            "text": "Total <<Month>> Expenses: <<Sum of above lines>>\n",
                        },
                        "replaceText": "",
                    }
                }
            )

        if "6" not in test:
            updates.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "matchCase": True,
                            "text": "<<Month>> 4MATIV Partner-Aligned Savings: <<Gain Share>>\n",
                        },
                        "replaceText": "",
                    }
                }
            )

        if "7" not in test:
            updates.append(
                {
                    "replaceAllText": {
                        "containsText": {"matchCase": True, "text": "Final <<Month>> Total: <<Invoice Total>>\n"},
                        "replaceText": "",
                    }
                }
            )

        for cur in needed_keys:
            updates.append(
                {
                    "replaceAllText": {
                        "containsText": {"matchCase": True, "text": "<<" + cur + ">>"},
                        "replaceText": value_dict[cur],
                    }
                }
            )

        updates.append(
            {
                "replaceAllText": {
                    "containsText": {"matchCase": True, "text": "  "},
                    "replaceText": " ",
                }
            }
        )

        updates.append(
            {
                "replaceAllText": {
                    "containsText": {"matchCase": True, "text": "\n\n"},
                    "replaceText": "\n",
                }
            }
        )

        # Apply all of the changes to the copied document
        docs.documents().batchUpdate(documentId=copied_id, body={"requests": updates}).execute()

        # print("Done: 2. Update copied Document.")

        # 3. Download the updated Document as PDF file.
        request = drive.files().export_media(fileId=copied_id, mimeType="application/pdf")
        fh = io.FileIO(save_path, mode="wb")
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            # print("Download %d%%." % int(status.progress() * 100))
        # print("Done: 3. Download the updated Document as PDF file.")

        # 4. Delete the copied Document.
        drive.files().delete(fileId=copied_id, supportsAllDrives=True).execute()
        # print("Done: 4. Delete the copied Document.")

    except HttpError as error:
        print(f"An error occurred during the creation of the executive summary: {error}")


def replaceGoogleSheetData(sheet_id, df):
    scope_app = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    connection = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(getCreds("google-drive"), scope_app))

    sheets = connection.open_by_url(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid=0")

    google_sheet = sheets[0]

    # Save the df to the google sheet
    google_sheet.resize(len(df) + 1, len(df.columns))
    google_sheet.set_dataframe(df, (1, 1))


def findFileID(file_name, drive_name):
    service = build("drive", "v3", credentials=oAuth())

    results = (
        service.files()
        .list(
            corpora="drive",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            driveId=data_ops_drive_id if "data" in drive_name.lower() else general_drive_id,
            q=f"name = '{file_name}'",
            fields="files(id)",
        )
        .execute()
    )
    items = results.get("files", [])
    file_id = items[0]["id"]
    return file_id


def main():
    print(findFileID("Billing Data", "dataops"))


if __name__ == "__main__":
    main()
