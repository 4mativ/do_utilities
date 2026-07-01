import os
import requests
from datetime import date, datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from glob import glob
from json import dumps
from re import search, sub
from shutil import copyfile, move, rmtree
from smtplib import SMTP
from tkinter import filedialog
from traceback import format_exc
from copy import deepcopy


import pandas as pd
from gspread import authorize
from numpy import nan
from oauth2client.service_account import ServiceAccountCredentials
from pandas import concat, DataFrame, ExcelFile, options, read_csv, read_excel
from pydrive2.auth import GoogleAuth
from anglicize import anglicize
from rapidfuzz import process, fuzz

# from Geocoding.GoogleApi import GetRoutedDistance, EquivalentAddresses
from do_utilities.Constants import getStandards, getCred, data_ops_drive, initializeVariables
from do_utilities.AddressStandardizer import convertAddress

options.mode.chained_assignment = None


# Save the standardization df into a local variable
standard = getStandards()

# Ramsey County Foster and some other schools need to be treated as a single entity, so we need to
# know all of the schools that fall under their umbrellas
df_toms_schools = read_csv(data_ops_drive + "/Databases/All_TOMS_schools.csv")
df_toms_schools["District Alpha"] = ""

always_convert = [
    "El Paso Leadership Academy",
    "Ramsey Cty-Foster",
    "West MEC",
    "Compass Rose",
    "Compass Rose Public Schools",
]

convert_for_invoicing = [
    "El Paso Leadership Academy",
    "Ramsey Cty-Foster",
    "West MEC",
    "Compass Rose Public Schools",
    "Compass Rose - Austin",
    "Compass Rose - San Antonio",
    "Hogan Prep",
    "Seven Hills Prep Academy",
    "Vista College Prep",
    "United Schools",
]

fake_districts = ["Montgomery Test District"]

df_toms_schools = df_toms_schools[~df_toms_schools["District"].isin(fake_districts)]

try:
    df_toms_schools = df_toms_schools[df_toms_schools["Archived"].isna()]
except Exception:
    df_toms_schools = df_toms_schools[~df_toms_schools["SchoolName"].str.contains("TEST")]
    df_toms_schools = df_toms_schools[~df_toms_schools["SchoolName"].str.contains("4mativ")]
    df_toms_schools = df_toms_schools[~df_toms_schools["SchoolName"].str.contains("Link")]
    df_toms_schools = df_toms_schools[df_toms_schools["SchoolCode"] != "ESD"]
    pass

df_toms_schools = df_toms_schools.dropna(subset=["PrimarySchoolAddress"])

df_toms_schools = df_toms_schools.rename(
    columns={
        "SchoolName": "School",
        "SchoolCode": "Code",
        "PrimarySchoolAddress": "Address",
        "SchoolLat": "Lat",
        "SchoolLon": "Long",
    }
)

df_toms_schools["Contact1"] = ""
df_toms_schools["Contact2"] = ""

df_toms_schools["Address"] = [sub(r"^.*?(\d)", r"\1", x) for x in df_toms_schools["Address"]]

df_toms_schools["Street"] = [x.split(", ")[0] for x in df_toms_schools["Address"]]
df_toms_schools["City"] = [x.split(", ")[1] for x in df_toms_schools["Address"]]

df_toms_schools["State"] = [x.split(", ")[2][:2] for x in df_toms_schools["Address"]]
df_toms_schools["ZIP"] = [int(x.split(", ")[2][-5:]) for x in df_toms_schools["Address"]]

df_toms_schools = df_toms_schools.reset_index(drop=True)
df_toms_schools = df_toms_schools.reset_index(drop=False)
df_toms_schools = df_toms_schools.sort_values(by=["School", "index"]).drop_duplicates(
    subset=["School", "Code", "Street", "City", "ZIP"]
)

df_toms_schools = df_toms_schools[df_toms_schools["Lat"] == df_toms_schools["Lat"]]
df_toms_schools = df_toms_schools.reset_index(drop=True)
initialized = False

df_accounts = pd.DataFrame(
            [],
            columns=[
                "Account Status",
                "State",
                "Region",
                "School Name",
                "School Alpha",
                "District",
                "District Alpha",
                "Service Email",
                "AM Emails",
                "Billing Emails",
                "Billing CCs",
                "Account Managers",
                "School Field Trip Contact",
                "School Address",
                "Pod",
                "Searchable",
                "Hotline",
                "Hours Different from Central",
            ],
        )


