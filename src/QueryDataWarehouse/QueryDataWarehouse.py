import os
from datetime import datetime
from time import time

import pandas as pd
from boto3 import client
from pandas import concat, DataFrame, DateOffset, options, read_csv, Timestamp, to_datetime

from Common import convertDistrictKids, getCreds
from Constants import color, data_ops_drive, f_year

# Removes a warning about chaining assignments
options.mode.chained_assignment = None


def getLastMonthDataFromWarehouse(report_type="all_trips", profile="prod"):
    today = datetime.now() - pd.DateOffset(months=1)
    min_date = datetime(today.year, today.month, 1)
    max_date = min_date + pd.DateOffset(months=1) - pd.DateOffset(days=1)
    return getDataFromWarehouse(min_date, max_date, report_type, profile)


def getUpdatedRamseyData():

    os.chdir(os.path.dirname(__file__))

    # all_report_types = ["adm", "all_trips", "comms_metrics", "historical_trips", "school_events", "schools", "students", "vehicles"]

    ramsey_students = getLastMonthDataFromWarehouse("students")
    ramsey_schools = getLastMonthDataFromWarehouse("schools")
    ramsey_trips = getLastMonthDataFromWarehouse("all_trips")
    ramsey_days_off = getLastMonthDataFromWarehouse("school_events")
    schools = ramsey_schools["SchoolName"].loc[ramsey_schools["District"] == "Ramsey Cty-Foster"].unique()
    ramsey_students = ramsey_students[ramsey_students["SchoolName"].isin(schools)]
    ramsey_days_off = ramsey_days_off[
        (ramsey_days_off["SchoolName"].isin(schools)) & (ramsey_days_off["SchoolEventType"] == "Days Off")
    ]

    ramsey_students["Student Name"] = [
        " ".join([x.strip(), y.strip()]) for x, y in zip(ramsey_students["FirstName"], ramsey_students["LastName"])
    ]
    ramsey_students["School"] = ramsey_students["SchoolName"]
    ramsey_students["CCI#"] = ["'" + str(x.split("_")[1]) + "'" for x in ramsey_students["ID"]]
    ramsey_students["School TOMS Code"] = [x.split("_")[0] for x in ramsey_students["ID"]]

    ramsey_trips = ramsey_trips[ramsey_trips["SisID"].isin(ramsey_students["ID"].unique())]

    ramsey_trips = ramsey_trips[ramsey_trips["TransportationVendor"] != "Unassigned"]

    save_path = os.path.dirname(__file__).replace(
        "Utilities\\QueryDataWarehouse", "Invoicing\\Ramsey\\InvoiceProcessing"
    )
    os.chdir(save_path)

    ramsey_students.to_csv("All_Ramsey_Students.csv", index=False)

    ramsey_students = ramsey_students[ramsey_students["Status"] == "Active"]
    ramsey_students = ramsey_students[["Student Name", "CCI#", "School", "School TOMS Code"]]

    ramsey_students = ramsey_students.drop_duplicates(subset=["Student Name", "CCI#"])

    previous_ramsey_lookup = pd.read_csv("Ramsey_Lookup_Table.csv")

    ramsey_students = (
        (
            pd.concat([ramsey_students, previous_ramsey_lookup]).drop_duplicates(
                subset=["Student Name", "CCI#", "School"]
            )
        )
        .sort_values(by=["Student Name", "School"])
        .reset_index(drop=True)
    )

    dupe_students = (
        ramsey_students["Student Name"].loc[ramsey_students.duplicated(subset=["Student Name", "CCI#"])].unique()
    )

    if len(dupe_students) > 0:
        print(
            f"There are {len(dupe_students)} extra entries " f"because the below students are under multiple schools\n"
        )
        for cur_dupe in dupe_students:
            print(
                f"{cur_dupe} has entries for "
                f"{ramsey_students['School'].loc[ramsey_students['Student Name']==cur_dupe].unique()}\n"
            )

    ramsey_students.to_csv(os.path.dirname(__file__) + "\\Ramsey Students.csv", index=False)

    ramsey_students.to_csv("Ramsey_Lookup_Table.csv", index=False)
    ramsey_trips.to_csv("Ramsey_All_Trips.csv", index=False)
    ramsey_days_off.to_csv("Ramsey_Days_Off.csv", index=False)


