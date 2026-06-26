import os
import time
from concurrent.futures import as_completed
from copy import deepcopy
from glob import glob

import googlemaps
import pandas as pd
import requests

from numpy import nan
from requests_futures.sessions import FuturesSession

from Geocoding.GoogleApi import UpdateQueryDB
from Constants import creds

geo_api = "https://maps.googleapis.com/maps/api/geocode/json"
route_api = "https://maps.googleapis.com/maps/api/directions/json"

gparams = {"key": creds["GOOGLE-MAPS-GKEY"]}

gmaps = googlemaps.Client(key=creds["GOOGLE-MAPS-GKEY"])

os.chdir(os.path.dirname(__file__))
# Read the master query log into memory, used to reduce overall API queries
try:
    query_db = pd.read_csv("QueryDB.csv", low_memory=False)
except Exception:
    # If it doesn't exist, make one
    query_db = pd.DataFrame(
        [], columns=["Lat1", "Long1", "Stop1", "Lat2", "Long2", "Stop2", "Distance", "Route", "Navigation Mode"]
    )


def BatchDistanceRequests(
    df, address_pairs, address_column1, address_column2, distance_column, route, navigation_mode="driving"
):
    global gparams, query_db
    arr_queries = []

    counter = 1
    full = len(address_pairs)

    previously_geocoded = 0
    successes = 0
    fail_star = 0
    fail = 0
    address_results = [[], [], []]
    gparams["mode"] = navigation_mode
    gparams["units"] = "imperial"

    with FuturesSession() as session:
        future_requests = {}
        for i in range(len(address_pairs)):

            pair = address_pairs[i]

            if nan in pair or "" in pair:
                continue

            query_check = query_db[(query_db["Stop1"] == pair[0]) & (query_db["Stop2"] == pair[1])]

            if len(query_check) <= 0:
                request_params = gparams
                request_params["origin"] = pair[0]
                request_params["destination"] = pair[1]
                time.sleep(0.02)
                future = session.get(route_api, params=deepcopy(request_params), timeout=5)
                future_requests[future] = deepcopy(pair)
            else:
                pair_mask = (df[address_column1] == pair[0]) & (df[address_column2] == pair[1])
                # df[distance_column].loc[pair_mask] = query_check["Distance"].max()
                df.loc[pair_mask, distance_column] = query_check["Distance"].max()

                previously_geocoded += 1

        full -= previously_geocoded

        for future in as_completed(future_requests):
            response = future.__getattribute__("_result")
            pair = future_requests[future]

            # print("Had to do a query for", pair)

            try:
                if response.status_code == 200:
                    # Find the data we want from the response data
                    data = response.json()
                    try:
                        results = data["routes"][0]["legs"]
                    except Exception:
                        results = []
                    if len(results) > 0:
                        # Get distance and convert it from a string
                        distance = results[0]["distance"]["text"]

                        # Remove any text which will prevent the conversion to float
                        distance = distance.replace(",", "").replace(" mi", "")

                        # Convert ft to miles
                        if "ft" in str(distance):
                            distance = float(distance.replace(" ft", "")) / 5280.000
                        # Use the meters instead of miles for a more precise result
                        else:
                            distance = round(results[0]["distance"]["value"] / 1609.344, 4)

                        # pull the lat/longs for the stops from the results
                        lat1 = results[0]["start_location"]["lat"]
                        long1 = results[0]["start_location"]["lng"]
                        lat2 = results[0]["end_location"]["lat"]
                        long2 = results[0]["end_location"]["lng"]

                        arr_queries.append(
                            [lat1, long1, pair[0], lat2, long2, pair[1], distance, route, navigation_mode]
                        )

                        successes += 1
                        address_results[0].append(pair)

                        pair_mask = (df[address_column1] == pair[0]) & (df[address_column2] == pair[1])

                        # df[distance_column].loc[pair_mask] = distance
                        df.loc[pair_mask, distance_column] = distance

                    else:
                        print("Failed to find path between", pair)
                        fail_star += 1

                else:
                    # print("Failed to get query result for", pair)
                    fail += 1
            except:
                fail += 1
                continue

            counter += 1

    full += previously_geocoded

    print(
        f"Breakdown:\n"
        f"Previously Coded: {previously_geocoded}/{full}\n"
        f"Success: {successes + previously_geocoded}/{full}\n"
        f"No_matches: {fail_star}/{full}\n"
        f"Failed Queryyy: {fail}/{full}"
    )

    try:
        df_new_queries = pd.DataFrame(
            arr_queries,
            columns=["Lat1", "Long1", "Stop1", "Lat2", "Long2", "Stop2", "Distance", "Route", "Navigation Mode"],
        )

        query_db = pd.concat([query_db, df_new_queries])
        UpdateQueryDB(query_db)
    except:
        print("Failed to update QueryDB")
        pass

    return df