def initialize(filepath = os.getcwd()):
    global df_toms_schools, initialized

    initializeVariables(filepath)
    # Data for accessing the Google sheets file with account managers
    scope_app = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    sheet_id = "1EkiQx2Q4R-CjLofQTEkl0cNIa_Dn9OvQNDf34mSJRhw"
    try:
        cred = ServiceAccountCredentials.from_json_keyfile_dict(getCreds("google-drive"), scope_app)
        initialized = True
    except:
        print(f"ERROR: Constants has not been initialized, so creds could not be accessed")
        return
    gauth = GoogleAuth()
    gauth.credentials = cred
    client = authorize(cred)

    try:
        g_sheet = client.open_by_key(sheet_id)

        # pull just the first tab
        sheet_instance = g_sheet.get_worksheet(0)

        # Read in the data as a df
        df_accounts = DataFrame(sheet_instance.get_all_values())

        # Make the first row values the column headers, then remove that row
        df_accounts.columns = df_accounts.iloc[0]
        df_accounts = df_accounts[1:]
    except Exception:
        print("Can't access Google sheets currently")
        df_accounts = pd.DataFrame(
            [],
            columns=[
                "Account Status",
                "State",
                "Region",
                "School Name",
                "School Alpha",
                "District",
                "District Alpha",
                "Service Email",
                "AM Emails",
                "Billing Emails",
                "Billing CCs",
                "Account Managers",
                "School Field Trip Contact",
                "School Address",
                "Pod",
                "Searchable",
                "Hotline",
                "Hours Different from Central",
            ],
        )
    
    df_districts = df_toms_schools.groupby("District")
    for district, df_current_district in df_districts:
        if district in df_accounts["District"].unique():
            df_toms_schools.loc[df_current_district.index, "District Alpha"] = df_accounts.loc[
                df_accounts["District"] == district, "District Alpha"
            ].mode()[0]

    df_toms_schools["Hotline"] = [
    df_accounts.loc[df_accounts["School Name"] == x, "Hotline"].max() for x in df_toms_schools["School"]
]

    df_toms_schools["Hours off Central"] = [
        df_accounts.loc[df_accounts["School Name"] == x, "Hours Different from Central"].max()
        for x in df_toms_schools["School"]
    ]

    df_toms_schools["Pod"] = [
        df_accounts.loc[df_accounts["School Name"] == x, "Pod"].max() for x in df_toms_schools["School"]
    ]

    df_toms_schools["Pod"] = [x if x == x else "" for x in df_toms_schools["Pod"]]

    df_toms_schools["Hotline"] = [
        str(x).replace(".0", "").replace("-", "").replace("(", "").replace(")", "") if x == x else ""
        for x in df_toms_schools["Hotline"]
    ]

    df_toms_schools["Hotline"] = [f"({x[:3]}) {x[4:7]}-{x[7:]}" if len(x) == 10 else "" for x in df_toms_schools["Hotline"]]

    df_toms_schools = df_toms_schools[
        [
            "School",
            "Code",
            "Address",
            "Street",
            "City",
            "State",
            "ZIP",
            "Lat",
            "Long",
            "Contact1",
            "Contact2",
            "District",
            "District Alpha",
            "Hotline",
            "Hours off Central",
            "Pod",
        ]
    ]
    
    df_toms_schools["Street"] = [convertAddress(x, True) for x in df_toms_schools["Street"]]
    
    df_toms_schools = df_toms_schools[df_toms_schools["Lat"] == df_toms_schools["Lat"]]
    df_toms_schools = df_toms_schools.reset_index(drop=True)


# ------------- Basic Getters -------------------------------------------------------------------- #

# Get the school df
def getSchoolDF():
    return df_toms_schools


# Get the QBR filepath for saving, file path is State\Districts or Individual\Alpha\
def getSchoolMatrixRegionPath(alpha):
    state = getStateFromAlphaOrName(alpha)
    if state != state or str(state).lower() == "nan":
        print(f"Failed to find state for: {alpha}")
        quit(1)
    return f"\\{state}\\{alpha}\\"

# Get the QBR filepath for saving, file path is State\Alpha\
def getSchoolSharedFolderPath(alpha):
    school = getSchoolFromAlpha(alpha)
    if school == "Ramsey Cty-Foster":
        return "MSP RAM\\MSP RAM FULL\\"
    state = compareToSchools(school, "School", ["State"])[0]

    shared_folder_name = "4mativ-" + alpha + "-Shared Folder"

    if state == "MN":
        return "MSP\\" + alpha + "\\" + shared_folder_name + "\\"
    elif state == "TX":
        state = "HOU"
    elif state == "IN":
        state = "IND\\INDY"
    elif state == "AZ":
        state = "PHX\\Paul Revere" if alpha == "PRA" else "PHX\\VCP Arizona"
    else:
        print(f"ERROR: NO state found for {alpha} / {school}")
        quit(1)

    return f"{state}\\{alpha}\\"


