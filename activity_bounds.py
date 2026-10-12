#!/usr/bin/env python3
"""
Create north-west and south-east bounding corners for Garmin activity files.

Accepts GPX files and the JSON files written by fetch_activity.py. With no
--file option, reads one GPX or JSON document from UTF-8 stdin.

Examples:
    python activity_bounds.py -f hike.gpx
    python activity_bounds.py -f '*.gpx' -f '*.json' -o bounds.json
    cat hike.gpx | python activity_bounds.py
"""

import argparse
import glob
import json
import logging
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


LOG_FILE = Path(__file__).with_name(f"{Path(__file__).stem}.log")
SEMICIRCLE_DEGREES = 180 / (2 ** 31)
LATITUDE_KEYS = {"lat", "latitude", "latitudeindegree", "directlatitude"}
LONGITUDE_KEYS = {"lon", "lng", "longitude", "longitudeindegree", "directlongitude"}


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "-f", "--file", action="append", nargs="+", metavar="PATH_OR_PATTERN",
        help="input GPX or JSON file; repeat or provide multiple paths/patterns",
    )
    parser.add_argument("-o", "--outfile", type=Path, help="write JSON to this file instead of stdout")
    parser.add_argument("-d", action="store_true", help="write DEBUG logs to activity_bounds.log next to this script")
    return parser.parse_args()


def configure_logging(debug):
    if debug:
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.DEBUG,
            encoding="utf-8",
            format="%(asctime)s %(levelname)s %(message)s",
        )


def decode_file(data):
    """Decode a text file using BOMs, UTF-8, or a Windows-compatible fallback."""
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return data.decode("utf-32")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def read_stdin():
    """Read stdin as UTF-8, using its byte stream where available."""
    if hasattr(sys.stdin, "buffer"):
        return sys.stdin.buffer.read().decode("utf-8-sig")
    return sys.stdin.read()


def expand_files(file_arguments):
    """Expand file patterns and return existing paths in argument order."""
    paths = []
    seen = set()
    for argument_group in file_arguments or []:
        for pattern in argument_group:
            matches = sorted(glob.glob(pattern), key=str.casefold)
            if not matches and Path(pattern).is_file():
                matches = [pattern]
            if not matches:
                raise ValueError(f"No file matches: {pattern}")
            for match in matches:
                path = Path(match)
                if not path.is_file():
                    raise ValueError(f"Not a file: {path}")
                key = str(path.resolve()).casefold()
                if key not in seen:
                    paths.append(path)
                    seen.add(key)
    return paths


def coordinate_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def add_coordinate_pair(points, latitude, longitude, semicircles=False):
    lat = coordinate_number(latitude)
    lon = coordinate_number(longitude)
    if lat is None or lon is None:
        return
    if semicircles:
        lat *= SEMICIRCLE_DEGREES
        lon *= SEMICIRCLE_DEGREES
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        points.append((lat, lon))


def normalized_key(key):
    return "".join(character for character in str(key).casefold() if character.isalnum())


def collect_json_coordinates(document):
    """Find coordinate objects and descriptor-indexed Garmin metric samples."""
    points = []
    descriptors = []

    def collect_descriptors(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if normalized_key(key) in {"metricdescriptors", "descriptors"} and isinstance(item, list):
                    descriptors.extend(descriptor for descriptor in item if isinstance(descriptor, dict))
                collect_descriptors(item)
        elif isinstance(value, list):
            for item in value:
                collect_descriptors(item)

    def visit(value):
        if isinstance(value, dict):
            keys = {normalized_key(key): item for key, item in value.items()}
            latitude_key = next((key for key in LATITUDE_KEYS if key in keys), None)
            longitude_key = next((key for key in LONGITUDE_KEYS if key in keys), None)
            if latitude_key and longitude_key:
                add_coordinate_pair(points, keys[latitude_key], keys[longitude_key])

            for key, item in value.items():
                normalized = normalized_key(key)
                if normalized == "weather":
                    continue
                if normalized == "metrics" and isinstance(item, list) and descriptors:
                    visit_metric_rows(item, descriptors, points)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    collect_descriptors(document)
    visit(document)
    return points


def visit_metric_rows(metrics, descriptors, points):
    descriptor_indexes = {}
    for index, descriptor in enumerate(descriptors):
        key = normalized_key(descriptor.get("key", descriptor.get("metricKey", "")))
        if key in LATITUDE_KEYS:
            descriptor_indexes["latitude"] = (index, descriptor)
        elif key in LONGITUDE_KEYS:
            descriptor_indexes["longitude"] = (index, descriptor)

    latitude_descriptor = descriptor_indexes.get("latitude")
    longitude_descriptor = descriptor_indexes.get("longitude")
    if latitude_descriptor is None or longitude_descriptor is None:
        return

    def visit_rows(value):
        if isinstance(value, list):
            if len(value) > max(latitude_descriptor[0], longitude_descriptor[0]):
                units = " ".join(
                    str(descriptor.get("unitKey", descriptor.get("unit", ""))).casefold()
                    for _, descriptor in (latitude_descriptor, longitude_descriptor)
                )
                add_coordinate_pair(
                    points,
                    value[latitude_descriptor[0]],
                    value[longitude_descriptor[0]],
                    semicircles="semicircle" in units,
                )
            for item in value:
                if isinstance(item, (list, dict)):
                    visit_rows(item)
        elif isinstance(value, dict):
            for item in value.values():
                visit_rows(item)

    visit_rows(metrics)


def coordinates_from_gpx(document):
    root = ET.fromstring(document)
    points = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].casefold() not in {"trkpt", "rtept"}:
            continue
        add_coordinate_pair(points, element.get("lat"), element.get("lon"))

    activity_type = None
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].casefold() not in {"trk", "rte"}:
            continue
        type_element = next(
            (child for child in element if child.tag.rsplit("}", 1)[-1].casefold() == "type"),
            None,
        )
        if type_element is not None and type_element.text and type_element.text.strip():
            activity_type = type_element.text.strip()
            break
    return points, activity_type


