import json
import os
from math import atan2, cos, pi, sin, sqrt

import googlemaps
import pandas as pd
import requests
from googlemaps.convert import decode_polyline
from googlemaps.directions import directions
from numpy import nan

from Constants import creds
import time

# Move to the current folder to read and write locally
os.chdir(os.path.dirname(__file__))

# Google Geocoder API Parameters
geo_api = "https://maps.googleapis.com/maps/api/geocode/json"
gparams = {"key": creds["GOOGLE-MAPS-GKEY"]}

gmaps = googlemaps.Client(key=creds["GOOGLE-MAPS-GKEY"])

# Route finding requires calling a slightly different endpoint
route_api = "https://maps.googleapis.com/maps/api/directions/json"

# Read the master query log into memory, used to reduce overall API queries
try:
    query_db = pd.read_csv("QueryDB.csv", low_memory=False)
    query_db.drop_duplicates(inplace=True)
    query_db.to_csv("QueryDB.csv", index=False)
except Exception:
    # If it doesn't exist, make one
    query_db = pd.DataFrame(
        [], columns=["Lat1", "Long1", "Stop1", "Lat2", "Long2", "Stop2", "Distance", "Route", "Navigation Mode"]
    )

# Read the master query log into memory, used to reduce overall API queries
try:
    route_query_db = pd.read_csv("RouteQueryDB.csv")
except Exception:
    # If it doesn't exist, make one
    route_query_db = pd.DataFrame([], columns=["Lat1", "Long1", "Lat2", "Long2", "Stops"])

# Read the master query log into memory, used to reduce overall API queries
try:
    polyLineQueryDB = pd.read_csv("PolyLineQueryDB.csv")
except:
    # If it doesn't exist, make one
    polyLineQueryDB = pd.DataFrame([], columns=["Route", "Stops", "PolyLine"])


def CalculateLatLongDistanceWithStops(stop1, stop2):
    if nan in [stop1, stop2]:
        return nan
    if stop1 == stop2:
        return 0

    latlong1 = Geocode(stop1, save=True)
    latlong2 = Geocode(stop2, save=True)
    return CalculateLatLongDistance(latlong1[0], latlong1[1], latlong2[0], latlong2[1])


# Calculates an approximate distance between two points on a sphere using the haversine formula
# to calculate the
# great-circle distance between two points (https://www.movable-type.co.uk/scripts/lat_long.html)
# Haversine formula:
# a = sin²(Δφ/2) + cos φ1 ⋅ cos φ2 ⋅ sin²(Δλ/2) c = 2 ⋅ atan2( √a, √(1−a) ) d = R ⋅ c
# where φ (phi) is latitude, λ (lambda) is longitude, R is earth’s radius (mean radius = 3958.8mi)
# note that angles need to be in radians to pass to trig functions!
def CalculateLatLongDistance(latitude1, longitude1, latitude2, longitude2):
    if nan in [latitude1, longitude1, latitude2, longitude2]:
        return nan

    # Make sure lat longs are all floats
    latitude1 = float(latitude1)
    latitude2 = float(latitude2)
    longitude1 = float(longitude1)
    longitude2 = float(longitude2)

    if (latitude1 == 0 and longitude1 == 0) or (latitude2 == 0 and longitude2 == 0):
        print("Error: a null lat/long was found")

    phi1 = latitude1 * pi / 180
    phi2 = latitude2 * pi / 180
    delta_phi = (latitude2 - latitude1) * pi / 180
    delta_lambda = (longitude2 - longitude1) * pi / 180

    a = sin(delta_phi / 2) * sin(delta_phi / 2) + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) * sin(delta_lambda / 2)

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    final = 3958.8 * c

    return final


def GetDf():
    return query_db