# Get the street address of all schools
def getSchoolAddresses():
    return df_toms_schools["Street"].unique()


# Get the text name of all schools
def getSchools():
    return df_toms_schools["School"].unique()


def getCurrentSchools():
    return df_toms_schools["School"].unique()


# ------------- User Input ----------------------------------------------------------------------- #

# Generic helper function for getting the user to select a file/directory and confirm their
# selection
def confirmFilepath(root, intro_text, is_folder):
    # The intro text should explain what file/directory the user should be locating
    print(intro_text)

    # updating the display element prior to creating the file dialog menu
    root.update()

    # Create a file dialog window that determines the given file or folderpath
    if is_folder:
        file_path = filedialog.askdirectory()
    else:
        file_path = filedialog.askopenfilename()

    # Get confirmation that the user's selection was correct and rerun if not
    print("You selected:", file_path, "\nIs that correct? (y/n) ")
    while True:
        response = input().lower()
        if response in ["y", "yes", "yep"]:
            return file_path
        elif response in ["n", "no", "nope"]:
            return confirmFilepath(root, intro_text, is_folder)


# Get some user input via the console/log
def getInput(intro_text="", yes_no=False):
    # The intro text should explain what input the user should be providing
    print(intro_text)

    # Read the user's last line of input and verify it
    var = input().lower()
    if yes_no:
        # A null response should be treated as a quick yes
        if var in ["y", "yes", "yep", ""]:
            return True
        elif var in ["n", "no", "nope"]:
            return False
        return getInput(intro_text, yes_no)

    # Have user verify their input
    response = getInput(f"You entered: {var} \nIs that correct? (y/n) ", True)
    if response:
        print(f"Accepted '{var}' as user's input")
        return var
    else:
        return getInput(intro_text, yes_no)


# ------------- File Reading --------------------------------------------------------------------- #

# Combines all excel and/or csv files in a folder (assumes the files are the same column format)
def generateMasterFile(folder, add_filename_column=False, return_dict=False, recursive=False):
    # Save the current directory for later use
    start_path = os.getcwd()

    # Move to the file path given to look through the folders
    os.chdir(folder)
    dfs = []
    lookup_dict = {}

    # Iterate through all excel files
    for file in glob("*.xls") + glob("*.xlsx"):
        # While you have an Excel file open, it "creates" a temporary version with the same name
        # and a '~' at the front in the same folder, ignore those
        if "~" == file[0]:
            continue
        # For Excel files, read all sheets
        try:
            xl = read_excel(file, sheet_name=None)
            for sheet in xl.keys():
                df_sheet = xl[sheet]
                # df_sheet.dropna(how="all", axis=1, inplace=True)

                df_sheet["InputFile"] = file + "|" + sheet
                lookup_dict[file + "|" + sheet] = df_sheet
                dfs.append(df_sheet)
        except Exception as e:
            print(f"Failed to read file {file}|{sheet}")
            raise e

    # If we found any excel data, convert it to a dataframe, else create an empty one
    excel = concat(dfs) if dfs else DataFrame()

    # Create an empty df for the csv entries
    dfs = []
    # os.chdir(file_path)

    # Iterate through all csv files
    for file in glob("*.csv"):
        try:
            try:
                df_csv = read_csv(file)
            except:
                df_csv = read_csv(file, encoding="ISO-8859-1")
            df_csv["InputFile"] = file
            lookup_dict[file] = df_csv
            dfs.append(df_csv)
        except Exception:
            print(f"Failed to read file {file}")

    dfs = concat(dfs) if dfs else DataFrame()

    # Combine any .csv and .xlsx dataframes generated
    final = concat([excel, dfs])

    if not add_filename_column:
        try:
            final = final.drop(columns=["InputFile"])
        except Exception:
            pass

    if recursive:
        try:
            sub_folders = next(os.walk(folder))[1]
            for folder in sub_folders:
                sub_entry = generateMasterFile(folder, add_filename_column, return_dict, recursive)
                if return_dict:
                    lookup_dict.update(sub_entry)
                else:
                    final = concat([final, sub_entry])
        except Exception:
            pass

    # Move the system back to the starting path to avoid issues with further script calls
    os.chdir(start_path)
    if return_dict:
        return lookup_dict
    return final.reset_index(drop=True)


