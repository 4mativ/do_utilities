import os
from collections import namedtuple
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from copy import deepcopy
from dotenv import dotenv_values
from pandas import read_csv, DataFrame

# A utility file that other scripts may import and use its common variables

shared_4mativ_drive = "G:/Shared drives/4MATIV General"

diagnostics_drive = "G:/Shared drives/Consulting"

data_ops_drive = "G:/Shared drives/Data_Ops"

active_diagnostics_folder = diagnostics_drive + "/0. Consulting - Ongoing"

billing_doc_id = "12NvTg2NfkuvnT-bM7lO0eTu4WW3BWA7ul0t0y7YvX7E"

# f_year ~= 2024
f_year = datetime.now().year + (
    1 if datetime.now().month > 7 or (datetime.now().month > 6 and datetime.now().day > 25) else 0
)

# fiscal_year ~= FY24
fiscal_year = f"FY{str(f_year)[2:]}"

# School Year ~= SY23-24
school_year = f"SY{str(f_year - 1)[2:]}-{str(f_year)[2:]}"

# The current pricing scheme for variable price vendors: cost per picked up student, cost per
# mile, minimum trip cost, cost for a student not showing up
price_schema = namedtuple("price_schema", ["pu_fee", "mi_fee", "min_fee", "no_show_fee", "base_fee"])
prices = {
    "Rainbow/B&W-Old": price_schema(7, 2.75, 25, 0, 0),
    "Assist Services-Old": price_schema(7.5, 2.5, 26, 0, 26),
    "Rainbow/B&W": price_schema(7.5, 2.75, 27, 0, 0),
    # 'Meisa': price_schema(14.12, 2.73, 0, 20.8, 0),
    "Assist Services": price_schema(10, 2.5, 28, 0, 28),
    "Assist Services - INDY": price_schema(10, 2.5, 28, 0, 28),
    "Assist Services - MSP": price_schema(10, 2.5, 28, 0, 28),
    "First Alt": price_schema(0, 2.65, 84.5, 0, 72.5),  # Add 2 for camera and 10 for HC vehicle
    "zTrip": price_schema(60, 0, 60, 0, 60),
    "HopSkipDrive": price_schema(0, 2.75, 30, 0, 30),
    "Houston: HopSkipDrive": price_schema(0, 2.75, 30, 0, 30),
    "Oromiya-Ramsey": price_schema(175, 0, 0, 175, 0),
    "Halo Transportation-Ramsey": price_schema(155, 0, 0, 155, 0),
}
# Rainbow is $27 min with $7.5 per pickup and 2.75 per mile
# Assist = 26 to run route + 7.50 per additional kid and 2.5/mile after 5 miles
# zTrip = 60 per student (120 for some)
# HSD is 30 + 2.75 for miles travelled, regardless of riders