# Connect to the AWS server
def createS3Connection(profile, consulting=False):
    # Read in and process the config for our AWS credentials
    config = getCreds("dw")

    # if the provided profile is not listed, throw an error
    if profile not in config:
        print(f"The profile, {profile}, was not found in your config file")
        quit()

    # Establish a connection to the s3 origin and identify the bucket our data is stored in
    s3 = client(
        "s3",
        aws_access_key_id=config[profile]["aws_access_key_id"],
        aws_secret_access_key=config[profile]["aws_secret_access_key"],
    )
    bucket = config[profile]["bucket"] if not consulting else "4mativ-couchdrop"

    return s3, bucket


def getNewProductData(report_type="all_trips", pull_date=datetime.now() - DateOffset(days=datetime.now().weekday())):
    conversion = {
        "all_trips": "all_trips",
        "old_curb": "weekly_curbside_last_wed",
        "new_curb": "weekly_curbside_next_wed",
        "students": "students",
        "weekly_routes": "weekly_routes",
    }

    if report_type not in conversion:
        print(f"Error: the only supported files for getNewProductData are {conversion.keys()}")
        quit(1)

    if pull_date > datetime(2025, 2, 10):
        # Moved from monday to tuesday
        pull_date = pull_date + DateOffset(days=1)

    report_type = conversion[report_type]

    s3, bucket = createS3Connection("new")

    pull_date = pull_date.strftime("%m.%d.%Y")

    # Request the files from the s3 origin's bucket
    response = s3.list_objects_v2(Bucket=bucket, Prefix=f"{pull_date}/")

    old_curb = []
    new_curb = []
    all_trips = pd.DataFrame()
    students = pd.DataFrame()

    file_paths = response.get("Contents", [])
    file_paths = [x["Key"] for x in file_paths]

    file_paths = [x if report_type in x else "" for x in file_paths]

    try:
        file_paths = list(set(file_paths))
        file_paths.remove("")
    except:
        pass

    for cur_file_path in file_paths:

        try:
            # Request the month's file from the s3 origin's bucket
            response = s3.get_object(Bucket=bucket, Key=cur_file_path)

            # Get the status of the request
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")

            # 200 = Success
            if status == 200:
                df = read_csv(response.get("Body"), low_memory=False)

                if "all_trips" in cur_file_path:
                    all_trips = df
                elif "students" in cur_file_path:
                    students = df
                elif "next_wed" in cur_file_path:
                    new_curb.append(df)
                elif "last_wed" in cur_file_path:
                    old_curb.append(df)
                else:
                    print(f"Not sure what this file is: {cur_file_path}")
            else:
                print(f"Couldn't successfully access {cur_file_path.split('/')[1]}")

        except:
            print(f"Error processing: {cur_file_path.split('/')[1]}")

    if report_type == "all_trips":
        return cleanData(all_trips, datetime.now(), datetime.now(), "all_trips", False)
    elif report_type == "students":
        return students
    elif report_type == "weekly_curbside_last_wed":
        return pd.concat(old_curb)
    elif report_type == "weekly_curbside_next_wed":
        return pd.concat(new_curb)
    else:
        print(f"Error: Missing return logic for {report_type}")
        quit(1)


def getDataForLastXWeeks(weeks_back, report_type="all_trips", offset_weeks=0):
    # Pull today's date to determine the mondays and friday we need
    today = datetime.now()

    weeks_back = weeks_back + offset_weeks

    # Get the monday of the earliest week we want to send data about
    earliest_week_monday = today - DateOffset(days=today.weekday() + 7 * weeks_back)

    # Get the last friday
    last_week_friday = today - DateOffset(days=today.weekday() + 3 + 7 * offset_weeks)

    return getDataFromWarehouse(earliest_week_monday, last_week_friday, report_type)