# Combines all files at the given file paths
def combineFiles(file_path_arr):
    # Create an array to store the created df for each file
    dfs = []

    # Iterate through all of the given files in the array
    for file_path in file_path_arr:

        # csv
        if file_path[-4:] == ".csv":
            dfs.append(read_csv(file_path, low_memory=False))

        elif file_path[-5:] == ".xlsx":
            xl = ExcelFile(file_path)
            dfs.extend(xl.parse(sheet) for sheet in xl.sheet_names)
    return concat(dfs)


# Combines all excel and/or csv files in given folder paths (assumes they are the same format)
def combineFolders(folder_path_arr):
    arr = [generateMasterFile(folderPath) for folderPath in folder_path_arr]
    return concat(arr)


# ------------- Random Utility Functions -------------------------------------------------------- #

# Sends an email from your email address
def sendEmail(sender, to, cc, subject, body, attachment_filepath=None, bcc=None):
    if not initialized:
        print(f"Error: Common has not been initialized")
        return
    # alternate password used to access my email via script
    app_pass = getCreds("gmail-personal")["app_pass"]

    # Instantiate email object
    msg = MIMEMultipart()

    # Store the sender's email address
    msg["From"] = sender

    # storing the receiver's email addresses
    msg["To"] = ", ".join(to) if len(to) > 1 else to[0] if len(to) == 1 else ""
    msg["CC"] = ", ".join(cc) if len(cc) > 1 else cc[0] if len(cc) == 1 else ""

    # Generate the email subject line
    msg["Subject"] = subject

    # attach the to with the msg instance
    msg.attach(MIMEText(body, "plain"))

    if attachment_filepath:

        if not isinstance(attachment_filepath, list):
            attachment_filepath = [attachment_filepath]

        for cur_file in attachment_filepath:
            # open the file to be sent and save the file stream
            attachment = open(cur_file, "rb")

            # Instantiate an instance of MIMEBase to store the file
            p = MIMEBase("application", "octet-stream")

            # Add attachment file to p
            p.set_payload(attachment.read())

            # Encode into base64
            encoders.encode_base64(p)

            filename = cur_file.replace("\\", "/").split("/")[-1]

            # Save the file name as part of the attachment
            p.add_header("Content-Disposition", f"attachment; filename= {filename}")

            # attach the instance 'p' to instance 'msg'
            msg.attach(p)

    # create an SMTP session
    s = SMTP("smtp.gmail.com", 587)

    # start TLS for security
    s.starttls()

    # Authenticate email
    s.login(sender, app_pass)

    # Converts the Multipart msg into a string
    text = msg.as_string()

    if bcc:
        bcc = ", ".join(bcc) if len(bcc) > 1 else bcc[0] if len(bcc) == 1 else ""
        # Send the email
        s.sendmail(sender, bcc, text)
    else:
        s.sendmail(sender, to + cc, text)

    print("Email sent")

    # terminate the connection to the email service
    s.quit()


# Get the most common item in an array
def getMode(arr):
    return max(set(arr), key=arr.count)


# Applies appropriate suffix to dates based on the number
def dateDaySuffix(d):
    return "th" if 11 <= d <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")


# Converts text to time
def extractTime(entry):
    try:
        # convert nan to midnight
        if entry != entry:
            return datetime.strptime("0:00", "%H:%M")

        # If a time zone code is in the string, remove it
        if "t" in str(entry) or "T" in str(entry):
            entry = str(entry)[:-4]
        return datetime.strptime(str(entry), "%H:%M")

    except Exception:
        # Error processing time, return midnight
        return datetime.strptime("0:00", "%H:%M")


# Generates a requirements.txt file based on imported libraries
def generateRequirementsFile(move_locations = True):
    try:
        if move_locations:
            os.chdir(os.path.dirname(__file__))
        
        repo_path = "/".join(os.getcwd().split("\\"))
        command = f"python.exe -m pip list --format=freeze > {repo_path}/requirements.txt"
        
        os.chdir(repo_path)
        os.system(command)
    except Exception:
        print("Failed to generate new reqiurements file")

# Gets the credential values for various APIs
def getCreds(cred_name):
    return getCred(cred_name)


# ------------- Archive System ----------------------- #