def BatchDistanceRequestsLats(
    df, address_pairs, lat_col1, lon_col1, lat_col2, lon_col2, distance_column, route, navigation_mode="driving"
):
    global gparams, query_db
    arr_queries = []

    counter = 1
    full = len(address_pairs)

    previously_geocoded = 0
    successes = 0
    fail_star = 0
    fail = 0
    address_results = [[], [], []]
    gparams["mode"] = navigation_mode
    gparams["units"] = "imperial"

    with FuturesSession() as session:
        future_requests = {}
        for i in range(len(address_pairs)):

            pair = address_pairs[i]

            if nan in pair or "" in pair:
                continue

            query_check = query_db[
                (query_db["Lat1"] == pair[0])
                & (query_db["Long1"] == pair[1])
                & (query_db["Lat2"] == pair[2])
                & (query_db["Long2"] == pair[3])
            ]

            if len(query_check) <= 0:
                request_params = gparams
                request_params["origin"] = f"{str(pair[0])}, {str(pair[1])}"
                request_params["destination"] = f"{str(pair[2])}, {str(pair[3])}"
                future = session.get(route_api, params=deepcopy(request_params), timeout=5)
                future_requests[future] = deepcopy(pair)
            else:
                pair_mask = (
                    (df[lat_col1] == pair[0])
                    & (df[lon_col1] == pair[1])
                    & (df[lat_col2] == pair[2])
                    & (df[lon_col2] == pair[3])
                )
                df.loc[pair_mask, distance_column] = query_check["Distance"].max()

                previously_geocoded += 1

        full -= previously_geocoded

        for future in as_completed(future_requests):
            response = future.__getattribute__("_result")
            pair = future_requests[future]

            # print("Had to do a query for", pair)

            try:
                if response.status_code == 200:
                    # Find the data we want from the response data
                    data = response.json()
                    try:
                        results = data["routes"][0]["legs"]
                    except Exception:
                        results = []
                    if len(results) > 0:
                        # Get distance and convert it from a string
                        distance = results[0]["distance"]["text"]

                        # Remove any text which will prevent the conversion to float
                        distance = distance.replace(",", "").replace(" mi", "")

                        # Convert ft to miles
                        if "ft" in str(distance):
                            distance = float(distance.replace(" ft", "")) / 5280.000
                        # Use the meters instead of miles for a more precise result
                        else:
                            distance = round(results[0]["distance"]["value"] / 1609.344, 4)

                        # pull the lat/longs for the stops from the results
                        lat1 = results[0]["start_location"]["lat"]
                        long1 = results[0]["start_location"]["lng"]
                        lat2 = results[0]["end_location"]["lat"]
                        long2 = results[0]["end_location"]["lng"]

                        arr_queries.append(
                            [lat1, long1, pair[0], lat2, long2, pair[1], distance, route, navigation_mode]
                        )

                        successes += 1
                        address_results[0].append(pair)

                        pair_mask = (
                            (df[lat_col1] == pair[0])
                            & (df[lon_col1] == pair[1])
                            & (df[lat_col2] == pair[2])
                            & (df[lon_col2] == pair[3])
                        )

                        df.loc[pair_mask, distance_column] = distance

                    else:
                        # print("Failed to find path between", pair)
                        fail_star += 1

                else:
                    # print("Failed to get query result for", pair)
                    fail += 1
            except:
                continue

            counter += 1

    full += previously_geocoded

    print(
        f"Breakdown:\n"
        f"Previously Coded: {previously_geocoded}/{full}\n"
        f"Success: {successes + previously_geocoded}/{full}\n"
        f"No_matches: {fail_star}/{full}\n"
        f"Failed Query: {fail}/{full}"
    )

    try:
        df_new_queries = pd.DataFrame(
            arr_queries,
            columns=["Lat1", "Long1", "Stop1", "Lat2", "Long2", "Stop2", "Distance", "Route", "Navigation Mode"],
        )

        query_db = pd.concat([query_db, df_new_queries])
        UpdateQueryDB(query_db)
    except:
        print("Failed to update QueryDB")
        pass

    return df