# Takes in the range of dates of data to provide and the type of report to pull
def getWeeklyDataFromWarehouse(
    min_date_original=datetime.now() - DateOffset(days=7),
    max_date_original=datetime.now(),
    report_type="all_trips",
    profile="prod",
):
    # Type names are stored as underscore separated instead of space
    report_type = report_type.replace(" ", "_").lower()

    # Create an empty dataframe to store data
    arr = DataFrame()

    # Establish a connection to the s3 origin
    s3, bucket = createS3Connection(profile)

    # Convert the min date to its previous monday and the max date to its following sunday as
    # that's the range our data is saved in
    start_of_current_week = min_date_original - DateOffset(days=min_date_original.weekday())
    max_date = max_date_original + DateOffset(days=6 - max_date_original.weekday())

    # Reports are stored by the first and last day of the given week, so we need to know the end
    # date of the first week to pull
    end_of_current_week = start_of_current_week + DateOffset(days=6)

    # While the end of the current week isn't past the date we are working towards
    while max_date >= end_of_current_week:

        # Convert the current week's start and end dates to the expected format
        min_string = start_of_current_week.strftime("%m.%d.%Y")
        mid_string = end_of_current_week.strftime("%m.%d.%Y")

        # Files are stored in filepath "month1.day1.year1-month2.day2.year2/month1.day1.year1
        # -month2.day2.year2-report_type.csv"
        # Where the first date is a monday and the second is the following sunday
        file_path = min_string + "-" + mid_string
        file_path = file_path + "/" + file_path + "-" + report_type + ".csv"

        try:
            # Request the month's file from the s3 origin's bucket
            response = s3.get_object(Bucket=bucket, Key=file_path)

            # Get the status of the request
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")

            # 200 = Success
            if status == 200:
                test = read_csv(response.get("Body"), low_memory=False)
                if report_type == "comms_metrics":

                    # Comms metrics are cumulative, so mark the columns as such for later
                    # calculations
                    for cur in test.columns:
                        if cur != "School" or "sec" not in cur:
                            test["Cumulative " + cur] = test[cur]

                if report_type == "comms_metrics" or report_type == "weekly_routes":
                    # comms_metrics doesn't use any sort of dates, so we need to add our own
                    test["WeekStarting"] = start_of_current_week.strftime("%m/%d/%Y")
            else:
                print(f"Unsuccessful S3 get_object response. Status - {status}")
                print(
                    f"Double check that the data warehouse bucket, {bucket}, houses the desired "
                    f"report at this filepath: {file_path}"
                )
                break

            # increment the current week
            start_of_current_week += DateOffset(days=7)
            end_of_current_week += DateOffset(days=7)

            # Combine current week's report to the master data frame
            arr = concat([arr, test], ignore_index=True)
        except Exception:
            # Failed to get response from s3
            print(
                f"Double check that the data warehouse bucket, {bucket}, houses the desired report "
                f"at this filepath: {file_path}"
            )
            break

    return cleanData(arr, min_date_original, max_date_original, report_type)


# Takes in the range of dates of data to provide and the type of report to pull
def getDailyDataFromWarehouse(
    date_of_data=datetime.now() - DateOffset(days=1), report_type="daily_comms", profile="prod"
):
    # Type names are stored as underscore separated instead of space
    report_type = report_type.replace(" ", "_").lower()

    # Create an empty dataframe to store data
    df = DataFrame()

    # Establish a connection to the s3 origin
    s3, bucket = createS3Connection(profile)

    # Convert the current week's start and end dates to the expected format
    date_string = date_of_data.strftime("%m.%d.%Y")

    # Files are stored in filepath "month.day.year/month.day.year-report_type.csv
    file_path = date_string + "/" + date_string + "-" + report_type + ".csv"

    try:
        # Request the month's file from the s3 origin's bucket
        response = s3.get_object(Bucket=bucket, Key=file_path)

        # Get the status of the request
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")

        # 200 = Success
        if status == 200:
            df = read_csv(response.get("Body"), low_memory=False)
        else:
            print(f"Unsuccessful S3 get_object response. Status - {status}")
            print(
                f"Double check that the data warehouse bucket, {bucket}, houses the desired report "
                f"at this filepath: {file_path}"
            )

    except Exception:
        # Failed to get response from s3
        print(
            f"Double check that the data warehouse bucket, {bucket}, houses the desired report at "
            f"this filepath: {file_path}"
        )

    return cleanData(df, date_of_data, date_of_data, report_type)


