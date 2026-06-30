import os
from glob import glob
from shutil import move

import pandas as pd
from pandas import to_datetime
import numpy as np

import SqlTableVariables as variables
from ..Common import generateMasterFile, getCreds, getInput, convertDistrictKids
from ..Constants import f_year
from google.cloud import bigquery
from google.oauth2 import service_account
from datetime import datetime

# BigQuery access data
credentials = service_account.Credentials.from_service_account_info(getCreds("google-drive"))
client = bigquery.Client(credentials=credentials, project=credentials.project_id)

trips_table_name = "finance-450221.finance_data.TripData"


# Connect to the given db and add the given db to it with the passed
# 'if_exists' option
def writeDfToDb(df, table_name="", dtype_dict=None, option="WRITE_APPEND"):

    if dtype_dict is None:
        dtype_dict = variables.trips_db_sql_schema

    if table_name == "":
        table_name = trips_table_name

    job_config = bigquery.LoadJobConfig(
        schema=dtype_dict,
        write_disposition=option,
    )

    # Load table from dataframe
    job = client.load_table_from_dataframe(df, table_name, job_config=job_config)
    job.result()  # Wait for result
    # Get table info
    table = client.get_table(table_name)
    print("{} is now {} rows and {} columns after adding data".format(table_name, table.num_rows, len(table.schema)))


# Generic function for executing a SQL statement on a given connection to a db
def executeStatement(
    stmt=None,
    conversion_dict=None,
    save_as_csv=False,
    return_a_df=True,
    include_previous_years=False,
    include_archived=False,
):

    if conversion_dict is None:
        conversion_dict = variables.sql_to_trips_db

    if "delete" in stmt.lower():
        response = getInput(
            f"You've selected the option to delete entries from a database, is that correct? (y/n)", True
        )

        if not response:
            print(f"Cancelling operation")
            return

    # Attempt to convert SQL statement to a text object if needed
    try:
        if not include_previous_years:
            start = " and " if "where" in stmt.lower() else " where "
            stmt += start + f"school_year = {f_year}"
        if not include_archived:
            start = " and " if "where" in stmt.lower() else " where "
            stmt += start + f"archive_timestamp is null"
        sql_stmt = stmt.replace("  ", " ")
    except Exception:
        sql_stmt = stmt

    df = client.query_and_wait(sql_stmt).to_dataframe(create_bqstorage_client=True)

    # If the statement affected any rows
    if len(df) > 0:
        if "regexp_extract(record_id,r'(.*)-.*')" in sql_stmt:
            return df
        print(f"The statement '{sql_stmt}' was executed on {len(df)} rows")

        # If we are saving the output, convert it to a df to return as-is
        # and/or to save as a csv
        if save_as_csv or return_a_df:
            if "delete" in stmt.lower():
                df = pd.DataFrame()
                print(f"Can't return deleted files from this function, call from updateDb")
            else:
                try:
                    # Convert df from sql columns to expected
                    df = convertColumns(df, conversion_dict)
                except:
                    print(f"Failed to convert df after running stmt {sql_stmt}")

        # Save as query output csv, if expected
        if save_as_csv:
            df.to_csv(os.path.dirname(__file__) + "/Output/QueryOutput.csv", index=False)

        # Return the df, if expected
        if return_a_df:
            return df

    else:
        print(f"The statement '{sql_stmt}' was executed with no output")
        return pd.DataFrame()


# Helper function for swapping between tripsdb and sql headers
def convertColumns(df, converter_dict):
    # Use pandas built in name re-mapper to change the column names
    df = df.rename(columns=converter_dict)

    # Regardless of which type of df we are using, the date and invoice run
    # need to be a date object
    try:
        df["Date"] = to_datetime(df["Date"])
        df["InvoiceRun"] = to_datetime(df["InvoiceRun"]).dt.date
        if not df["ArchiveTimestamp"].isnull().all():
            try:
                df["ArchiveTimestamp"] = [None if x != x else x for x in df["ArchiveTimestamp"]]
                df["ArchiveTimestamp"] = to_datetime(df["ArchiveTimestamp"])
            except:
                print("Couldn't convert ArchiveTimestamp")
                pass

    except Exception:
        try:
            df["date"] = to_datetime(df["date"]).dt.date
            df["invoice_run"] = to_datetime(df["invoice_run"]).dt.date
            if not df["archive_timestamp"].isnull().all():
                try:
                    df["archive_timestamp"] = [None if x != x else x for x in df["archive_timestamp"]]
                    df["archive_timestamp"] = to_datetime(df["archive_timestamp"])
                except:
                    print("Couldn't convert archive_timestamp")
                    pass
        except Exception:
            print("Failed to convert date columns from text")
            pass
    return df