# Codes used to print to the log with formatting, until the END command is used, all following
# text will use the previous codes
color = {
    "PURPLE": "\033[95m",
    "CYAN": "\033[96m",
    "DARKCYAN": "\033[36m",
    "BLUE": "\033[94m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "RED": "\033[91m",
    "BOLD": "\033[1m",
    "UNDERLINE": "\033[4m",
    "END": "\033[0m",
}

# Rainbow refers to schools by their internal account code, this allows us to switch between
# account code and our alpha code
rainbow_account_lookup = {
    "AGA": "5300",
    "BCN": "R5034",
    "CDH": "550A",
    "CPA": "471M",
    "HBA": "1301",
    "HCH": "R3500",
    "HCK": "R3800",
    "HCN": "R4640",
    "HPN": "R2123",
    "LNK": "L260",
    "KPL": "R2620",
    "KPN": "R5034",
    "KPX": "R1000",
    "LWA": "R2225",
    "MLA": "9060z",
    "NCC": "R1500",
    "NCP": "N300",
    "NSH": "6717",
    "PCH": "R620",
    "PGY": "R5929",
    "PST": "R170",
    "RCF": "R763",
    "SHB": "8600",
    "SHR": "1401",
    "TCA": "690B",
}

rainbow_school_lookup = dict([(value, key) for key, value in rainbow_account_lookup.items()])

# HSD refers to schools by their internal account code, this allows us to switch between account
# code and our alpha code
hsd_account_lookup = {"586809": "Paul Revere Academy", "423062": "Etoile Academy - Bissonnet"}

# The days of the week, can be indexed later to determine the day using pandas dayofweek function
days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# A dictionary fo defining what the one character code for each day fo the week is
day_riding_dict = {"Mon": "M", "Tue": "T", "Wed": "W", "Thu": "R", "Fri": "F"}

months = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


data_ops_drive_id = "0AEjNd0TBUj-JUk9PVA"
general_drive_id = "0AMbHK88Jjh41Uk9PVA"


trips_db_columns = [
    "InvoiceRun",
    "School Year",
    "LegID",
    "Vendor",
    "School",
    "Trip Type",
    "BookingID",
    "Date",
    "PUTime",
    "Direction",
    "RouteName",
    "Mode",
    "StudentName",
    "Program",
    "Stop",
    "Status",
    "Miles",
    "StudentCount",
    "OriginalTotalCost",
    "OriginalCostperLeg",
    "CostAdjustment",
    "FinalTotalCost",
    "FinalCostperLeg",
    "4mativAllocation",
    "CostperLegwAllocation",
    "Invoice",
    "StudentID",
    "ArchiveTimestamp",
    "RecordID",
]


valid_accomodations = [
    "curb_to_curb",
    "booster_seat",
    "car_seat",
    "5_point_harness",
    "solo",  # Planned change to "solo_rider"
    "aide",
    "wheelchair" "small_vehicle",
    "hand_to_hand",
    "visual_impairment",
    "hearing_impairment",
    "non_verbal",
    "behavior_plan",
    "medical_plan",
    # Plan to add: "closest_corner", "1_to_1_aide", "nurse"
]

supported_languages = [
    "english",
    "spanish",
    "somali",
    "french",
    "russian",
    "somali",
    "pashto",
    "hmong",
    "karen",
]

data_template_columns = [
    "Change?",
    "FirstName",
    "LastName",
    "Change Requested via Transportation Hotline",
    "Date of Contact",
    "SSID",
    "School",
    "Transportation Status (Riding/Not Riding)",  # Riding, Riding (AM Only), Riding (PM Only), Not Riding
    "Grade",
    "Program",
    "Accomodations (select all that apply)",
    # Curb-to-Curb, Booster seat, Car seat, 5-point harness, Solo, Aide,
    # Wheelchair, Small vehicle, hand-to-hand, Visual Impairment, Hearing impairment, Non-verbal, Behavior plan,
    # Medical plan, No transportation accomodations in IEP
    "New Enrollee or Returning Student?",  # New or Returning
    #
    "Primary Contact: Name",
    "Primary Contact: Relationship to Student",
    "Primary Contact: Mobile Phone Number",
    "Primary Contact: Preferred Language",
    #
    "Home: Address",
    "Home: Address Line 2",
    "Home: City",
    "Home: Zip",
    #
    "AM Transportation: Address",
    "AM Transportation: Address Line 2",
    "AM Transportation: City",
    "AM Transportation: Zip",
    "AM Transportation: Type (Optional)",
    # Home, Daycare, Other Alternate Transportation Address Type, PPU, Walk, Unassigned, Carpool, Distance Learning
    #
    "PM Transportation: Address",
    "PM Transportation: Address Line 2",
    "PM Transportation: City",
    "PM Transportation: Zip",
    "PM Transportation: Type (Optional)",
    # Home, Daycare, Other Alternate Transportation Address Type, PPU, Walk, Unassigned, Carpool, Distance Learning
    #
    "Days of Week (if applicable)",  # Monday AM, Monday PM...Friday AM, Friday PM
    "Public Student Note",
    "Private Student Note",
    #
    "Additional Address 1: Address",
    "Additional Address 1: Address Line 2",
    "Additional Address 1: City",
    "Additional Address 1: Zip",
    "Additional Address 1: Type (Optional)",
    "Additional Address 1: Days of Week",
    # Monday AM, Monday PM...Friday AM, Friday PM, Alternating Weeks
    #
    "Additional Address 2: Address",
    "Additional Address 2: Address Line 2",
    "Additional Address 2: City",
    "Additional Address 2: Zip",
    "Additional Address 2: Type (Optional)",
    "Additional Address 2: Days of Week",
    #
    "Contact 2: Name",
    "Contact 2: Relationship to Student",
    "Contact 2: Mobile Phone Number",
    "Contact 2: Opt-in to Hotline Communications?",
    "Contact 2: Preferred Language",
    #
    "Contact 3: Name",
    "Contact 3: Relationship to Student",
    "Contact 3: Mobile Phone Number",
    "Contact 3: Opt-in to Hotline Communications?",
    "Contact 3: Preferred Language",
    #
    "Contact 4: Name",
    "Contact 4: Relationship to Student",
    "Contact 4: Mobile Phone Number",
    "Contact 4: Opt-in to Hotline Communications?",
    "Contact 4: Preferred Language",
]

github_file_path = ""

creds = {}

# billing_dbs = {}

invoicing_db_path = ""

df_standardizations = DataFrame()


def initializeVariables(filepath = os.getcwd()):
    global github_file_path, creds, billing_dbs, invoicing_db_path, df_standardizations

    # The path to the github repository that this repo is in, used to reference other repo's files in
    # scripts
    github_file_path = str(filepath)[: str(filepath).find("GitHub") + 7]
    creds = dotenv_values(github_file_path + ".env")
    for cur in ["google-drive", "postgres", "qb", "gmail-personal", "dw", "twilio"]:
        creds[cur] = [[x.replace(f"{cur.upper()}-", ""), creds[x]] for x in creds if f"{cur.upper()}" in x]

        creds[cur] = dict([(str(x[0]).lower(), x[1]) for x in creds[cur]])
    for cur in ["staging", "prod"]:
        creds[f"dw-{cur}"] = [
            [x.replace(f"{cur}-", ""), creds["dw"][x]] for x in creds["dw"] if f"{cur}" in x and "new" not in x
        ]
        creds[f"dw-{cur}"] = dict([(str(x[0]).lower(), x[1]) for x in creds[f"dw-{cur}"]])
    creds["dw"] = {
        "staging": creds["dw-staging"],
        "prod": creds["dw-prod"],
        "new": deepcopy(creds["dw-prod"]),
    }
    creds["dw"]["new"]["bucket"] = creds["DW-PROD-NEW-BUCKET"]
    # scope_app = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # cred = ServiceAccountCredentials.from_json_keyfile_dict(creds["google-drive"], scope_app)
    # client = gspread.authorize(cred)
    # billing_file = client.open_by_key(billing_doc_id)
    # billing_sheets = billing_file.worksheets()
    # for cur_sheet in billing_sheets:
    #     name = cur_sheet.title
    #     # Read in the filter as a df
    #     df = DataFrame(cur_sheet.get_all_values())
    #     # Make the first row values the column headers, then remove that row
    #     df.columns = df.iloc[0]
    #     df = df[1:]
    #     if "Archive Date" in df.columns:
    #         df["Archive Date"] = df["Archive Date"].astype(str)
    #         df = df[df["Archive Date"] == ""]
    #         df.reset_index(drop=True, inplace=True)
    #     billing_dbs[name] = df
    # Save the file path to the files in the InvoicingDB repo
    invoicing_db_path = github_file_path + "Automation-Scripts/Invoicing/InvoicingDBs/"
    df_standardizations = read_csv(data_ops_drive + "/Databases/Standardization.csv")

def getCred(cred_name):
    if cred_name in creds.keys():
        return creds[cred_name]
    print(f"There were no credentials found for {cred_name}")


def getStandards():
    return df_standardizations