# Get all of the routed coordinates between two points
def GetRouteBetweenPoints(lat1, long1, lat2, long2):
    # Check if this distance query exists in the database already
    test = route_query_db[
        (route_query_db["Lat1"] == lat1)
        & (route_query_db["Long1"] == long1)
        & (route_query_db["Lat2"] == lat2)
        & (route_query_db["Long2"] == long2)
    ]

    if len(test) > 0:
        # Entry was found, return distance
        return test["Stops"].mode()[0]

    # Apply parameters for google api query, car travel in miles
    gparams["mode"] = "driving"
    gparams["units"] = "imperial"

    # lat longs must be entered in a specific string format
    gparams["origin"] = f"{str(lat1)}, {str(long1)}"
    gparams["destination"] = f"{str(lat2)}, {str(long2)}"

    # Query the api
    r = requests.get(route_api, params=gparams)

    # request was successfully returned
    if r.status_code == 200:
        # Find the data we want from the response data
        data = r.json()

        time.sleep(0.01)

        try:
            steps = data["routes"][0]["legs"][0]["steps"]
        except Exception:
            print(f"Failed to find route between {lat1}, {long1} and {lat2}, {long2}")
            return [(long1, lat1)]

        stop_list = [(long1, lat1)]

        stop_list.extend((step["end_location"]["lng"], step["end_location"]["lat"]) for step in steps)
        # Add the query to the end of the database
        route_query_db.loc[len(route_query_db.index)] = [lat1, long1, lat2, long2, stop_list]

        # save the updated query_db, saves after every query to avoid losing work if the API times
        # out during a batch request
        os.chdir(os.path.dirname(__file__))
        route_query_db.to_csv("RouteQueryDB.csv", index=False)

        return stop_list

    print("Failed to query API")


# The master distance finding functions that takes lat longs and addresses as parameters
def GetRoutedDistance(lat1, long1, lat2, long2, stop1, stop2, route, mode="driving", save=True):
    # Set the default distance between points as 0
    distance = 0

    if nan in [lat1, long1, lat2, long2, stop1, stop2]:
        return nan

    # If the same locations were provided, the distance is 0
    if (lat1 == lat2 and long1 == long2) or stop1 == stop2:
        return distance

    # Calculate the haversine difference between the two points to check against later if needed
    check = CalculateLatLongDistance(lat1, long1, lat2, long2)
    try:
        # Try to get the distance between the two lat longs
        distance = GetRoutedDistanceFromLatLong(lat1, long1, lat2, long2, route, mode, save)

    except Exception:
        try:
            # Using the lat/longs didn't work, try using the addresses
            distance = GetRoutedDistanceFromAddresses(stop1, stop2, route, mode, save)
        except Exception:
            # Neither options worked, check if the haversine formula found that the points are
            # actually apart from one another
            if check > 0.1:
                print("Failed to find distance using stops or lat/long")
                print(f"{lat1} | {long1} |  {lat2} | {long2} | {stop1} | {stop2} | {route} | {mode}")
                print(f"Check = {check}\n")
                return nan
            else:
                # The locations are functionally equivalent, so the distance apart can be
                # considered 0
                distance = 0

    if distance != distance:
        print(f"Distance between {stop1} and {stop2} is {distance}")

    # If the calculated distance seems high, print it out for review
    if 75 > distance > 25 and abs(distance - check) > 10:
        print(
            f"The distance between {stop1} and {stop2} is {distance}, which seems high, the direct "
            f"distance is {check}"
        )

    # If the distance is large, print it out and terminate as it's likely an incorrect address was
    # provided
    elif distance > 75:
        print(
            f"The distance between {stop1} and {stop2} is {distance}, which must be wrong, "
            f"the direct distance is {check}"
        )
        quit(1)
    return distance