def archiveRun(start_location, current_files=True):

    if not "Run Files" in start_location:
        start_location += "\\Run Files\\"

    date_string = date.today().strftime("%Y_%m_%d")

    # Generate the filepath to save this file in the state's run folder

    archive_path = start_location + "Used\\"

    if current_files:
        paths = [archive_path + "LastRun\\", archive_path + date_string + "\\"]
        try:
            while len(next(os.walk(archive_path))[1]) > 10:
                oldest_folder = next(os.walk(archive_path))[1][0]
                print(oldest_folder + "'s old archived record was deleted")
                rmtree(archive_path + oldest_folder)
        except Exception:
            print("ERROR: Failed to Unload run files")
        try:
            rmtree(paths[0])
        except:
            pass
    else:
        start_location = archive_path + "LastRun\\"
        try:
            # -2 = last date archive folder, -1 = LastRun folder
            newest_folder = next(os.walk(archive_path))[1][-2]
            paths = [archive_path + newest_folder + "\\"]
        except Exception:
            paths = [archive_path + "LastRun\\"]
            print("ERROR: Failed to Unload last run files")

    paths = [x.replace("\\", "/") for x in paths]

    for input_folder in next(os.walk(start_location))[1]:
        if input_folder.lower() in ["used", ".gitkeep"]:
            continue

        for cur_path in paths:
            if not os.path.exists(cur_path + input_folder):
                os.makedirs(cur_path + input_folder)

        archiveFiles(input_folder, paths, start_location)


def archiveFiles(input_folder, paths, start_location):
    start_location = start_location.replace("\\", "/")
    if start_location[-1] != "/":
        start_location += "/"
    files = glob(start_location + input_folder + "/*")
    for f in files:
        f = f.replace("\\", "/")
        try:
            for cur_path in paths:
                new_path = f.replace(start_location, cur_path)
                copyfile(f, new_path)
            os.remove(f)
        except Exception as ex:
            folder = f.split("/")[-1]
            for cur_path in paths:
                new_path = f.replace(start_location, cur_path)
                if not os.path.exists(new_path):
                    os.makedirs(new_path)
            # Found folder instead of file, run again on this folder
            archiveFiles(input_folder + "/" + folder, paths, start_location)


def getPreviousRun(start_location):
    try:
        newest_folder = start_location + "\\Run Files\\Used\\LastRun"
        if not os.path.exists(newest_folder):
            raise Exception
        newest_folder = "LastRun"
        print("Loading inputs from LastRun")
    except Exception:
        try:
            # Find the newest run folder to move the inputs from
            if len(next(os.walk(start_location + "\\Run Files\\Used\\"))[1]) >= 1:
                newest_folder = next(os.walk(start_location + "\\Run Files\\Used\\"))[1][-1]
                print("Loading inputs from folder:", newest_folder)
        except Exception:
            print("Unable to Reload input files as there are no saved archives")
            quit(1)

    # Save the current location of the run's folder
    newest_path = start_location + "\\Run Files\\Used\\" + newest_folder

    # Iterate through each folder in the last run and move its contents to the Run Files folder
    for folder in next(os.walk(newest_path))[1]:
        if "output" in folder.lower():
            continue
        files = glob(newest_path + "\\" + folder + "\\*")
        for f in files:
            temp = f.replace("Run Files\\Used\\" + newest_folder, "Run Files")
            move(f, temp)


# The opposite of pandas 'explode' function, combine rows that have identical values for the
# given columns and store their values as a list
def implode(df, group_columns, merge_columns):
    arr = []
    if len(group_columns[0]) == 1:
        group_columns = [group_columns]

    for cur in merge_columns:
        df_temp = df[group_columns + [cur]]
        df_temp = df_temp.groupby(group_columns).agg({cur: lambda x: x.tolist()}, axis=1).reset_index()
        arr.append(df_temp)

    df_final = arr[0]
    for i in range(1, len(arr)):
        df_final = pd.merge(df_final, arr[i], on=group_columns, how="outer")

    return df_final


# Query TOMS for the given address
def queryAdddressInTOMS(address, school_alpha="", coords="", return_candidates=False, return_coords=False):
    if not initialized:
        print(f"Error: Common has not been initialized")
        return
    headers = {"X-Authorization": getCreds("TOMS_INTERNAL_API_TOKEN")}
    params = {"input": address}
    if school_alpha != "":
        params["school"] = school_alpha
    if coords != "":
        params["coords"] = coords

    response = requests.get("https://toms.4mativ.org/api/geo/lookup", headers=headers, params=params)
    if response.status_code == 200:
        result = response.json()
        if "matched" in result:
            address = result["matched"]["address"]
            if return_coords:
                address = (address, f"{result['matched']['lat']}, {result['matched']['lng']}")
        if return_candidates and "candidates" in result:
            address = [address]
            for cur in result["matched"]["candidates"]:
                entry = cur["address"]
                if return_coords:
                    entry = (entry, f"{cur['matched']['lat']}, {result['matched']['lng']}")
                address.append(entry)
        return address
    else:
        print(f"Failed to query TOMS for {address}")
        return [address] if return_candidates else address



