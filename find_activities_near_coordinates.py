#!/usr/bin/env python3
"""
Find activity bounds containing a coordinate, then fill results by proximity.

Reads the JSON array produced by activity_bounds.py from UTF-8 stdin, or from
a file supplied with -f/--file. Containing rectangles are preferred; if fewer
than --count contain the coordinate, remaining results are the nearest rectangle
centers.

Examples:
    python find_activities_near_coordinates.py --lat 60.17 --lon 24.94 --count 5 < list.txt
    python find_activities_near_coordinates.py --lat 60.17 --lon 24.94 -c 5 -f list.txt
    python find_activities_near_coordinates.py --gmap 'https://maps.app.goo.gl/...' -c 5 -f list.txt
"""

import argparse
import json
import logging
import math
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen


LOG_FILE = Path(__file__).with_name(f"{Path(__file__).stem}.log")
EARTH_RADIUS_METERS = 6_371_000


def parse_args():
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lat", type=latitude_argument, help="target latitude, from -90 to 90")
    parser.add_argument("--lon", type=longitude_argument, help="target longitude, from -180 to 180")
    parser.add_argument("-g", "--gmap", help="Google Maps link to the target location (instead of --lat/--lon)")
    parser.add_argument("-c", "--count", type=positive_integer, required=True, help="number of activity names to return")
    parser.add_argument("-f", "--file", type=Path, help="bounds JSON file (default: read UTF-8 JSON from stdin)")
    parser.add_argument("-d", action="store_true", help="write DEBUG logs to this script's log file")
    args = parser.parse_args()

    if args.gmap and (args.lat is not None or args.lon is not None):
        parser.error("--gmap cannot be combined with --lat or --lon")
    if args.gmap is None and (args.lat is None or args.lon is None):
        parser.error("provide either --gmap or both --lat and --lon")
    return args


def latitude_argument(value):
    try:
        coordinate = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("latitude must be a number") from error
    if not math.isfinite(coordinate) or not -90 <= coordinate <= 90:
        raise argparse.ArgumentTypeError("latitude must be between -90 and 90")
    return coordinate


def longitude_argument(value):
    try:
        coordinate = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("longitude must be a number") from error
    if not math.isfinite(coordinate) or not -180 <= coordinate <= 180:
        raise argparse.ArgumentTypeError("longitude must be between -180 and 180")
    return coordinate


def positive_integer(value):
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("count must be a positive integer") from error
    if count < 1:
        raise argparse.ArgumentTypeError("count must be a positive integer")
    return count


def map_coordinates(url):
    """Extract latitude and longitude from a resolved Google Maps URL."""
    decoded_url = unquote(url)
    patterns = (
        r"@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)",
        r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, decoded_url)
        if match:
            latitude, longitude = float(match.group(1)), float(match.group(2))
            break
    else:
        query = parse_qs(urlsplit(decoded_url).query)
        match = None
        for key in ("q", "query", "ll", "center", "destination"):
            for value in query.get(key, []):
                match = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", value)
                if match:
                    break
            if match:
                break
        if not match:
            raise ValueError("Could not find coordinates in the Google Maps link")
        latitude, longitude = float(match.group(1)), float(match.group(2))

    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError(f"Google Maps link contains an invalid latitude: {latitude}")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError(f"Google Maps link contains an invalid longitude: {longitude}")
    return latitude, longitude


def google_maps_coordinates(url):
    """Follow a Google Maps link and read coordinates from its resolved URL."""
    parsed_url = urlsplit(url)
    host = (parsed_url.hostname or "").casefold()
    if parsed_url.scheme not in {"http", "https"} or not (
        host == "maps.app.goo.gl"
        or host == "goo.gl"
        or host == "google.com"
        or host.endswith(".google.com")
    ):
        raise ValueError("The link must be a Google Maps URL")

    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=20) as response:
        resolved_url = response.geturl()

    resolved_host = (urlsplit(resolved_url).hostname or "").casefold()
    if not (
        resolved_host == "maps.app.goo.gl"
        or resolved_host == "goo.gl"
        or resolved_host == "google.com"
        or resolved_host.endswith(".google.com")
    ):
        raise ValueError("The Google Maps link redirected outside Google")
    return map_coordinates(resolved_url)