# Execute the given query on the trips DB
def queryTripsDb(query, include_previous_years):
    return executeStatement(query, return_a_df=True, include_previous_years=include_previous_years)


def updateDbFromFolder(table, school_year=f_year, column_conversion=variables.trips_db_to_sql):
    os.chdir(os.path.dirname(__file__))
    df_update = generateMasterFile(os.path.dirname(__file__) + "\\Upload")

    if "School Year" not in df_update.columns:
        df_update = convertColumns(df_update, variables.sql_to_trips_db)

    if table == trips_table_name:
        df_update["School"] = [convertDistrictKids(x, for_invoicing=True) for x in df_update["School"]]

    try:
        df_update = df_update[df_update["ArchiveTimstamp"].isna()]
    except:
        pass

    df_update = setRecordID(df_update, school_year)

    df_update = convertColumns(df_update, column_conversion)

    df_update = df_update[(df_update["invoice_run"] == df_update["invoice_run"]) & (df_update["invoice_run"] != "")]

    df_test = df_update[df_update["archive_timestamp"].isna()]

    if len(df_test) != len(df_test["leg_id"].unique()):
        print(
            f"ERROR: THERE ARE {len(df_test) - len(df_test['leg_id'].unique())} duplicate Leg "
            f"IDs in this file, cancelling operations"
        )
        df_update = convertColumns(df_update, dict([(value, key) for key, value in column_conversion.items()]))
        df_update["Count"] = df_update.groupby("LegID")["LegID"].transform("count")
        df_update2 = df_update[df_update["Count"] > 1].sort_values(by=["LegID", "InvoiceRun", "Date"])
        df_update2.to_csv(os.path.dirname(__file__) + "\\Output\\Dupes.csv", index=False)
        df_update = df_update[df_update["Count"] == 1]
        df_update.to_csv(os.path.dirname(__file__) + "\\Output\\Fine.csv", index=False)

        return
    updateDb(table, df_update, school_year)


# Update the trips db by either replacing existing entries or adding new ones
# from the given df
def updateDb(table, df_update, school_year=f_year):
    response = getInput(f"You've selected to update the {table} table, is that correct? (y/n)", True)

    if not response:
        print(f"Cancelling operation")
        return

    # If the df has an index, get rid of it to avoid issues
    try:
        df_update = df_update.drop(columns=["index"])
    except Exception:
        pass

    # Get a list of the leg IDs for the entries being edited/added
    ids = list(df_update["leg_id"].loc[df_update["school_year"] == school_year].unique())

    # Find any un-archived entries in the DB with those Leg Ids so we can archive them
    stmt = f"select * from {trips_table_name} where leg_id in UNNEST(@leg_ids) and archive_timestamp is null"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("leg_ids", "STRING", ids),
        ]
    )
    df = client.query_and_wait(stmt, job_config=job_config).to_dataframe()

    if len(df) > 0:
        df = convertColumns(df, variables.trips_db_to_sql)
        df.sort_values(by="leg_id", inplace=True)
        dupe_ids = df["leg_id"].unique()

        if len(df) != len(dupe_ids):
            print(
                f"There are {len(df) - len(dupe_ids)} entries in the TripsDB related to the file you're "
                f"uploading! Their invoice runs are {df['invoice_run'].unique()}"
            )
            df.to_csv(os.path.dirname(__file__) + "/Output/CurrentEntries.csv", index=False)
            quit(1)
            df.drop_duplicates(subset=["leg_id"], inplace=True)

        df_test = df_update[df_update["leg_id"].isin(dupe_ids)]

        df = df.set_index("leg_id")
        df_test = df_test.set_index("leg_id")
        df.sort_index(inplace=True)
        df_test.sort_index(inplace=True)
        test = df.compare(df_test, result_names=("BQ", "Upload"))

        if len(test) > 0:
            display_text = "This action will mark {:,.0f}".format(len(df)) + " current entries as archived"
            display_text += " and then add {:,.0f}".format(len(df_update)) + " entries"
            display_text += ", proceed? (y/n)"
            response = getInput(display_text, True)
            if not response:
                print(f"Cancelling operation")
                df.to_csv(os.path.dirname(__file__) + "/Output/PotentiallyArchivedEntries.csv", index=False)
                return
            archive_ids = list(df["record_id"].unique())
            df.to_csv(os.path.dirname(__file__) + "/Output/ArchivedEntries.csv", index=False)

            # Set the timestamp for all archived legs
            stmt = (
                f"update {trips_table_name} set archive_timestamp = CURRENT_TIMESTAMP() where record_id in UNNEST("
                f"@records)"
            )
            job_config2 = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ArrayQueryParameter("records", "STRING", archive_ids),
                ]
            )
            client.query_and_wait(stmt, job_config=job_config2)

    # Uploaded legs can't be archived already
    df_update["archive_timestamp"] = None
    # Add the updated/new rows to the end of the db
    df_invoice_run = df_update.groupby("invoice_run")
    for invoice_run, rows in df_invoice_run:
        print(f"\n\nUploading Invoice Run: {invoice_run}")
        writeDfToDb(rows, table)
        print(f"Added {len(rows)} entries to {table}")

    files = glob(os.path.dirname(__file__) + "/Upload/*")
    for f in files:
        temp = f.replace("/Upload", "")
        move(f, temp)