# Takes in the range of dates of data to provide and the type of report to pull
def getDataFromWarehouse(
    start_of_current_week=datetime.now() - DateOffset(years=1),
    max_date=datetime.now(),
    report_type="all_trips",
    profile="prod",
):
    # Starting on 9/1/2022 we switched from a monthly report to a weekly one, if the given date
    # range extends over this gap, we need to process them differently
    flag_mixed = False

    local_max_date = max_date

    # Ensure the dates are in the correct format
    if not isinstance(start_of_current_week, datetime) or isinstance(start_of_current_week, Timestamp):
        start_of_current_week = datetime(
            start_of_current_week.year, start_of_current_week.month, start_of_current_week.day
        )
    if not isinstance(max_date, datetime) or isinstance(max_date, Timestamp):
        max_date = datetime(max_date.year, max_date.month, max_date.day)

    # Create an empty dataframe to add our data to
    arr2 = DataFrame()

    if report_type == "daily_comms":
        arr = []
        while start_of_current_week <= max_date:
            arr.append(getDailyDataFromWarehouse(start_of_current_week, report_type))
            start_of_current_week += DateOffset(days=1)
        try:
            return pd.concat(arr)
        except:
            return pd.DataFrame()

    # Starting on 9/1/2022 we switched from a monthly report to a weekly one
    if max_date > datetime(2022, 8, 31):

        # Comms_metrics are cumulative, so we need to pull the previous week's report as well to
        # get the accurate weekly values for the given range
        if report_type == "comms_metrics":
            arr2 = processCommsMetrics(start_of_current_week, max_date, report_type, profile)
        else:
            arr2 = getWeeklyDataFromWarehouse(
                max(start_of_current_week, datetime(2022, 8, 31)), max_date, report_type, profile
            ).reset_index(drop=True)

        # Only pulling data from newer reports
        if start_of_current_week > datetime(2022, 8, 31):
            return arr2

        # Set the max data as the last day of the old reports
        local_max_date = datetime(2022, 8, 31)

        # Pulling data before and after the report change
        flag_mixed = True

    # Type names are stored as underscore separated instead of space
    report_type = report_type.replace(" ", "_").lower()

    # Data is stored by month/year combo, so we don't need the day for these dates
    local_min = start_of_current_week.month
    local_max = local_max_date.month
    min_year = start_of_current_week.year
    max_year = local_max_date.year

    # Need to increment max month (and wrap if over 12) in case both dates are in the same month
    if local_max == 12:
        local_max = 0
        max_year += 1
    local_max += 1

    # Create an empty dataframe to add our data to
    arr = DataFrame()

    # Connect to data warehouse bucket to pull from
    s3, bucket = createS3Connection(profile)

    # Convert the min and max dates to the first of their respective month/year
    fake_min = datetime(min_year, local_min, 1)
    fake_max = datetime(max_year, local_max, 1)

    # For each month needed, pull the report and combine it
    while fake_min < fake_max:

        # Files are stored in filepath month-year/month-year-report_type.csv
        file_path = "{:02d}".format(local_min) + "-" + str(min_year)
        file_path = file_path + "/" + file_path + "-" + report_type + ".csv"

        try:
            # Request the month's file from the s3 origin's bucket
            response = s3.get_object(Bucket=bucket, Key=file_path)

            # Get the status of the request
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")

            # 200 = Success
            if status == 200:
                test = read_csv(response.get("Body"))

            else:
                print(f"Unsuccessful S3 get_object response. Status - {status}")
                print(
                    f"Double check that the data warehouse bucket, {bucket}, houses the desired "
                    f"report at this filepath: {file_path}"
                )
        except Exception:
            print(
                f"Double check that the data warehouse bucket, {bucket}, houses the desired report "
                f"at this filepath: {file_path}"
            )

        # Increment month and wrap if needed (incrementing year)
        local_min += 1
        if local_min > 12:
            local_min = 1
            min_year = str(int(min_year) + 1)
        fake_min += DateOffset(months=1)

        # Combine current month's df to master
        try:
            arr["Date"] = pd.to_datetime(arr["Date"])
            arr = concat([arr, test], ignore_index=True)
        except Exception:
            # Do nothing
            pass
    if flag_mixed:
        arr = concat([arr, arr2], ignore_index=True)

    arr = cleanData(arr, start_of_current_week, max_date, report_type)

    return arr.reset_index(drop=True)