def decode_file(data):
    """Decode JSON input using BOM detection, UTF-8, or a legacy Windows fallback."""
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return data.decode("utf-32")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1252")
        except UnicodeDecodeError:
            return data.decode("latin-1")


def read_records(path):
    if path is not None:
        text = decode_file(path.read_bytes())
    elif hasattr(sys.stdin, "buffer"):
        text = sys.stdin.buffer.read().decode("utf-8-sig")
    else:
        text = sys.stdin.read()

    records = json.loads(text)
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise ValueError("Input JSON must be a record or a list of records")
    return records


def coordinate(record, corner, axis, minimum, maximum, index):
    try:
        value = float(record[corner][axis])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Record {index} must have numeric {corner}.{axis}") from error
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"Record {index} has out-of-range {corner}.{axis}")
    return value


def validated_bounds(record, index):
    if not isinstance(record, dict) or not isinstance(record.get("name"), str):
        raise ValueError(f"Record {index} must have a string 'name' field")
    name = record["name"]
    if not name:
        raise ValueError(f"Record {index} has an empty name")

    north = coordinate(record, "NW", "latitude", -90, 90, index)
    west = coordinate(record, "NW", "longitude", -180, 180, index)
    south = coordinate(record, "SE", "latitude", -90, 90, index)
    east = coordinate(record, "SE", "longitude", -180, 180, index)
    if south > north:
        raise ValueError(f"Record {index} has SE latitude north of NW latitude")
    return name, north, west, south, east


def contains(bounds, latitude, longitude):
    _, north, west, south, east = bounds
    longitude_is_inside = (
        west <= longitude <= east
        if west <= east
        else longitude >= west or longitude <= east
    )
    return south <= latitude <= north and longitude_is_inside


def rectangle_center(bounds):
    _, north, west, south, east = bounds
    longitude_span = (east - west) % 360
    center_longitude = (west + longitude_span / 2 + 180) % 360 - 180
    return (north + south) / 2, center_longitude


def distance_meters(latitude1, longitude1, latitude2, longitude2):
    lat1 = math.radians(latitude1)
    lat2 = math.radians(latitude2)
    latitude_delta = lat2 - lat1
    longitude_delta = math.radians((longitude2 - longitude1 + 180) % 360 - 180)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(min(1, math.sqrt(haversine)))


def closest_activity_names(records, latitude, longitude, count):
    bounds = []
    errors = []
    for index, record in enumerate(records, start=1):
        try:
            bounds.append(validated_bounds(record, index))
        except ValueError as error:
            errors.append(str(error))

    distances = [
        distance_meters(latitude, longitude, *rectangle_center(activity_bounds))
        for activity_bounds in bounds
    ]
    containing_indexes = [
        index for index, activity_bounds in enumerate(bounds)
        if contains(activity_bounds, latitude, longitude)
    ]
    containing_indexes.sort(key=distances.__getitem__)

    selected = containing_indexes[:count]
    if len(selected) < count:
        selected_indexes = set(selected)
        nearest_indexes = sorted(
            (index for index in range(len(bounds)) if index not in selected_indexes),
            key=distances.__getitem__,
        )
        selected.extend(nearest_indexes[:count - len(selected)])
    return [bounds[index][0] for index in selected], errors


def main():
    args = parse_args()
    if args.d:
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.DEBUG,
            encoding="utf-8",
            format="%(asctime)s %(levelname)s %(message)s",
        )

    try:
        records = read_records(args.file)
        if args.gmap:
            latitude, longitude = google_maps_coordinates(args.gmap)
        else:
            latitude, longitude = args.lat, args.lon
        names, errors = closest_activity_names(records, latitude, longitude, args.count)
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        for error in errors:
            print(f"Error: skipping {error}", file=sys.stderr)

        for name in names:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            print(name)
        logging.debug("Selected %d activity names from %d records", len(names), len(records))
        if errors:
            return 1
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