def BatchRequests(addresses):
    arr_queries, arr_geocodes = [], []

    counter = 1
    full = len(addresses)

    previously_geocoded = 0
    successes = 0
    fail_star = 0
    fail = 0
    address_results = [[], [], []]
    future_requests = []

    with FuturesSession() as session:
        for address in addresses:
            time.sleep(0.0004)
            start_address = query_db[query_db["Stop1"] == address]
            end_address = query_db[query_db["Stop2"] == address]

            if len(start_address) <= 0 and len(end_address) <= 0:
                new_request = session.get(
                    geo_api, params={"key": creds["GOOGLE-MAPS-GKEY"], "address": address}, timeout=5
                )
                new_request.address = address
                future_requests.append(new_request)
            else:
                lat = start_address["Lat1"].mode()[0] if len(start_address) > 0 else end_address["Lat2"].mode()[0]
                lon = start_address["Long1"].mode()[0] if len(start_address) > 0 else end_address["Long2"].mode()[0]
                arr_queries.append([lat, lon, address])
                previously_geocoded += 1
                # print(f"{previously_geocoded}/{full}: Stored Previously --> {address}")

        full -= previously_geocoded

        for future in as_completed(future_requests):
            response = future.__getattribute__("_result")
            address = future.address
            if response.status_code == 200:
                # Find the data we want from the response data
                data = response.json()
                results = data["results"]
                if len(results) > 0:
                    # Get coordinates from response data
                    coords = results[0]["geometry"]["location"]

                    arr_queries.append(
                        [
                            coords["lat"],
                            coords["lng"],
                            address,
                            coords["lat"],
                            coords["lng"],
                            address,
                            0,
                            "Geocode-Diagnostics",
                            "SLPS",
                        ]
                    )
                    arr_geocodes.append([coords["lat"], coords["lng"], address])
                    print(f"{counter}/{full}: Success --> {address}")
                    successes += 1
                    address_results[0].append(address)
                else:
                    print(f"{counter}/{full}: No matches --> {address}\n" f"{response.json()}" f"\n")
                    fail_star += 1
                    address_results[1].append(address)
                    arr_geocodes.append([0, 0, address])
            else:
                print(f"{counter}/{full}: Failed Query --> {address}")
                fail += 1
                address_results[2].append(address)
                arr_geocodes.append([0, 0, address])

            counter += 1

    full += previously_geocoded

    print(
        f"Breakdown:\n"
        f"Previously Coded: {previously_geocoded}/{full}\n"
        f"Success: {successes + previously_geocoded}/{full}\n"
        f"No_matches: {fail_star}/{full}\n"
        f"Failed Query: {fail}/{full}"
    )

    if fail_star > 0:
        print(f"\n\nFail*:\n{address_results[1]}")

    if fail > 0:
        print(f"\n\nFail:\n{address_results[2]}")

    try:
        df_queries = pd.concat(
            [
                query_db,
                pd.DataFrame(
                    arr_queries,
                    columns=[
                        "Lat1",
                        "Long1",
                        "Stop1",
                        "Lat2",
                        "Long2",
                        "Stop2",
                        "Distance",
                        "Route",
                        "Navigation Mode",
                    ],
                ),
            ]
        )
        UpdateQueryDB(df_queries)
    except:
        pass

    geocodes = pd.DataFrame(arr_geocodes, columns=["Latitude", "Longitude", "Address"])

    return geocodes


def BatchRoutedDistance(df, address_column1, address_column2, distance_column, route, navigation_mode):
    os.chdir(os.path.dirname(__file__))
    files = glob("/output/*")
    for f in files:
        os.remove(f)

    address_pairs = []

    df_address_group = df.groupby([address_column1, address_column2])
    for group, rows in df_address_group:
        if nan not in group and "" not in group:
            address_pairs.append(group)

    # Make a big list of all of the addresses to be processed.
    address_pairs = list(set(address_pairs))

    return BatchDistanceRequests(
        df, address_pairs, address_column1, address_column2, distance_column, route, navigation_mode
    )