def GetVehicleRoute(stops, route_name):
    all_stops = str(stops)

    # Check if this query exists in the database already
    query_check = polyLineQueryDB[(polyLineQueryDB["Route"] == route_name) & (polyLineQueryDB["Stops"] == all_stops)]

    if len(query_check) > 0:
        # Entry was found, return polyLine as an array converted from its stored string
        return json.loads(query_check["PolyLine"].mode()[0])

    print(f"Querying Google for {route_name}")
    origin = str(stops[0])
    destination = str(stops[-1])

    stops = stops[1:-1]

    data = directions(gmaps, origin, destination, mode="driving", waypoints=stops, units="imperial")
    try:
        polyline = data[0]["overview_polyline"]["points"]
        steps = decode_polyline(polyline)

        steps = [list(x.values()) for x in steps]

        for cur_step in steps:
            if float(cur_step[0]) == 0 and float(cur_step[1]) == 0:
                print(f"Couldn't process a stop for {route_name}")
                return []

        # save the updated queryDB, saves after every query to avoid losing work if the API times
        # out during a batch request
        os.chdir(os.path.dirname(__file__))
        polyLineQueryDB.loc[len(polyLineQueryDB.index)] = [route_name, all_stops, str(steps)]
        polyLineQueryDB.to_csv("PolyLineQueryDB.csv", index=False)
        return steps
    except:
        print(f"Failed to find poly line for {route_name}")
        raise Exception


def GetMdeRoutedDistanceFromLatLong(lat1, long1, lat2, long2):
    # Get haversine distance between points
    check = CalculateLatLongDistance(lat1, long1, lat2, long2)

    # Check if this distance query exists in the database already
    test = query_db[
        (query_db["Lat1"] == lat1)
        & (query_db["Long1"] == long1)
        & (query_db["Lat2"] == lat2)
        & (query_db["Long2"] == long2)
    ]

    if len(test) > 0:
        # Entry was found, return distance
        return test["Distance"].mode()[0], True

    # Apply parameters for google api query, car travel in miles
    gparams["mode"] = "driving"
    gparams["units"] = "imperial"

    # lat longs must be entered in a specific string format
    gparams["origin"] = f"{str(lat1)}, {str(long1)}"
    gparams["destination"] = f"{str(lat2)}, {str(long2)}"

    # Query the api
    r = requests.get(route_api, params=gparams)

    # request was successfully returned
    if r.status_code == 200:

        # Slow down api calls slightly to avoid hitting rate limit of 50/s
        time.sleep(0.01)

        # Find the data we want from the response data
        data = r.json()
        results = data["routes"][0]["legs"]

        # Check if a route was found and use the first one
        if len(results) > 0:

            # Get distance and convert it from a string
            distance = results[0]["distance"]["text"]

            # replace text which will prevent a conversion to a float
            distance = distance.replace(",", "").replace(" mi", "")

            # Convert ft to miles
            if "ft" in str(distance):
                distance = float(distance.replace(" ft", "")) / 5280.000
            # Use the meters instead of miles for a more precise result
            else:
                distance = round(results[0]["distance"]["value"] / 1609.344, 4)

            # pull the address names from the results
            stop1 = results[0]["start_address"]
            stop2 = results[0]["end_address"]

            # If the calculated distance seems high, print it out for review
            if 75 > distance > 25 and abs(distance - check) > 10:
                print(
                    f"The distance between {stop1} and {stop2} is {distance}, which seems high, "
                    f"the direct distance is {check}"
                )

            # If the distance is large, print it out and terminate as it's likely an incorrect
            # address was provided
            elif distance > 75:
                print(
                    f"The distance between {stop1} and {stop2} is {distance}, which must be wrong, "
                    f"the direct distance is {check}"
                )
                quit(1)
        else:
            print("Google failed to find a route between the points")
            quit(1)

    else:
        print("Failed to query Google")
        quit(1)
    return distance, False