def coordinates_from_text(text, source_name):
    suffix = Path(source_name).suffix.casefold()
    if suffix == ".gpx":
        return coordinates_from_gpx(text)
    if suffix == ".json":
        document = json.loads(text)
        points = collect_json_coordinates(document)
        return points, activity_type_from_json(document)

    stripped = text.lstrip()
    if stripped.startswith("<"):
        return coordinates_from_gpx(text)
    document = json.loads(text)
    points = collect_json_coordinates(document)
    return points, activity_type_from_json(document)


def activity_type_from_json(document):
    if not isinstance(document, dict):
        return None
    summary = document.get("summary")
    if not isinstance(summary, dict):
        return None
    activity_type = summary.get("activityTypeDTO")
    if not isinstance(activity_type, dict):
        return None
    return activity_type.get("typeKey")


def bounds_record(name, points, activity_type=None):
    if not points:
        raise ValueError(f"No route coordinates found in {name}")
    latitudes, longitudes = zip(*points)
    if max(longitudes) - min(longitudes) <= 180:
        west, east = min(longitudes), max(longitudes)
    else:
        circular_longitudes = sorted(longitude % 360 for longitude in longitudes)
        gaps = [
            (circular_longitudes[(index + 1) % len(circular_longitudes)] - longitude) % 360
            for index, longitude in enumerate(circular_longitudes)
        ]
        largest_gap_index = max(range(len(gaps)), key=gaps.__getitem__)
        west = circular_longitudes[(largest_gap_index + 1) % len(circular_longitudes)]
        east = circular_longitudes[largest_gap_index]
        west = (west + 180) % 360 - 180
        east = (east + 180) % 360 - 180
    box_center_longitude = (west + ((east - west) % 360) / 2 + 180) % 360 - 180
    return {
        "name": name,
        "NW": {"latitude": max(latitudes), "longitude": west},
        "SE": {"latitude": min(latitudes), "longitude": east},
        "box_center": {
            "latitude": (max(latitudes) + min(latitudes)) / 2,
            "longitude": box_center_longitude,
        },
        "weighed_center": {
            "latitude": sum(latitudes) / len(latitudes),
            "longitude": sum(longitudes) / len(longitudes),
        },
        "act": activity_type,
    }


def records_from_files(paths):
    records = []
    errors = []
    for path in paths:
        try:
            text = decode_file(path.read_bytes())
            points, activity_type = coordinates_from_text(text, path.name)
            records.append(bounds_record(path.name, points, activity_type))
            logging.debug("Read %d coordinates from %s", len(points), path)
        except (OSError, UnicodeError, ValueError, ET.ParseError, json.JSONDecodeError) as error:
            errors.append(f"{path}: {error}")
    return records, errors


def main():
    args = parse_args()
    configure_logging(args.d)

    try:
        if args.file:
            records, errors = records_from_files(expand_files(args.file))
            if errors and hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8")
            for error in errors:
                print(f"Error: skipping {error}", file=sys.stderr)
        else:
            text = read_stdin()
            points, activity_type = coordinates_from_text(text, "stdin")
            records = [bounds_record("stdin", points, activity_type)]
            errors = []

        output = json.dumps(records, ensure_ascii=False, indent=2)
        if args.outfile:
            args.outfile.write_text(output + "\n", encoding="utf-8")
        else:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            print(output)
        if errors:
            return 1
    except (OSError, UnicodeError, ValueError, ET.ParseError, json.JSONDecodeError) as error:
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
