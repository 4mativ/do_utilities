from google.cloud import bigquery

# ------------------------------trips_db----------------------------------------

# Remapping dictionary for columns
trips_db_to_sql = {
    "InvoiceRun": "invoice_run",
    "School Year": "school_year",
    "LegID": "leg_id",
    "Vendor": "vendor",
    "School": "school",
    "Trip Type": "trip_type",
    "BookingID": "booking_id",
    "Date": "date",
    "PUTime": "pu_time",
    "Direction": "direction",
    "RouteName": "route_name",
    "Mode": "mode",
    "StudentName": "student_name",
    "Program": "program",
    "Stop": "stop",
    "Status": "status",
    "Miles": "miles",
    "StudentCount": "student_count",
    "OriginalTotalCost": "original_total_cost",
    "OriginalCostperLeg": "original_cost_per_leg",
    "CostAdjustment": "cost_adjustment",
    "FinalTotalCost": "final_total_cost",
    "FinalCostperLeg": "final_cost_per_leg",
    "4mativAllocation": "allocation",
    "CostperLegwAllocation": "cost_per_leg_w_allocation",
    "Invoice": "invoice",
    "StudentID": "student_id",
    "ArchiveTimestamp": "archive_timestamp",
    "RecordID": "record_id",
}

# Reverse remapping dict to go other direction
sql_to_trips_db = dict([(value, key) for key, value in trips_db_to_sql.items()])

# Column variable types
trips_db_sql_schema = [
    bigquery.SchemaField("invoice_run", bigquery.enums.SqlTypeNames.DATE),
    bigquery.SchemaField("school_year", bigquery.enums.SqlTypeNames.INT64),
    bigquery.SchemaField("leg_id", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("vendor", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("school", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("trip_type", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("booking_id", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("date", bigquery.enums.SqlTypeNames.DATE),
    bigquery.SchemaField("pu_time", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("direction", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("route_name", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("mode", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("student_name", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("program", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("stop", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("status", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("miles", bigquery.enums.SqlTypeNames.FLOAT),
    bigquery.SchemaField("student_count", bigquery.enums.SqlTypeNames.INT64),
    bigquery.SchemaField("original_total_cost", bigquery.enums.SqlTypeNames.FLOAT),
    bigquery.SchemaField("original_cost_per_leg", bigquery.enums.SqlTypeNames.FLOAT),
    bigquery.SchemaField("cost_adjustment", bigquery.enums.SqlTypeNames.FLOAT),
    bigquery.SchemaField("final_total_cost", bigquery.enums.SqlTypeNames.FLOAT),
    bigquery.SchemaField("final_cost_per_leg", bigquery.enums.SqlTypeNames.FLOAT),
    bigquery.SchemaField("allocation", bigquery.enums.SqlTypeNames.FLOAT),
    bigquery.SchemaField("cost_per_leg_w_allocation", bigquery.enums.SqlTypeNames.FLOAT),
    bigquery.SchemaField("invoice", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("student_id", bigquery.enums.SqlTypeNames.STRING),
    bigquery.SchemaField("archive_timestamp", bigquery.enums.SqlTypeNames.TIMESTAMP),
    bigquery.SchemaField("record_id", bigquery.enums.SqlTypeNames.STRING),
]