def cleanData(arr, min_date, max_date, report_type, filter_dates=True):
    # If the data is sorted by date, then filter to just the given date range, else remove
    # duplicates between months
    if "Date" in arr.columns:
        arr["Date"] = to_datetime(arr["Date"])
        if filter_dates:
            mask = (arr["Date"] >= min_date) & (arr["Date"] <= max_date)
            arr = arr[mask]

    for cur_col in arr.columns:

        if "route" in cur_col.lower():
            arr[cur_col] = arr[cur_col].str.replace(r" \(.*\)", "", regex=True)
            arr[cur_col] = arr[cur_col].str.replace(r"_0", "_", regex=True)
            arr[cur_col] = arr[cur_col].str.replace(" ", "")

        if "name" in cur_col.lower():
            arr[cur_col] = [x.replace("`", "'").replace("’", "'") if x == x else x for x in arr[cur_col]]

        if "school" in cur_col.lower():

            # if report_type == "weekly_comms":
            # 	arr[cur_col] = [x if x == x else getSchoolFromAlpha(y[:3]) for x, y in zip(arr[
            # 	cur_col], arr['FromName'])]

            # Remove trailing/leading spaces or double spaces from school names
            arr[cur_col] = [x if x != x else str(x).strip().replace("  ", " ") for x in arr[cur_col]]
            # Fix MELA
            arr[cur_col] = [x if x != x or "MELA" not in x else "MELA" for x in arr[cur_col]]

            fake_schools = ["Eastern Middle School", "Blair High School", "Montgomery Test District"]
            arr = arr[~arr[cur_col].isin(fake_schools)]

        if cur_col in ["VehicleType", "Vehicle Type", "Vehicle_Type"]:
            conver = {
                "monitors": "Monitor",
                "stipends": "Stipend",
                "wc van": "WC Van",
                "esy": "ESY",
                "pass through": "Pass Through",
                "PPU": "PPU",
            }

            arr[cur_col] = [conver[x] if x in conver.keys() else str(x).title() for x in arr[cur_col]]

        if cur_col in ["TransportationVendor", "Vendor"]:

            arr[cur_col].fillna("", inplace=True)

            conversions = {
                "Assist": "Assist Services",
                "HopSkipDrive": "HopSkipDrive",
                "AST": "NorthStar-AST",
                "Safe Ride": "Safe Ride",
                "Bille": "Bille",
                "Star Shuttle": "Star Shuttle",
                "First Alt": "First Alt",
                "First Student": "First Student",
                "Pride": "Pride-PTB",
                "Rainbow": "Rainbow/B&W",
                "Eventsource Ministries": "Event Source",
            }

            for cur_conversion in conversions:
                arr.loc[arr[cur_col].str.contains(cur_conversion), cur_col] = conversions[cur_conversion]
            try:
                arr.loc[(arr["Date"] >= datetime(2023, 7, 1)) & (arr[cur_col] == "NorthStar"), cur_col] = (
                    "NorthStar-AST"
                )
            except:
                pass
            # arr[cur_col] = [x.strip().replace("  ", " ").replace(" Bus", "") for x in arr[cur_col]]

    # Short lived change to school name
    arr = arr.replace("Yellowstone Schools", "Yellowstone Academy")

    arr = arr.drop_duplicates()

    return arr


