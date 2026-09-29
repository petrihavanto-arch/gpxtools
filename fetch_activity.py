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
"""

import argparse
import json
import os
import re
import sys

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
        sys.exit(f"Could not find an activity ID in URL: {url}")
    return match.group(1)


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="Garmin Connect activity URL")
    ap.add_argument("--outdir", default=".", help="directory to save output files (default: current dir)")
    ap.add_argument("--gpx", action="store_true", help="also download the GPX track")
    ap.add_argument("--tcx", action="store_true", help="also download the TCX track")
    args = ap.parse_args()

    activity_id = activity_id_from_url(args.url)
    os.makedirs(args.outdir, exist_ok=True)

    api = login()

    print(f"Fetching data for activity {activity_id}...", file=sys.stderr)
    data = fetch_all(api, activity_id)

    json_path = os.path.join(args.outdir, f"activity_{activity_id}.json")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Saved metrics/splits/weather/gear -> {json_path}")

    if args.gpx:
        gpx_bytes = api.download_activity(activity_id, dl_fmt=api.ActivityDownloadFormat.GPX)
        gpx_path = os.path.join(args.outdir, f"activity_{activity_id}.gpx")
        with open(gpx_path, "wb") as f:
            f.write(gpx_bytes)
        print(f"Saved GPX track -> {gpx_path}")

    if args.tcx:
        tcx_bytes = api.download_activity(activity_id, dl_fmt=api.ActivityDownloadFormat.TCX)
        tcx_path = os.path.join(args.outdir, f"activity_{activity_id}.tcx")
        with open(tcx_path, "wb") as f:
            f.write(tcx_bytes)
        print(f"Saved TCX track -> {tcx_path}")

    # Quick human-readable summary to stdout
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


if __name__ == "__main__":
    main()
