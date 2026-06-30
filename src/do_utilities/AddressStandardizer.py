import os
from string import capwords

from usaddress import tag

from do_utilities.Constants import getStandards

standard = getStandards()


# Function for applying address standards such as North Street --> N St
def standardization(text):
    
    # Convert text to lowercase to match entries
    final = text.lower().replace(".", "")

    # Look for a standardization entry with this text
    df_entry = standard.loc[standard["Text"] == final]

    # If an entry was found, use the corresponding abbreviation
    if not df_entry.empty:
        df_index = df_entry.index.tolist()[0]
        final = df_entry.at[df_index, "Abbreviation"].capitalize()

    # If an entry wasn't found, check if they are already using the abbreviation
    else:
        df_entry = standard.loc[standard["Abbreviation"] == final]

        # The text is already using the abbreviation, so just keep using it
        if not df_entry.empty:
            df_index = df_entry.index.tolist()[0]
            final = df_entry.at[df_index, "Abbreviation"].capitalize()

    # Cardinal directions need to be fully capitalized instead of just the first letter like all
    # others
    final = final.upper() if final in ["Ne", "Se", "Nw", "Sw"] else final.title()
    return final


# Create a street based on the given breakdown and type
# Switch 1 = Standard address
# Switch 2 = Intersection
# Switch 3 = Ambiguous intersection
# Switch 4 = other
def createStreet(data, switch):
    # Street string will be constructed from modified tokens of the original data
    street = ""
    try:
        # Street address is for a specific location, assemble based on available data
        if switch == 1:
            if "StreetNamePreDirectional" in data:
                street = standardization(data["StreetNamePreDirectional"]) + " "
            if "StreetNamePreModifer" in data:
                street = standardization(data["StreetNamePreModifer"]) + " "
            if "StreetNamePreType" in data:
                street = standardization(data["StreetNamePreType"]) + " "
            street += capwords(data["StreetName"])
            if "StreetNamePostType" in data:
                street = street + " " + standardization(data["StreetNamePostType"])
            if "StreetNamePostModifer" in data:
                street = standardization(data["StreetNamePostModifer"]) + " "
            if "StreetNamePostDirectional" in data:
                street = street + " " + standardization(data["StreetNamePostDirectional"])

        elif switch == 2:
            for cur_item in data:
                if cur_item.__contains__("Second"):
                    if cur_item.__contains__("StreetName"):
                        street += data[cur_item] + " "
                    else:
                        street += standardization(data[cur_item]) + " "
            street = street[:-1]

        elif switch == 3:
            keys_values = data.items()

            # Recreate the original string and standardize text when possible
            for key, value in keys_values:

                # process the tokens we know will standardize well, else just give the expected
                # capitalization
                if key in [
                    "StreetNamePreType",
                    "StreetNamePostType",
                    "SecondStreetNamePreType",
                    "SecondStreetNamePostType",
                    "StreetNamePreDirectional",
                    "StreetNamePostDirectional",
                    "SecondStreetNamePreDirectional",
                    "SecondStreetNamePostDirectional",
                ]:
                    value = standardization(value)
                elif key in ["PlaceName", "StateName", "ZipCode"]:
                    continue
                else:
                    value = capwords(value)

                # Build the final street name one token at a time
                street = street + value + " "

            street = street.strip()

        elif switch == 4:
            # Address is an oddity, try to standardize where possible
            for a, b in data:
                if b in [
                    "StreetNamePreType",
                    "StreetNamePostType",
                    "SecondStreetNamePreType",
                    "SecondStreetNamePostType",
                    "StreetNamePreDirectional",
                    "StreetNamePostDirectional",
                    "SecondStreetNamePreDirectional",
                    "SecondStreetNamePostDirectional",
                ]:
                    a = standardization(a)
                else:
                    a = capwords(a)
                street = street + a + " "
            street = street.strip()

        else:
            return
    except Exception:
        return street
    return street