def BatchRoutedDistanceGeo(df, lat_col1, lon_col1, lat_col2, lon_col2, distance_column, route, navigation_mode):
    os.chdir(os.path.dirname(__file__))
    files = glob("/output/*")
    for f in files:
        os.remove(f)

    address_pairs = []

    df_address_group = df.groupby([lat_col1, lon_col1, lat_col2, lon_col2])
    for group, rows in df_address_group:
        address_pairs.append(group)

    # Make a big list of all of the addresses to be processed.
    address_pairs = list(set(address_pairs))

    return BatchDistanceRequestsLats(
        df, address_pairs, lat_col1, lon_col1, lat_col2, lon_col2, distance_column, route, navigation_mode
    )


def BatchGeocode(df, address_columns, parallel=False, save=True):
    os.chdir(os.path.dirname(__file__))
    files = glob("/output/*")
    for f in files:
        os.remove(f)

    missing_columns = False
    # Form a list of addresses for geocoding:
    addresses = []
    for address_column_name in address_columns:

        if address_column_name not in df.columns:
            missing_columns = True
            print(f"Dataframe is missing column {address_column_name}")
        else:
            addresses.extend(df[address_column_name].tolist())

    if missing_columns:
        raise ValueError("Missing Address column(s) in input data")

    # Make a big list of all of the addresses to be processed.
    addresses = set(addresses)

    addresses = [x for x in addresses if x == x and x.lower() != "nan"]

    if parallel:
        geocodes = BatchRequests(addresses)
    else:
        # Create a list to hold results
        geocodes = pd.DataFrame([], columns=["Latitude", "Longitude", "Address"])
        # Go through each address in turn
        for address in addresses:

            # Print status every 100 addresses
            if len(geocodes) % 100 == 0 and len(geocodes) > 0:
                print("\n\nCompleted {} of {} address\n\n".format(len(geocodes), len(addresses)))

            # Every 500 addresses, save progress to file(in case of a failure so you have
            # something!)
            if len(geocodes) % 500 == 0:
                os.chdir(os.path.dirname(__file__))
                geocodes.to_csv("output\\BatchGeocode_{}.csv".format(len(geocodes)))

            if address in [None, "", nan, "nan"]:
                print(f"Ignoring invalid address |{address}|")
                continue

            start_address = query_db[query_db["Stop1"] == address]
            if len(start_address) > 0:
                print(f"Already had geocode for {address} as stop 1")
                geocodes.loc[len(geocodes.index)] = [
                    start_address["Lat1"].mode()[0],
                    start_address["Long1"].mode()[0],
                    address,
                ]
                continue

            end_address = query_db[query_db["Stop2"] == address]
            if len(end_address) > 0:
                print(f"Already had geocode for {address} as stop 2")
                geocodes.loc[len(geocodes.index)] = [
                    end_address["Lat2"].mode()[0],
                    end_address["Long2"].mode()[0],
                    address,
                ]
                continue

            print(f"Querying google for: {address}")
            # Geocode the address with google
            gparams["address"] = address

            # Query the api
            r = requests.get(geo_api, params=gparams)

            # request was successfully returned
            if r.status_code == 200:

                # Find the data we want from the response data
                data = r.json()
                results = data["results"]
                if len(results) > 0:
                    # Get coordinates from response data
                    coords = results[0]["geometry"]["location"]

                    # Add the query to the end of the database, store as a trip to itself
                    query_db.loc[len(query_db.index)] = [
                        coords["lat"],
                        coords["lng"],
                        address,
                        coords["lat"],
                        coords["lng"],
                        address,
                        0,
                        "Geocode",
                        "Geocode",
                    ]
                    os.chdir(os.path.dirname(__file__))

                    query_db.to_csv("QueryDB.csv", index=False)
                    geocodes.loc[len(geocodes.index)] = [coords["lat"], coords["lng"], address]

                else:
                    print(f"Google failed to Geocode '{address}")

    os.chdir(os.path.dirname(__file__))
    # Write the full results to csv using the pandas library.
    if save:
        geocodes.to_csv(f"{os.walk(os.path.dirname(__file__))}/BatchGeocodes.csv", encoding="utf8", index=False)
    return geocodes


