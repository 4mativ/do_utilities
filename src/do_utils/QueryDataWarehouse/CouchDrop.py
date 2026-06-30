import os
from time import time

from boto3 import client
from pandas import options

from ..Common import getCreds
from QueryDataWarehouse import createS3Connection

# Removes a warning about chaining assignments
options.mode.chained_assignment = None


# Takes in the range of dates of data to provide and the type of report to pull
def getCouchDropData(
    file_path="",
):

    if not os.path.exists(f"{os.path.dirname(__file__)}/consulting/{file_path.split('/')[-1]}"):
        os.makedirs(f"{os.path.dirname(__file__)}/consulting/{file_path.split('/')[-1]}")

    s3, bucket = createS3Connection("prod", True)

    response = s3.list_objects_v2(Bucket=bucket, Prefix=file_path)

    file_paths = response.get("Contents", [])
    file_paths = [x["Key"] for x in file_paths]

    try:
        file_paths = list(set(file_paths))
        file_paths.remove(file_path)
    except:
        pass

    for cur_file_path in file_paths:

        try:
            s3.download_file(
                bucket,
                cur_file_path,
                f"{os.path.dirname(__file__)}/consulting/{cur_file_path.split('/')[-2]}"
                f"/{cur_file_path.split('/')[-1]}",
            )

        except:
            print(f"Error processing: {cur_file_path}")


# Test the system and save a copy of the pulled data locally, this script is mainly intended to
# have its functions be called by other scripts
def test():
    getCouchDropData("PWCS/Ridership Audit Blank Sheets/20251029 by Vehicle")


if __name__ == "__main__":
    start_time = time()

    test()
    print(f"--- {time() - start_time} seconds ---")
