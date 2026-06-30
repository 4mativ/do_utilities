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

    df["School Address"] = [f"{x[:-5]}, Jacksonville, FL {x[-5:]}" for x in df["School"]]

    df["Home-to-School"] = nan
    df = BatchRoutedDistance(df, "Primary Address", "School Address", "Home-to-School", "Diagnostics - DUV", "drive")
    print("\n")

    df.to_csv(os.path.dirname(__file__) + "\\Run Files\\Output\\Test.csv", index=False)
    archiveRun(os.path.dirname(__file__))


# If running this file, run the Main function
if __name__ == "__main__":
    main()