def processCommsMetrics(start_of_current_week, max_date, report_type, profile):
    result = getWeeklyDataFromWarehouse(
        max(start_of_current_week, datetime(2022, 8, 31)) - DateOffset(days=7),
        max_date,
        report_type,
        profile,
    ).reset_index(drop=True)

    # Get the week values so we can remove the extra week we pulled
    weeks = result["WeekStarting"].unique()

    # Group the df by school so that we can compare the school's weekly cumulative values
    df_school = result.groupby("School")

    # Get a list of the df columns
    columns = result.columns

    # Iterate through each school and it's associated entries
    for school, df in df_school:

        # Assign the current cumulative value to the earliest known value
        previous_week = df.iloc[0]

        for index, row in df.iterrows():

            # If the current row has the same week, ignore it (used to not do anything about the
            # previous week pulled earlier)
            if row["WeekStarting"] == previous_week["WeekStarting"]:
                continue

            # Iterate through each of the df columns, using range index to easily refer to related
            # ones
            for i in range(len(columns)):

                # Only touch columns that aren't School, WeekStarting, or marked cumulative
                if (
                    "Cumulative" not in columns[i]
                    and columns[i] != "WeekStarting"
                    and columns[i] != "School"
                    and "(sec)" not in columns[i]
                ):
                    result.loc[index, columns[i]] = row[columns[i]] - previous_week[columns[i]]
                    # result[columns[i]].loc[index] = row[columns[i]] - previous_week[columns[i]]

            # Set the current row's cumulative totals as the previous week's
            previous_week = row

    # Remove the earliest week we pulled only to get accurate weekly values
    result = result[result["WeekStarting"] != weeks[0]]

    # Remove the cumulative columns
    columns = [i for i in columns if "Cumulative" not in i]
    return result[columns]


# Attempts to get a full school years worth of data
def getSchoolYearDataFromWarehouse(year_given_school_year_ends=f_year, report_type="all_trips", profile="prod"):
    # Try to ensure that the year is an accurate 4 digit number
    if "FY" in str(year_given_school_year_ends) or len(str(year_given_school_year_ends)) != 4:
        year_given_school_year_ends = 2000 + int(str(year_given_school_year_ends)[-2:])

    year_given_school_year_ends = int(year_given_school_year_ends)

    # School year X-Y is 7/1/X - 6/30/Y
    start_date = datetime(year_given_school_year_ends - 1, 7, 1)
    max_date = datetime(year_given_school_year_ends, 6, 30)
    return getDataFromWarehouse(start_date, max_date, report_type, profile)


# Gets a monthly report of data, the same process as the old way, but can be done from the new
# weekly reports
def getSchoolYearMonthDataFromWarehouse(school_year, month, report_type="all_trips", profile="prod"):
    # Try to ensure that the year is an accurate 4 digit number
    if "FY" in str(school_year) or len(str(school_year)) != 4:
        school_year = 2000 + int(str(school_year)[-2:])

    school_year = school_year if month < 7 else school_year - 1

    # Convert the given month to a date range to pull
    start_date = datetime(school_year, month, 1)
    max_date = start_date + DateOffset(months=1) - DateOffset(days=1)
    month_data = getDataFromWarehouse(start_date, max_date, report_type, profile)

    # Sometime when we pull data near the end/start of a month, the data is likely incomplete and
    # needs to be supplemented if acting upon
    if "Date" in month_data.columns and month_data["Date"].max() < max_date:
        print(
            color["RED"] + "Be aware that this monthly report appears to be incomplete and you will "
            "likely need to pull the rest of the data directly "
            "from TOMS." + color["END"]
        )

    return month_data


def updateSchools():
    dw_report = getDataForLastXWeeks(1, "schools")

    dw_report = dw_report.drop_duplicates()

    dw_report.to_csv(f"{data_ops_drive}\\Databases\\All_TOMS_schools.csv", index=False)

    dw_report = dw_report[dw_report["Archived"].isna()]
    dw_report.to_csv(f"{data_ops_drive}\\Databases\\TOMS_schools.csv", index=False)