# ------------- Data Cleaning ----------------------- #

# Fix most common syntax issues
def cleanText(text, translate=False, printing=True):

    text = text.strip()

    if translate:
        text = anglicize(text)

    apos_replacements = [
        "′",
        "`",
        "'",
        "ʻ",
        "ʼ",
        "´",
        "ʹ",
        "'",
        "ʽ",
        "ʾ",
        "ʿ",
        "ˈ",
        "ˊ",
        "ˮ",
        "ʹ",
        "΄",
        "՚",
        "׳",
        "᾽",
        "᾿",
        "‘",
        "’",
        "‛",
        "′",
        "‵",
        "Ꞌ",
        "ꞌ",
        "＇",
        "'",
    ]
    for cur in apos_replacements:
        text = text.replace(cur, "'")

    # If not a contraction, assume the apostrophe is the end of the string
    if text[-1] == "'" and text[-2] not in ["s", "t"]:
        text = text[:-1]

    other_replacements = {
        "  ": " ",
        "\t": " ",
        "\x81N": "ñ",
        "\u202a": "",
        "\u200b": "",
        "\u202c": "",
        "\u202d": "",
        "\u0026": "&",
        "'\xa0'": "",
    }
    for cur in other_replacements:
        text = text.replace(cur, other_replacements[cur])

    checkGSMEncoding(text, printing)

    return text


def checkGSMEncoding(text, printing=True):

    if text != text:
        return True
    else:
        text = str(text)
    # GSM 7-bit basic character set
    gsm_7bit_charset = (
        "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1BÆæßÉ !\"#¤%&'()*+,"
        "-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
    )

    # Extended GSM 7-bit characters (require escape character \x1B)
    gsm_7bit_extended = {
        "^": "\x1B\x14",
        "{": "\x1B\x28",
        "}": "\x1B\x29",
        "\\": "\x1B\x2F",
        "[": "\x1B\x3C",
        "~": "\x1B\x3D",
        "]": "\x1B\x3E",
        "|": "\x1B\x40",
        "€": "\x1B\x65",
        "–": " ",
        "-": " ",
    }

    # Find non-GSM characters
    non_gsm_chars = {char for char in text if char not in gsm_7bit_charset and char not in gsm_7bit_extended}

    if len(list(non_gsm_chars)) > 0:
        if printing:
            print(f"'{text}' contains the following invalid chars: \n{list(non_gsm_chars)}\n\n")
        return False
    return True


# Convert all school names to their district one, if possible
def convertDistrictKids(school_name, collapse_all_districts=False, for_invoicing=False):

    if (
        school_name in df_toms_schools["District"].unique()
        or school_name in df_toms_schools.loc[df_toms_schools["District"].isna(), "School"].unique()
        or school_name in always_convert
    ):
        return school_name
    else:
        try:
            district = df_toms_schools.loc[df_toms_schools["School"] == school_name, "District"].mode()[0]
            if collapse_all_districts | (for_invoicing & (district in convert_for_invoicing)):
                return district
        except:
            # print("Error with finding the district for", school_name)
            pass

    return school_name


def standardizeRouteName(route_name):
    not_riding_vendors = ["Unassigned", "WALK", "DISTANCE", "PPU", "CARPOOL", "TRANSIT"]

    if "(archived" in route_name:
        route_name = route_name[: route_name.rfind("archived") - 1]
    arr = route_name.split("_")
    for i in range(1, len(arr)):
        if arr[i] == "":
            continue
        # Leave Field trips or routes with camelCase or PascalCase alone
        if arr[i][:2] == "FT" or (arr[i] != arr[i].upper() and arr[i].lower()) or (arr[i] in not_riding_vendors):
            continue
        arr[i] = arr[i].title() if arr[i].upper() not in ["SS"] else arr[i]
        if arr[i][0] == "0":
            arr[i] = arr[i][1:]
    arr = [entry for entry in arr if entry == entry and entry != ""]

    return "_".join(arr).replace(" ", "")



# ------------- School Data Lookup ----------------------- #