# Get a df of all the trips in a given month
def getTripsInMonths(months, year_to_use=f_year):

    stmt = (
        f"Select * from {trips_table_name} where EXTRACT(MONTH from date) in ({",".join(months)}) and school_year ="
        f" {year_to_use}"
    )

    return executeStatement(stmt)


# Get a df of the tripsDB entries for the latest invoice run
def getLatestInvoiceRun(recent_runs_to_skip_over=0, runs_to_grab=1, only_mgmt=False, include_previous_years=True):

    sql_stmt = f"SELECT * from {trips_table_name} where "

    if only_mgmt:
        sql_stmt += "trip_type = 'management' and "

    sql_stmt += "invoice_run in "

    sub_stmt = f"(SELECT invoice_run from {trips_table_name} "

    if not include_previous_years:
        sub_stmt += f"where school_year = {f_year} "

    sub_stmt += (
        f"Group by invoice_run "
        f"order by invoice_run DESC "
        f"LIMIT {runs_to_grab} "
        f"OFFSET {recent_runs_to_skip_over})"
    )

    sql_stmt += sub_stmt

    df = executeStatement(
        stmt=sql_stmt,
        conversion_dict=variables.trips_db_to_sql,
        return_a_df=True,
        include_previous_years=include_previous_years,
    )

    if df is None and recent_runs_to_skip_over < 10:
        print("Failed to find data, trying further back")
        recent_runs_to_skip_over += runs_to_grab
        return getLatestInvoiceRun(recent_runs_to_skip_over, runs_to_grab, only_mgmt)

    elif not df.empty:
        return convertColumns(df, variables.sql_to_trips_db)
    else:
        print(f"The statement '{sql_stmt}' was executed with no output")
        return pd.DataFrame()


def getTripsForYear(year=f_year):
    return executeStatement(
        f"SELECT * from {trips_table_name} where school_year = {year}",
        save_as_csv=False,
        return_a_df=True,
        include_previous_years=True,
    )


def getLastRecordID(year=f_year):

    df = executeStatement(
        f"SELECT school_year, ifnull(format('%s-%d', any_value(year), max(CAST(id_val as INT64))),any_value("
        f"record_id)) as record_id FROM  (select *, regexp_extract(record_id, r'.*-(.*)') id_val, regexp_extract("
        f"record_id,r'(.*)-.*') year from `{trips_table_name}`) group by school_year",
        save_as_csv=False,
        return_a_df=True,
        include_previous_years=True,
    )

    last_id = df.loc[df["school_year"] == year, "record_id"].mode()[0]

    print(f"Got the last known ID of {int(last_id[5:])}")

    return int(last_id[5:])