# Get the distance between two lat/longs
def GetRoutedDistanceFromLatLong(lat1, long1, lat2, long2, route, mode="driving", save=True):
    # Get haversine distance between points
    check = CalculateLatLongDistance(lat1, long1, lat2, long2)

    # Check if this distance query exists in the database already
    test = query_db[
        (query_db["Lat1"] == lat1)
        & (query_db["Long1"] == long1)
        & (query_db["Lat2"] == lat2)
        & (query_db["Long2"] == long2)
    ]

    if len(test) > 0:
        # Entry was found, return distance
        return test["Distance"].mode()[0]

    # Apply parameters for google api query, car travel in miles
    gparams["mode"] = mode
    gparams["units"] = "imperial"

    # lat longs must be entered in a specific string format
    gparams["origin"] = f"{str(lat1)}, {str(long1)}"
    gparams["destination"] = f"{str(lat2)}, {str(long2)}"

    # Query the api
    r = requests.get(route_api, params=gparams)

    # request was successfully returned
    if r.status_code == 200:

        # Probably running in parallel, limit API calls per second, max is 50/sec
        if not save:
            time.sleep(0.1)

        # Find the data we want from the response data
        data = r.json()
        results = data["routes"][0]["legs"]

        # Check if a route was found and use the first one
        if len(results) > 0:

            # Get distance and convert it from a string
            distance = results[0]["distance"]["text"]

            # replace text which will prevent a conversion to a float
            distance = distance.replace(",", "").replace(" mi", "")

            # Convert ft to miles
            if "ft" in str(distance):
                distance = float(distance.replace(" ft", "")) / 5280.000
            # Use the meters instead of miles for a more precise result
            else:
                distance = round(results[0]["distance"]["value"] / 1609.344, 4)

            # pull the address names from the results
            try:
                stop1 = results[0]["start_address"]
            except:
                stop1 = f"{lat1}, {long1}"
            try:
                stop2 = results[0]["end_address"]
            except:
                stop2 = f"{lat2}, {long2}"

            # If the calculated distance seems high, print it out for review
            if 75 > distance > 25 and abs(distance - check) > 10:
                print(
                    f"The distance between {stop1} and {stop2} is {distance}, which seems high, "
                    f"the direct distance is {check}"
                )

            # If the distance is large, print it out and terminate as it's likely an incorrect
            # address was provided
            elif distance > 75:
                print(
                    f"The distance between {stop1} and {stop2} is {distance}, which must be wrong, "
                    f"the direct distance is {check}"
                )
                # quit(1)

            if save:
                # Add the query to the end of the database
                query_db.loc[len(query_db.index)] = [lat1, long1, stop1, lat2, long2, stop2, distance, route, mode]

                # save the updated query_db, saves after every query to avoid losing work if the
                # API times out during a batch request
                os.chdir(os.path.dirname(__file__))
                query_db.to_csv("QueryDB.csv", index=False)
        else:
            print("Google failed to find a route between the points")
            quit(1)

    else:
        print("Failed to query Google")
        quit(1)
    return distance


