import pandas as pd

import warnings
import os
from numpy import nan
from ..GoogleApi import GetRoutedDistanceFromAddresses, ReverseGeocode
from ..BatchGeocode import BatchRoutedDistance, BatchGeocode, BatchReverseGeocode

from ...Common import generateMasterFile, getPreviousRun, archiveRun, convertAddress


warnings.simplefilter(action="ignore", category=FutureWarning)
warnings.simplefilter(action="ignore", category=UserWarning)

# Removes warnings about editing copies in pandas
pd.options.mode.chained_assignment = None

# Global script level flag used to determine if all output should be logged, or just the important details
debug_flag = True

home_columns = ["Primary Address"]

stop_columns = ["New AM", "New PM", "AM Stop", "PM Stop"]


def main(full_output=True):
    global debug_flag
    debug_flag = full_output

    # If no file is in the run files, we must be redoing the last run (1 is the gitkeep file)
    if len(next(os.walk(os.path.dirname(__file__) + "\\Run Files\\Input\\"))[2]) == 1:
        # If redoing a run, move the last run's data into the Run Files folders
        getPreviousRun(os.path.dirname(__file__))

    if debug_flag:
        print("Printing full debug-level output\n")

    os.chdir(os.path.dirname(__file__))
    df = generateMasterFile(os.path.dirname(__file__) + "\\Run Files\\Input")
    # df["New AM"] = ""
    # df["New PM"] = ""

    # df = BatchReverseGeocode(df, "AM Lat", "AM Lon", "New AM")
    # df = BatchReverseGeocode(df, "PM Lat", "PM Lon", "New PM")

    # count = 0
    # for cur in ["AM", "PM"]:
    #     df_temp = df.groupby(f"{cur} Stop")
    #     for stop, rows in df_temp:
    #         if stop == stop and stop != "":
    #             count += 1
    #             df.loc[rows.index, f"New {cur}"] = ReverseGeocode(
    #                 rows[f"{cur} Lat"].mode()[0], rows[f"{cur} Lon"].mode()[0]
    #             )
    #             if count % 100 == 0:
    #                 print(cur, count)

    # df["New AM"] = [ReverseGeocode(x, y) if x == x and y == y else "" for x, y in zip(df["AM Lat"], df["AM Lon"])]
    # df["New PM"] = [ReverseGeocode(x, y) if x == x and y == y else "" for x, y in zip(df["AM Lat"], df["AM Lon"])]

    for cur in stop_columns:
        df[f"Walk-to-stop for {cur}"] = nan
        df = BatchRoutedDistance(df, "Primary Address", cur, f"Walk-to-stop for {cur}", "Diagnostics - DUV", "walk")
        print("\n")

    df.to_csv(os.path.dirname(__file__) + "\\Run Files\\Output\\Test.csv", index=False)
    archiveRun(os.path.dirname(__file__))


# If running this file, run the Main function
if __name__ == "__main__":
    main()