# Generic comparison function to check if the given value matches a known school field and return
# the requested matching entry's info
def compareToSchools(string_to_comp, field_to_comp, fields_to_return=None):
    string_to_comp = str(string_to_comp)
    if fields_to_return is None:
        fields_to_return = []
    found = False

    fields_to_return = fields_to_return if isinstance(fields_to_return, list) else [fields_to_return]

    return_value = [] if len(fields_to_return) > 0 else nan
    # Certain fields need to be processed differently
    if field_to_comp not in ["School", "Code", "State", "Pod"]:
        # if field_to_comp == "Street":
        #     # if the requested filed is the street, we only want the street part of the address
        #     string_to_comp = convertAddress(string_to_comp, True)
        # else:
        #     string_to_comp = convertAddress(string_to_comp)
        string_to_comp = cleanText(string_to_comp)
    else:
        string_to_comp = string_to_comp.title() if field_to_comp in "School" else string_to_comp.upper()

    values = list(df_toms_schools[field_to_comp].unique())

    for cur_value in values:
        if cur_value.title() == string_to_comp.title():
            found = True
            for i in range(len(fields_to_return)):
                return_value.append(
                    list(df_toms_schools[fields_to_return[i]].loc[df_toms_schools[field_to_comp] == cur_value].unique())
                )

    # If no fields were specified, return boolean
    if fields_to_return == "":
        return found

    # If no match was found, return [nan]
    if not return_value or return_value != return_value:
        return [nan]

    return_value = return_value[0] if len(return_value) == 1 else return_value

    if nan in return_value:
        return_value.remove(nan)

    if len(return_value) == 0:
        print(f"Fields = {fields_to_return}")
        if fields_to_return[0] == "Hours off Central":
            print(f"Failed to find {field_to_comp} for {string_to_comp} so I'm assuming they're Ramsey")
            return df_toms_schools[fields_to_return[0]].loc[df_toms_schools["District"] == "Ramsey Cty-Foster"].unique()
        print(f"Failed to find {field_to_comp} for {string_to_comp} so I have nothing to return")
    return return_value


def getAccountsFieldFromSchool(school, field):
    if not initialized:
        print(f"Error: Common has not been initialized")
        return
    if len(school) == 3:
        try:
            val = df_accounts[field].loc[df_accounts["School Alpha"] == school].max()
            if val != val or len(val) < 1:
                raise Exception
            return val
        except:
            return df_accounts[field].loc[df_accounts["District Alpha"] == school].max()
    else:
        try:
            val = df_accounts[field].loc[df_accounts["School Name"] == school].max()
            if val != val or len(val) < 1:
                raise Exception
            return val
        except:
            return df_accounts[field].loc[df_accounts["District"] == school].max()


# Determine what kind of school is being requested based on the input and return the relevent data
def getSchoolFromAlphaOrState(text):
    text = text.upper()
    if len(text) == 2 or text == "":
        return getSchoolsInState(text)
    else:
        return getSchoolFromAlpha(text)


def getSchoolsInDistrict(school):
    if school in df_toms_schools["District"].unique():
        return df_toms_schools.loc[df_toms_schools["District"] == school, "School"].unique()
    return [school]


def getHotlineForSchool(school):
    if not initialized:
        print(f"Error: Common has not been initialized")
        return
    if school in df_toms_schools["School"].unique():
        return df_toms_schools.loc[df_toms_schools["School"] == school, "Hotline"].unique()
    return [""]


# Determine what kind of school is being requested based on the input and return the relevent data
def getStateFromAlphaOrName(text):
    if len(text) == 3:
        text = text.upper()
        if text in df_toms_schools["District Alpha"].unique():
            return compareToSchools(text, "District Alpha", ["State"])[0]
        return compareToSchools(text, "Code", ["State"])[0]
    else:
        if text in df_toms_schools["District"].unique():
            return compareToSchools(text, "District", ["State"])[0]
        return compareToSchools(text, "School", ["State"])[0]


# Get all of the known schools in the given state
def getSchoolsInState(state_initials, get_alpha = False):
    
    if state_initials == "":
        arr = []
        for cur_state in ["MN", "TX", "IN", "AZ"]:
            arr.append(getSchoolsInState(cur_state, get_alpha))
            return sum(arr, [])
    
    schools = compareToSchools(state_initials, "State", ["Code" if get_alpha else "School"])
    districts = compareToSchools(
        state_initials, "State", ["District Alpha" if get_alpha else "District"]
    )
    
    try:
        schools = list(set(list(schools) + list(districts)))
    except:
        return []
    
    for entry in always_convert:
        try:
            remove_schools = compareToSchools(
                entry, "District", ["Code" if get_alpha else "School"]
            )
            schools -= remove_schools
        except:
            pass
    
    try:
        schools -= nan
    except:
        pass
    return schools