# Get the distance between two addresses
def GetRoutedDistanceFromAddresses(stop1, stop2, route, navigation_mode="driving", save=True):
    global query_db
    # Check if this query exists in the database already
    test = query_db[
        (query_db["Stop1"] == stop1) & (query_db["Stop2"] == stop2) & (query_db["Navigation Mode"] == navigation_mode)
    ]

    if len(test) > 0:
        # Entry was found, return distance
        return test["Distance"].mode()[0]

    print(f"Couldn't find an entry for: {stop1} | {stop2} | {route} | {navigation_mode}")

    # Apply parameters for google api query
    gparams["mode"] = navigation_mode
    gparams["units"] = "imperial"
    gparams["origin"] = stop1
    gparams["destination"] = stop2

    # Query the api
    r = requests.get(route_api, params=gparams)

    # request was successfully returned
    if r.status_code == 200:

        # Probably running in parallel, limit API calls per second, max is 50/sec
        if not save:
            time.sleep(0.1)

        # Find the data we want from the response data
        data = r.json()
        try:
            results = data["routes"][0]["legs"]
        except Exception:
            results = []

        # Check if a route was found and use the first one
        if len(results) > 0:

            # Get distance and convert it from a string
            distance = results[0]["distance"]["text"]

            # Remove any text which will prevent the conversion to float
            distance = distance.replace(",", "").replace(" mi", "")

            if "ft" in distance:
                distance = float(distance.replace(" ft", "")) / 5280.000
            # Use the meters instead of miles for a more precise result
            else:
                distance = round(results[0]["distance"]["value"] / 1609.344, 4)

            # pull the lat/longs for the stops from the results
            lat1 = results[0]["start_location"]["lat"]
            long1 = results[0]["start_location"]["lng"]
            lat2 = results[0]["end_location"]["lat"]
            long2 = results[0]["end_location"]["lng"]

            if float(lat1) == 0 and float(long1) == 0:
                print(f"Failed to process the geocodes for {stop1}")
                save = False

            if float(lat2) == 0 and float(long2) == 0:
                print(f"Failed to process the geocodes for {stop2}")
                save = False

            # Get haversine distance between points
            check = CalculateLatLongDistance(lat1, long1, lat2, long2)

            # If the calculated distance seems high, print it out for review
            if 75 > distance > 25 and abs(distance - check) > 10:
                print(
                    f"The distance between {stop1} and {stop2} is {distance}, which seems high, "
                    f"the direct distance is {check}"
                )

            # If the distance is large, print it out and terminate as it's likely an incorrect
            # address was provided
            elif distance > 75:
                print(
                    f"The distance between {stop1} and {stop2} is {distance}, which must be wrong, "
                    f"the direct distance is {check}"
                )
            # quit(1)

            if distance > 2 and navigation_mode == "walking":
                print(
                    f"The walk distance between {stop1} and {stop2} is {distance}, which is sus, "
                    f"and the check was {check}"
                )

            if save:
                query_db.loc[len(query_db.index)] = [
                    lat1,
                    long1,
                    stop1,
                    lat2,
                    long2,
                    stop2,
                    distance,
                    route,
                    navigation_mode,
                ]
                # save the updated query_db
                os.chdir(os.path.dirname(__file__))
                query_db.to_csv("QueryDB.csv", index=False)
        else:
            print(f"Google failed to find a route between {stop1} and {stop2}")
            quit(1)

    else:
        print("Failed to query Google")
        quit(1)
    return distance


# Call the google api to convert an address to lat/longs
def Geocode(address, save=True):
    global query_db
    if address in [None, "", nan, "nan"]:
        return nan, nan

    address = address.replace(", USA", "")
    # Check if this exists in the database already, and return the lat/longs if so
    start_address = query_db[(query_db["Stop1"] == address) & (query_db["Route"] == "Geocode")]
    if len(start_address) > 0:
        return start_address["Lat1"].mode()[0], start_address["Long1"].mode()[0]

    print(f"Geocoding address: {address}")

    # Apply parameter for google api query
    gparams["address"] = address

    # Query the api
    r = requests.get(geo_api, params=gparams)

    # request was successfully returned
    if r.status_code == 200:

        # Probably running in parallel, limit API calls per second, max is 50/sec
        if not save:
            time.sleep(0.1)

        # Find the data we want from the response data
        data = r.json()
        results = data["results"]
        if len(results) > 0:
            # Get coordinates from response data
            coords = results[0]["geometry"]["location"]
            returned_address = results[0]["formatted_address"]
            lat_long = (coords["lat"], coords["lng"])

            if coords["lat"] == 0 and coords["lng"] == 0:
                print(f"Failed to generate a real geocode for {address}")
                quit(1)

            if save:
                # Add the query to the end of the database, store as a trip to itself
                query_db.loc[len(query_db.index)] = [
                    coords["lat"],
                    coords["lng"],
                    address,
                    coords["lat"],
                    coords["lng"],
                    returned_address,
                    0,
                    "Geocode",
                    "Geocode",
                ]

                # save the updated query_db
                os.chdir(os.path.dirname(__file__))
                query_db.to_csv("QueryDB.csv", index=False)
        else:
            print(f"Google failed to Geocode '{address}")
            quit(1)

    else:
        print(f"Failed to geocode '{address}' via the Google Maps API")
        quit(1)
    return lat_long