def setRecordID(df, year=f_year):

    if "School Year" not in df.columns:
        df = convertColumns(df, variables.sql_to_trips_db)

    try:
        last_record = getLastRecordID(year)
    except:
        last_record = 0

    if "ArchiveTimestamp" in df.columns:
        df["ArchiveTimestamp"] = [None if x != x else x for x in df["ArchiveTimestamp"]]
    else:
        df["ArchiveTimestamp"] = None
    df["RecordID"] = df.groupby("School Year").cumcount()
    df["RecordID"] = [f"{x}-{y + last_record + 1}" for x, y in zip(df["School Year"], df["RecordID"])]
    return convertColumns(df, variables.trips_db_to_sql)

    # If we ever want to support record_id upload
    if "RecordID" not in df.columns:
        df["ArchiveTimestamp"] = None
        df["RecordID"] = np.nan

    b_new = df["RecordID"].isnull()

    df_new = df[b_new]
    df_old = df[~b_new]

    if not df_new.empty:

        df_new["RecordID"] = df_new.groupby("School Year").cumcount()
        df_new["RecordID"] = [f"{x}-{y + last_record + 1}" for x, y in zip(df_new["School Year"], df_new["RecordID"])]

        if not df_old.empty:
            df = pd.concat([df_old, df_new])
        else:
            df = df_new
    else:
        df = df_old

    return convertColumns(df, variables.trips_db_to_sql)


def getSpecificInvoiceRun(invoice_run=None):

    if invoice_run is None:
        return getLatestInvoiceRun()

    ending = f"invoice_run = '{invoice_run}'"

    print(ending)

    return executeStatement(f"Select * from {trips_table_name} where {ending}")


# Get a df of the tripsDB entries for the latest invoice run
def getYearsMgmt(year):

    sql_stmt = f"SELECT * from {trips_table_name} where school_year = {year} and trip_type = 'management'"

    df = executeStatement(
        stmt=sql_stmt,
        conversion_dict=variables.sql_to_trips_db,
        return_a_df=True,
        include_previous_years=True,
    )

    if not df.empty:
        return convertColumns(df, variables.sql_to_trips_db)
    else:
        print(f"The statement '{sql_stmt}' was executed with no output")
        return pd.DataFrame()


def main():

    actions = {
        1: "Get latest invoice run",
        2: "Update TripsDB via upload",
        3: "Execute Query",
        4: "Get trips in months",
        5: "Get all mgmt fees",
        6: "Get all year",
    }

    action = 2

    match actions[action]:
        case "Get latest invoice run":
            df = getLatestInvoiceRun(0, 1, False)
            df.to_csv(os.path.dirname(__file__) + "\\Output\\InvoiceRuns_bq.csv", index=False)

        case "Update TripsDB via upload":
            updateDbFromFolder(
                table=trips_table_name,
                school_year=f_year,
                column_conversion=variables.trips_db_to_sql,
            )
        case "Execute Query":
            df = executeStatement(
                stmt=f"Select from {trips_table_name} where invoice_run is not null",
                conversion_dict=variables.sql_to_trips_db,
                save_as_csv=True,
                return_a_df=True,
                include_previous_years=False,
                include_archived=False,
            )
            df.to_csv(os.path.dirname(__file__) + "\\Output\\QueryOutput.csv", index=False)
        case "Get trips in months":
            df = getTripsInMonths([9], 2026)
            df.to_csv(os.path.dirname(__file__) + "\\Output\\MonthTrips.csv", index=False)

        case "Get all mgmt fees":
            df = getYearsMgmt(f_year)
            df.to_csv(os.path.dirname(__file__) + "\\Output\\MgmtFees.csv", index=False)

        case "Get all year":
            df = getTripsForYear(f_year)
            df.to_csv(os.path.dirname(__file__) + "\\Output\\Year_entries.csv", index=False)
            print(
                f"There are {len(df)} entries which have {len(df['LegID'].unique())} leg ids and "
                f"{len(df['RecordID'].unique())} record IDs"
            )
        case _:
            print("Action not found")


# Example statements

# "SELECT * from {trips_table_name} where archive_timestamp is not null"

# "DELETE from {trips_table_name} where invoice_run is null"

# Compound statement with or
# ("SELECT * from {trips_table_name} where
# (school = 'Paul Revere Academy' or school = 'KIPP Legacy') and
# trip_type = 'management'")

# Fuzzy match
# "SELECT * from {trips_table_name} where school like '%Etoile Academy%'"

# Use date range
# "SELECT * from {trips_table_name} where date between '2024-01-01' and '2024-01-10'"
# "SELECT * from {trips_table_name} where date > '2024-01-10'"

# Remove fake entries
# "DELETE from {trips_table_name} where school is null"


if __name__ == "__main__":
    # print(getLastRecordID(2026))
    main()