def approximateLastMonthDataFromWarehouse(report_type="all_trips", profile="prod"):
    current_date = datetime.today()
    most_recent_monday = datetime.now() - DateOffset(days=datetime.now().weekday())
    most_recent_tuesday = (
        most_recent_monday + DateOffset(days=1)
        if current_date.day > most_recent_monday.day
        else most_recent_monday - DateOffset(days=6)
    )

    last_verified_date = most_recent_monday - pd.DateOffset(days=1)
    last_forecasted_date = most_recent_tuesday + pd.DateOffset(days=7)

    if last_verified_date.month == last_forecasted_date.month:
        return getSchoolYearMonthDataFromWarehouse(f_year, last_verified_date.month, report_type, profile)
    else:
        month_start = datetime(most_recent_monday.year, most_recent_monday.month, 1)
        month_end = month_start + pd.DateOffset(months=1) - pd.DateOffset(days=1)

        verified_data = getLastMonthDataFromWarehouse(report_type, profile)
        arr = []
        arr.append(getNewProductData(report_type, most_recent_tuesday))
        arr.append(getNewProductData(report_type, most_recent_tuesday - DateOffset(days=7)))
        projected_data = pd.concat(arr)
        projected_data = cleanData(projected_data, last_verified_date, month_end, report_type)
        return pd.concat([verified_data, projected_data]).drop_duplicates().reset_index(drop=True)


# Test the system and save a copy of the pulled data locally, this script is mainly intended to
# have its functions be called by other scripts
def test():
    start_date = datetime(2026, 2, 2)
    max_date = datetime(2026, 2, 6)

    updateSchools()

    all_report_types = [
        "adm",
        "all_trips",  # Also works for prod
        "comms_metrics",
        "historical_trips",
        "school_events",
        "schools",
        "students",  # Also works for prod
        "vehicles",
        "weekly_comms",
        "weekly_routes",
        "daily_comms",
        "new_curb",  # Only for new product data
        "old_curb",
    ]

    report_type = "schools"

    os.chdir(os.path.dirname(__file__))

    selection = 2

    if selection == 0:
        dw_report = getDataFromWarehouse(start_date, max_date, report_type)
    elif selection == 1:
        dw_report = getSchoolYearDataFromWarehouse(2025, report_type)

    elif selection == 2:
        dw_report = getDataForLastXWeeks(1, report_type, 0)
    elif selection == 3:
        dw_report = getSchoolYearMonthDataFromWarehouse(2026, month=1, report_type=report_type)
    elif selection == 4:
        dw_report = getNewProductData(report_type, start_date)
        report_type = f"Product_{report_type}"
    elif selection == 5:
        dw_report = approximateLastMonthDataFromWarehouse(report_type)
    else:
        print("ERROR: Unknown selection number given")
        quit(1)

    if report_type == "weekly_routes":
        today = datetime.today()

        dw_report = dw_report[dw_report["VehicleType"].isin(["Bus", "Cab", "Van"])]
        dw_report["WeekStarting"] = pd.to_datetime(dw_report["WeekStarting"])
        dw_report = dw_report.sort_values(by="WeekStarting", ascending=False)
        dw_report = dw_report.drop_duplicates(subset="Id")
        dw_report = dw_report.sort_values(by="RouteName", ascending=False)
        dw_report["SchoolDistrict"] = [convertDistrictKids(x, True) for x in dw_report["SchoolDistrict"]]
        dw_report["EndDate"] = pd.to_datetime(dw_report["EndDate"])
        dw_report["Archived"] = [today >= x for x in dw_report["EndDate"]]
        dw_report = dw_report[
            [
                "Id",
                "RouteName",
                "Archived",
                "SchoolDistrict",
                "Type",
                "VehicleType",
                "Vendor",
                "StartDate",
                "EndDate",
                "InboundVehicle",
                "InboundPairedRoute",
                "OutboundVehicle",
                "OutboundPairedRoute",
            ]
        ]

    dw_report.to_csv(f"DW_{report_type}.csv", index=False)


if __name__ == "__main__":
    # getNewProductData()
    start_time = time()
    # updateSchools()
    # getUpdatedRamseyData()
    # approximateLastMonthDataFromWarehouse()
    test()
    print(f"--- {time() - start_time} seconds ---")