# Create the address based on the given data and type
def processAddress(old_address, switch, street_only):

    # Process both of the intersecting streets and then combine them together
    if switch == "Intersection":
        street1 = createStreet(old_address, 1)
        street2 = createStreet(old_address, 2)
        new_address = street1 + " & " + street2

    # Process the given street address
    elif switch == "Street Address":
        street = createStreet(old_address, 1)
        new_address = old_address["AddressNumber"] + " " + street

    # Process the poorly processed intersection
    elif switch == "Ambiguous":
        new_address = createStreet(old_address, 3)

    # Attempt to process the odd address
    elif switch == "Other":
        new_address = createStreet(old_address, 4)

    elif switch == "PO Box":
        new_address = ""
        for entry in old_address:
            new_address += old_address[entry] + " "
        return new_address

    # Address resolved to unknown type, print the type and kill the program
    else:
        print("An address resolved to ", switch)
        quit()

    # If we don't want to just do a street address, add the other fields
    if not street_only:
        # If the city was provided, add it to the end of the address
        if "PlaceName" in old_address:

            if "St" in old_address["PlaceName"]:
                old_address["PlaceName"] = old_address["PlaceName"].replace("St", "Saint").replace(".", "")

            if ", " in old_address["PlaceName"]:
                new_address += " " + old_address["PlaceName"]
            else:
                new_address += ", " + old_address["PlaceName"]
        # If the state was provided, add it to the end of the address
        if "StateName" in old_address:
            new_address += ", " + (
                old_address["StateName"].upper() if len(old_address["StateName"]) == 2 else old_address["StateName"]
            )
        # If the zip was provided, add it to the end of the address
        if "ZipCode" in old_address:
            new_address += " " + old_address["ZipCode"]

    return new_address


def getAddressComponent(address_string, component):
    if address_string != address_string or address_string is None or address_string == "":
        return ""

    # If the given address appears to be an intersection
    if "&" in address_string:
        temp = address_string.split("&")
        while len(temp) > 2:
            # If given address is the intersection of more than two streets, remove all but 2
            temp.pop(len(temp) - 1)
        address_string = "&".join(temp)

    # Run the address parser and processor on the address
    try:
        # 3rd party library converts given address into an ordered dict of expected address
        # elements
        output = tag(address_string)
        try:
            return output[0][component]
        except Exception:
            print(f"Failed to find component '{component}' for address '{address_string}'")
            return ""

    except Exception:
        if component == "PlaceName":
            return address_string.split(", ")[1]
        elif component == "ZipCode":
            test = address_string.split(", ")
            if len(test) > 2:
                if "USA" in test[-1].upper():
                    test = test[:-1]
                if len(test[-1]) != 5:
                    return test[-1][-5:]

        # Library couldn't understand the address format, just return the address properly
        # capitalized
        print(f"Failed to find component '{component}' for address '{address_string}'")
        return ""


# Convert the given address string to an orderedDict for analysis and further work
def convertAddress(address_string, street_only=False):
    global standard
    
    if standard.empty:
        standard = getStandards()
        if standard.empty:
            print(f"Error: Common has not been initialized, can't standardize addresses")
            return ""
        
    # NAN check
    if address_string != address_string or address_string is None:
        return ""

    address_string = address_string.replace("  ", " ")

    address_string = address_string.title()

    # Typically a "USA" is seen when the last part of the address is repeated, so remove
    # everything prior to it (if not duplicated, it just removes the
    # country code)
    if ",USA" in address_string.upper() or " USA" in address_string.upper():
        temp = address_string.split(",")
        country_index = 0
        for cur in temp:
            if ",USA" in cur.upper() or " USA" in cur.upper():
                break
            country_index += 1
        address_string = ",".join(temp[:country_index])

    # Run the address parser and processor on the address
    try:
        # 3rd party library converts given address into an ordered dict of expected address
        # elements
        output = tag(address_string)
        # "Forece the '&' char to mean intersection
        if "&" in address_string and output[1] != "Intersection":
            raise Exception
        return processAddress(output[0], output[1], street_only)
    except Exception:
        # Library couldn't understand the address format, just return the address properly
        # capitalized
        address_string = address_string.title()
        if street_only:
            address_string = address_string.split(",")[0]
        return address_string
