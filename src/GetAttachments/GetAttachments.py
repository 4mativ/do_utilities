import os
import traceback

import pandas as pd
from imbox import Imbox
from glob import glob
import datetime

from Common import getCreds

creds = getCreds("gmail-personal")
download_folder = os.path.dirname(__file__) + "\\Attachments"

if not os.path.isdir(download_folder):
    os.makedirs(download_folder, exist_ok=True)

os.chdir(download_folder)
for file in glob("*.*"):
    # Clear old files
    os.remove(file)

mail = Imbox(
    creds["host"], username=creds["username"], password=creds["password"], ssl=True, ssl_context=None, starttls=False
)

# All inbox
# messages = mail.messages()

# All Unread messages
messages = mail.messages(unread=True)

# Messages sent FROM
# messages = mail.messages(sent_from='sender@example.org')

# Messages received after specific date, (gt = >)
# messages = mail.messages(date__gt=datetime.date(2018, 7, 30))

# Messages sent to someone before a certain date (lt = <)
# messages = mail.messages(sent_to='ar@hopskipdrive.com', date__lt=datetime.date(2023, 7, 30))

# Unread Rainbow Invoices
# messages = mail.messages(unread=True, sent_from="Followthatcab.net")

# Unread Assist Invoices
# messages = mail.messages(unread=True, sent_from="accounting@assistservicesonline.com")

# All rainbow messages since a given date
# messages = mail.messages(date__gt=datetime.date(2025, 7, 1), sent_from="Followthatcab.net")
# messages = mail.messages(date__gt=datetime.date(2024, 11, 1), sent_to="billing@4mativ.org")

# wil have array with emails and valid attachment counts for each sender
sender_tracker = {}

counter = 0

file_list = []
for uid, message in messages:
    # optional, mark message as read
    # mail.mark_seen(uid)

    cur_sender = message.sent_from[0]["name"]

    if cur_sender not in sender_tracker:
        sender_tracker[cur_sender] = [1, 0]
    else:
        sender_tracker[cur_sender][0] += 1

    for attachment in message.attachments:
        try:
            att_fn = attachment.get("filename")

            if att_fn == "" and attachment.get("content-type") == "application/octet-stream":
                counter += 1
                print(
                    f"Found an attachment I'm not able to parse, attempting to save file {counter} "
                    f"as "
                    f"an excel file or csv"
                )
                download_path = f"{download_folder}/unknown_file{counter}.xlsx"
                with open(download_path, "wb") as fp:
                    fp.write(attachment.get("content").read())
                try:
                    pd.read_excel(download_path)
                    print(f"Downloaded {att_fn}")
                except:
                    os.remove(download_path)
                    download_path = f"{download_folder}/unknown_file{counter}.csv"
                    with open(download_path, "wb") as fp:
                        fp.write(attachment.get("content").read())
                    try:
                        pd.read_csv(download_path)
                        print(f"Downloaded {att_fn}")
                    except:
                        os.remove(download_path)
                continue

            if any(x in att_fn for x in [".csv", ".xlsx", ".xls"]):
                download_path = f"{download_folder}/{att_fn}"
                # print(download_path)
                file_list.append(att_fn)
                with open(download_path, "wb") as fp:
                    fp.write(attachment.get("content").read())
                sender_tracker[cur_sender][1] += 1
                print(f"Downloaded {att_fn}")
            else:
                if ".pdf" not in att_fn:
                    print(f"Did not download {att_fn} because it did not have an approved file type")
        except Exception:
            print(traceback.print_exc())

mail.logout()
print("\n")
total_count = 0
for sender in sender_tracker:
    print(
        f"Found {sender_tracker[sender][0]} emails from {sender} that had {sender_tracker[sender][1]} total valid attachments"
    )
    total_count += sender_tracker[sender][1]

file_list = sorted(list(set(file_list)))

print("\nThe total number of attachments was", total_count, "which is", len(file_list), "unique files.\n\n")
print(file_list)
