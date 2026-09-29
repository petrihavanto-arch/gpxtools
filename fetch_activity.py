#!/usr/bin/env python3
"""
fetch_activity.py

Given a Garmin Connect activity URL, fetch its logged data (summary
metrics, splits, weather, gear, GPS track) and save it locally.

Requires:
    pip install garminconnect garth python-dotenv

Setup:
    Create a .env file next to this script with:

        GARMIN_EMAIL=you@example.com
        GARMIN_PASSWORD=your-password

Usage:
    python fetch_activity.py --url https://connect.garmin.com/modern/activity/12345678901
    python fetch_activity.py --url https://connect.garmin.com/modern/activity/12345678901 --gpx
    python fetch_activity.py --url .../12345678901 --outdir ./exports
    python fetch_activity.py --file activities.txt --outfile ./exports
    python fetch_activity.py --file activities.txt --time 2
"""

import argparse
import json
import math
import os
import re
import sys
import time

from dotenv import load_dotenv
from garminconnect import Garmin, GarminConnectAuthenticationError


def login():
    load_dotenv()
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        sys.exit("Set GARMIN_EMAIL and GARMIN_PASSWORD in a .env file next to this script.")

    api = Garmin(email, password)
    try:
        api.login()
    except GarminConnectAuthenticationError:
        code = input("Enter MFA code sent to your device: ")
        api.login(code)
    return api


def activity_id_from_url(url):
    match = re.search(r"/activity/(\d+)", url)
    if not match:
        raise ValueError(f"Could not find an activity ID in URL: {url}")
    return match.group(1)


def activities_from_file(path):
    """Read activity URLs and their optional output names from a text file."""
    activities = []
    with open(path, encoding="utf-8") as activity_file:
        for line_number, line in enumerate(activity_file, 1):
            line = line.strip()
            if not line:
                continue

            match = re.search(r"https?://\S+", line)
            if not match:
                raise ValueError(f"No activity URL found on line {line_number} of {path}")

            label = re.sub(r"\s*->\s*$", "", line[:match.start()]).strip()
            filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", "_".join(label.split()))
            url = match.group(0)
            activity_id = activity_id_from_url(url)
            activities.append((url, activity_id, filename or f"activity_{activity_id}"))

    if not activities:
        raise ValueError(f"No activity URLs found in {path}")
    return activities


def non_negative_seconds(value):
    """Parse a non-negative delay in seconds for argparse."""
    try:
        seconds = float(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("must be a number of seconds") from e
    if not math.isfinite(seconds) or seconds < 0:
        raise argparse.ArgumentTypeError("must be a finite, non-negative number")
    return seconds


def fetch_all(api, activity_id):
    """Pull together everything the API exposes for one activity."""
    data = {}

    getters = {
        "summary": lambda: api.get_activity(activity_id),
        "details": lambda: api.get_activity_details(activity_id),
        "splits": lambda: api.get_activity_splits(activity_id),
        "split_summaries": lambda: api.get_activity_split_summaries(activity_id),
        "weather": lambda: api.get_activity_weather(activity_id),
        "hr_zones": lambda: api.get_activity_hr_in_timezones(activity_id),
        "gear": lambda: api.get_activity_gear(activity_id),
        "exercise_sets": lambda: api.get_activity_exercise_sets(activity_id),
    }

    for key, fn in getters.items():
        try:
            data[key] = fn()
        except Exception as e:
            print(f"  (skipped '{key}': {e})", file=sys.stderr)
            data[key] = None

    return data


def fetch_and_save(api, activity_id, filename, outdir, download_gpx, download_tcx):
    print(f"Fetching data for activity {activity_id}...", file=sys.stderr)
    data = fetch_all(api, activity_id)

    json_path = os.path.join(outdir, f"{filename}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Saved metrics/splits/weather/gear -> {json_path}")

    if download_gpx:
        gpx_bytes = api.download_activity(activity_id, dl_fmt=api.ActivityDownloadFormat.GPX)
        gpx_path = os.path.join(outdir, f"{filename}.gpx")
        with open(gpx_path, "wb") as f:
            f.write(gpx_bytes)
        print(f"Saved GPX track -> {gpx_path}")

    if download_tcx:
        tcx_bytes = api.download_activity(activity_id, dl_fmt=api.ActivityDownloadFormat.TCX)
        tcx_path = os.path.join(outdir, f"{filename}.tcx")
        with open(tcx_path, "wb") as f:
            f.write(tcx_bytes)
        print(f"Saved TCX track -> {tcx_path}")

    summary = data.get("summary") or {}
    if summary:
        name = summary.get("activityName", "Unnamed")
        act_type = summary.get("activityType", {}).get("typeKey", "unknown")
        date = summary.get("startTimeLocal", "unknown date")
        distance_km = (summary.get("distance") or 0) / 1000
        duration_min = (summary.get("duration") or 0) / 60
        print(f"\n{name}  ({act_type})")
        print(f"  Date: {date}")
        print(f"  Distance: {distance_km:.2f} km")
        print(f"  Duration: {duration_min:.1f} min")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Garmin Connect activity URL")
    source.add_argument("-f", "--file", help="file containing activity URLs, one per line")
    ap.add_argument(
        "-o", "--outfile", "--outdir", dest="outfile", default=".",
        help="directory to save output files (default: current dir)",
    )
    ap.add_argument("--gpx", action="store_true", help="also download the GPX track")
    ap.add_argument("--tcx", action="store_true", help="also download the TCX track")
    ap.add_argument(
        "-t", "--time", type=non_negative_seconds, default=0,
        help="seconds to wait between fetching activities (default: 0)",
    )
    args = ap.parse_args()

    try:
        if args.file:
            activities = activities_from_file(args.file)
        else:
            activity_id = activity_id_from_url(args.url)
            activities = [(args.url, activity_id, f"activity_{activity_id}")]
    except (OSError, ValueError) as e:
        ap.error(str(e))

    os.makedirs(args.outfile, exist_ok=True)
    api = login()
    for index, (_, activity_id, filename) in enumerate(activities):
        if index:
            time.sleep(args.time)
        fetch_and_save(api, activity_id, filename, args.outfile, args.gpx, args.tcx)


if __name__ == "__main__":
    main()