# Get all of the known schools in the given state
def getSchoolsInPod(pod_name, get_alpha = False, getDistricts = False):
    if not initialized:
        print(f"Error: Common has not been initialized")
        return
    schools = compareToSchools(pod_name, "Pod", ["Code" if get_alpha else "School"])
    districts = compareToSchools(pod_name, "Pod", ["District Alpha" if get_alpha else "District"])
    
    schools = list(set(list(schools) + list(districts))) if getDistricts else list(
        set(list(schools))
    )
    
    for entry in always_convert:
        try:
            remove_schools = compareToSchools(
                entry, "District", ["Code" if get_alpha else "School"]
            )
            schools -= remove_schools
        except:
            pass
    
    try:
        schools -= nan
    except:
        pass
    return sorted(schools)


# Gets the school name from a student's alpha code
def getSchoolFromID(student_id):
    school_code = str(student_id).split("_")[0]
    return getSchoolFromAlpha(school_code)


# Gets the school name from a student's alpha code
def getSchoolFromAlpha(alpha):
    if alpha in df_toms_schools["District Alpha"].unique():
        return list(df_toms_schools.loc[df_toms_schools["District Alpha"] == alpha, "School"].unique())

    return compareToSchools(alpha, "Code", ["School"])[0]


def isValidTomsData(val, column):
    return val in df_toms_schools[column].unique()

# Get the address for a specific school
def getSchoolAddress(school_name):
    return compareToSchools(school_name, "School", ["Street"])[0]


# Get the address for a specific school
def getFullSchoolAddress(school_name):
    return compareToSchools(school_name, "School", ["Address"])[0]


# Get the address TOMS has for the given school
def getTOMSSchoolAddress(school_name):
    return df_toms_schools["Address"].loc[df_toms_schools["School"] == school_name].max()


# Get the school for a specific address
def getSchoolFromAddress(school_address):
    return compareToSchools(school_address, "Street", ["School"])[0]


# Get the alpha code for a specific school
def getAlphaFromSchool(school_name):

    if school_name == "" or school_name != school_name:
        return ""

    if school_name in df_toms_schools["District"].unique():
        return df_toms_schools.loc[df_toms_schools["District"] == school_name, "District Alpha"].mode()[0]
    if school_name == "Beacons Network":
        return "BCN"
    elif school_name == "Phalen Detroit Harperwoods":
        return "DCH"
    elif school_name == "Hogan Prep Academy":
        return "HPA"
    elif school_name == "St Mark's Catholic Church":
        return "SMC"
    return compareToSchools(school_name, "School", ["Code"])[0]


# Get the lat/longs for a specific school
def getSchoolLatLongs(school_name):
    return_value = compareToSchools(school_name, "School", ["Lat", "Long"])
    try:
        if len(return_value) == 2:
            return [return_value[0][0], return_value[1][0]]
        raise Exception
    except Exception:
        temp = []

        # iterate through the schools to compare their given field to the provided string
        for index, row in df_toms_schools.iterrows():
            if school_name in row["School"]:
                temp.extend((row["Lat"], row["Long"]))
                break
        return_value = temp
    return return_value


# Get a school name from an address, cleans up some addresses before calling checkIfAtSchool
def getSchoolName(address_to_check):
    # NAN check
    if address_to_check != address_to_check:
        return address_to_check

    try:
        if extra_space := search(r"\d", address_to_check):
            address_to_check = address_to_check[extra_space.start() :]
    except:
        print(f"Failed to process address {address_to_check}")
        quit(1)

    # Remove anything after a comma in the address before checking (city, state, zip, etc)
    address_to_check = convertAddress(str(address_to_check).split(",")[0])

    return checkIfAtSchool(address_to_check)


# Check if a given address matches a listed school address and return the school name
def checkIfAtSchool(address_to_check, cutoff=90):
    address_to_check = convertAddress(address_to_check, True)

    school_addresses = df_toms_schools["Street"]

    school_addresses = [convertAddress(x, True) for x in school_addresses]

    match = process.extractOne(address_to_check, school_addresses, score_cutoff=cutoff)
    if match:
        return df_toms_schools.iloc[match[2]]["School"]
    return nan


# Check if a given address matches a listed school address and return a boolean
def checkIfSchool(address_to_check, cutoff=90):
    address_to_check = convertAddress(address_to_check, True)

    school_addresses = list(df_toms_schools["Street"].unique())

    school_addresses = [convertAddress(x, True) for x in school_addresses]

    match = process.extractOne(address_to_check, school_addresses, score_cutoff=cutoff)
    if match:
        return True
    return False


def fuzzyMatchSchool(given_name, cutoff=90):
    schools = list(df_toms_schools["School"].unique())

    match = process.extractOne(given_name, schools, scorer=fuzz.token_sort_ratio, score_cutoff=cutoff)
    if match:
        return df_toms_schools.iloc[match[2]]["School"]
    return given_name


initialize()

if __name__ == "__main__":
    print()
    # generateRequirementsFile()