def BatchReverseGeocode(df, lat_col, long_col, new_address_col):
    os.chdir(os.path.dirname(__file__))

    df["LatLongs"] = [f"{str(x)}, {str(y)}" if x == x and y == y else "nan" for x, y in zip(df[lat_col], df[long_col])]

    lat_longs = set(df["LatLongs"].unique())

    lat_longs = [x for x in lat_longs if x == x and x.lower() != "nan"]

    full = len(lat_longs)

    previously_geocoded = 0
    successes = 0
    fail_star = 0
    fail = 0

    # Create a list to hold results
    addresses = pd.DataFrame([], columns=["Latitude", "Longitude", "Address"])
    # Go through each address in turn
    with FuturesSession() as session:
        future_requests = {}

        for coord in lat_longs:
            lat = float(coord.split(",")[0])
            lng = float(coord.split(" ")[1])

            if coord in [None, "", nan, "nan"]:
                print(f"Ignoring invalid lat-long |{coord}|")
                continue

            address_lookup = query_db[
                (query_db["Lat1"] == lat) & (query_db["Long1"] == lng) & (query_db["Route"] == "Geocode")
            ]
            if len(address_lookup) > 0:
                pair_mask = (df[lat_col] == lat) & (df[long_col] == lng)
                df.loc[pair_mask, new_address_col] = address_lookup["Stop1"].max()
                previously_geocoded += 1
                continue
            else:
                request_params = gparams
                request_params["latlng"] = coord
                time.sleep(0.0004)
                future = session.get(geo_api, params=deepcopy(request_params), timeout=5)
                future_requests[future] = deepcopy(coord)

        for future in as_completed(future_requests):
            response = future.__getattribute__("_result")
            coord = future_requests[future]
            try:
                if response.status_code == 200:

                    # Find the data we want from the response data
                    data = response.json()
                    results = data["results"]
                    if len(results) > 0:
                        # Get coordinates from response data
                        address = results[0]["formatted_address"]
                        lat = float(coord.split(",")[0])
                        lng = float(coord.split(" ")[1])
                        # Add the query to the end of the database, store as a trip to itself
                        query_db.loc[len(query_db.index)] = [
                            lat,
                            lng,
                            address,
                            lat,
                            lng,
                            address,
                            0,
                            "Geocode",
                            "Geocode",
                        ]

                        pair_mask = (df[lat_col] == lat) & (df[long_col] == lng)
                        df.loc[pair_mask, new_address_col] = address
                        os.chdir(os.path.dirname(__file__))

                        query_db.to_csv("QueryDB.csv", index=False)
                        addresses.loc[len(addresses.index)] = [lat, lng, address]
                        successes += 1

                    else:
                        # print(f"Google failed to ReverseGeocode '{coord}")
                        fail_star += 1
                else:
                    fail += 1
            except:
                fail += 1
                continue
    full += previously_geocoded

    print(
        f"Breakdown:\n"
        f"Previously Coded: {previously_geocoded}/{full}\n"
        f"Success: {successes + previously_geocoded}/{full}\n"
        f"No_matches: {fail_star}/{full}\n"
        f"Failed Queryyy: {fail}/{full}"
    )

    os.chdir(os.path.dirname(__file__))

    return df


def BatchGeocodeLookup(df, address_column_to_lat_long_dict):

    missing_columns = False
    # Form a list of addresses for geocoding:
    addresses = []
    for address_column_name in address_column_to_lat_long_dict:

        if address_column_name not in df.columns:
            missing_columns = True
            print(f"Dataframe is missing column {address_column_name}")

    if missing_columns:
        raise ValueError("Missing Address column(s) in input data")

    # Make a big list of all of the addresses to be processed.
    addresses = set(addresses)

    for address in addresses:
        for address_column_name in address_column_to_lat_long_dict:

            start_address = query_db[query_db["Stop1"] == address]
            end_address = query_db[query_db["Stop2"] == address]

            if len(start_address) <= 0 and len(end_address) <= 0:
                print(f"No lat_long infor was found for {address}")
                continue

            lat = start_address["Lat1"].mode()[0] if len(start_address) > 0 else end_address["Lat2"].mode()[0]
            lon = start_address["Long1"].mode()[0] if len(start_address) > 0 else end_address["Long2"].mode()[0]

            # df[address_column_to_lat_long_dict[address_column_name][0]].loc[df[address_column_name] == address] = lat
            # df[address_column_to_lat_long_dict[address_column_name][1]].loc[df[address_column_name] == address] = lon

            df.loc[df[address_column_name] == address, address_column_to_lat_long_dict[address_column_name][0]] = lat
            df.loc[df[address_column_name] == address, address_column_to_lat_long_dict[address_column_name][1]] = lon

    return df