def EquivalentAddresses(add1, add2):

    if "4848 Flag" in add1 and "4848 Flag" in add2:
        print()

    # Check if this exists in the database already, and return the lat/longs if so
    start_address = query_db[(query_db["Stop1"] == add1) & (query_db["Route"] == "Geocode")]
    if start_address.empty:
        Geocode(add1)
        start_address = query_db[(query_db["Stop1"] == add1) & (query_db["Route"] == "Geocode")]
    lat1 = start_address["Lat1"].mode()[0]
    lon1 = start_address["Long1"].mode()[0]

    start_address = query_db[(query_db["Stop1"] == add2) & (query_db["Route"] == "Geocode")]
    if start_address.empty:
        Geocode(add2)
        start_address = query_db[(query_db["Stop1"] == add2) & (query_db["Route"] == "Geocode")]
    lat2 = start_address["Lat1"].mode()[0]
    lon2 = start_address["Long1"].mode()[0]

    return CalculateLatLongDistance(lat1, lon1, lat2, lon2) < 0.2


# Call the google api to convert lat longs to an address
def ReverseGeocode(lat, long, save=True):
    # Check if this exists in the database already, and return the lat/longs if so
    start_address = query_db[(query_db["Lat1"] == lat) & (query_db["Long1"] == long) & (query_db["Route"] == "Geocode")]
    if len(start_address) > 0:
        return start_address["Stop2"].mode()[0]

    end_address = query_db[(query_db["Lat2"] == lat) & (query_db["Long2"] == long) & (query_db["Route"] == "Geocode")]
    if len(end_address) > 0:
        return end_address["Stop2"].mode()[0]

    # Google needs the lat and long in a specific format
    lat_long = f"{str(lat)}, {str(long)}"

    # Apply parameter for google api query
    gparams["latlng"] = lat_long

    # Query the api
    r = requests.get(geo_api, params=gparams)

    # request was successfully returned
    if r.status_code == 200:

        # Probably running in parallel, limit API calls per second, max is 50/sec
        if not save:
            time.sleep(0.1)

        # Find the data we want from the response data
        data = r.json()
        results = data["results"]

        if len(results) > 0:

            # Get address from response data
            address = results[0]["formatted_address"]

            if save:
                # Add the query to the end of the database as a trip to itself
                query_db.loc[len(query_db.index)] = [
                    lat,
                    long,
                    address,
                    lat,
                    long,
                    address,
                    0,
                    "ReverseGeocode",
                    "ReverseGeocode",
                ]

                # save the updated query_db
                os.chdir(os.path.dirname(__file__))
                query_db.to_csv("QueryDB.csv", index=False)
        else:
            print(f"Google failed to reverse ({lat}, {long}) into a physical address")
            return ""

    else:
        print(f"Did not receive a succesful request to reverse geocode ({lat}, {long})")
        return ""
    return address


def UpdateQueryDB(queries=pd.DataFrame(), save=True):
    global query_db
    try:
        if not queries.empty:
            query_db = pd.concat([query_db, queries], ignore_index=True)
        query_db = query_db.drop_duplicates()
        if not query_db.empty and save:
            os.chdir(os.path.dirname(__file__))
            query_db.to_csv("QueryDB.csv", index=False)
    except Exception:
        pass


def main():
    # pass
    print(
        "Routed stop addresses = ",
        GetRoutedDistanceFromAddresses(
            "N Bryant Ave & N 41st Ave, Minneapolis, MN 55412", "43rd Ave N & Beard Ave N, Robbinsdale, MN 55422", "MDE"
        ),
    )
    print(
        "Crow stop addresses = ",
        CalculateLatLongDistanceWithStops(
            "N Bryant Ave & N 41st Ave, Minneapolis, MN 55412", "43rd Ave N & Beard Ave N, Robbinsdale, MN 55422"
        ),
    )

    print(
        "Routed lat/longs = ",
        GetRoutedDistanceFromLatLong(45.0295, -93.2906, 45.0334, -93.3238, "MDE"),
    )
    print("Crow lat/longs = ", CalculateLatLongDistance(45.0295, -93.2906, 45.0334, -93.3238))


if __name__ == "__main__":
    # main()
    print(Geocode("90002 Duncan U Fletcher High Ac, Jacksonville", False))
    print(Geocode("806 4Th Ave S, Jacksonville", False))
    print(Geocode("287 Stonemason Way, Jacksonville", False))
