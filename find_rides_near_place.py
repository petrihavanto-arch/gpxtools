#!/usr/bin/env python3
"""
find_rides_near_place.py

Search your Garmin Connect activity history for rides/runs that passed
within a given radius of a specific location, even if you don't remember
when you did them.

Requires:
    pip install garminconnect garth gpxpy

Setup:
    Garmin now requires MFA-aware login via the `garth` session layer,
    which python-garminconnect uses under the hood. The first run will
    prompt for email/password (and an MFA code if enabled) and cache a
    session token locally (~/.garminconnect) so you don't have to log in
    every time.

Usage:
    python find_rides_near_place.py --lat 60.1699 --lon 24.9384 \
        --radius 300 --activity-type cycling --start 2018-01-01

    --lat/--lon      target coordinates (e.g. copy from Google Maps)
    --radius         search radius in metres around the target point
    --activity-type  optional Garmin activity type filter, e.g.
                      cycling, running, mountain_biking, gravel_cycling
    --start / --end  optional ISO date bounds (YYYY-MM-DD) to limit the
                      search and speed things up
    --limit          max number of activities to scan (default: all)
"""

import argparse
import datetime as dt
import math
import os
import sys
import tempfile
import zipfile

import gpxpy
from garminconnect import Garmin, GarminConnectAuthenticationError


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in metres."""
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def login():
    email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ")
    password = os.environ.get("GARMIN_PASSWORD")
    if not password:
        import getpass
        password = getpass.getpass("Garmin password: ")

    api = Garmin(email, password)
    try:
        api.login()
    except GarminConnectAuthenticationError:
        # MFA-enabled accounts raise here; garth's login flow will prompt
        # for the emailed/app code interactively.
        code = input("Enter MFA code sent to your device: ")
        api.login(code)
    return api


def track_within_radius(gpx_bytes, target_lat, target_lon, radius_m):
    gpx = gpxpy.parse(gpx_bytes)
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                if haversine_m(point.latitude, point.longitude, target_lat, target_lon) <= radius_m:
                    return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius", type=float, default=250, help="search radius in metres (default 250)")
    ap.add_argument("--activity-type", default=None, help="e.g. cycling, running, mountain_biking")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=2000, help="max activities to scan")
    args = ap.parse_args()

    api = login()

    print("Fetching activity list...", file=sys.stderr)
    activities = api.get_activities(0, args.limit)

    if args.start:
        start_date = dt.date.fromisoformat(args.start)
        activities = [a for a in activities if dt.date.fromisoformat(a["startTimeLocal"][:10]) >= start_date]
    if args.end:
        end_date = dt.date.fromisoformat(args.end)
        activities = [a for a in activities if dt.date.fromisoformat(a["startTimeLocal"][:10]) <= end_date]
    if args.activity_type:
        activities = [
            a for a in activities
            if args.activity_type.lower() in a.get("activityType", {}).get("typeKey", "").lower()
        ]

    print(f"Scanning {len(activities)} activities for tracks near "
          f"({args.lat}, {args.lon}) within {args.radius} m...", file=sys.stderr)

    matches = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, act in enumerate(activities, 1):
            act_id = act["activityId"]
            name = act.get("activityName", "Unnamed")
            date = act["startTimeLocal"][:10]
            print(f"  [{i}/{len(activities)}] {date}  {name}", file=sys.stderr, end="\r")

            try:
                gpx_bytes = api.download_activity(act_id, dl_fmt=api.ActivityDownloadFormat.GPX)
            except Exception as e:
                print(f"\n  Skipping {act_id} ({name}): {e}", file=sys.stderr)
                continue

            try:
                if track_within_radius(gpx_bytes, args.lat, args.lon, args.radius):
                    matches.append((date, name, act_id))
            except Exception as e:
                print(f"\n  Could not parse GPX for {act_id}: {e}", file=sys.stderr)

    print("\n\nMatches:")
    if not matches:
        print("  None found.")
    for date, name, act_id in sorted(matches):
        url = f"https://connect.garmin.com/modern/activity/{act_id}"
        print(f"  {date}  {name}  -> {url}")


if __name__ == "__main__":
    main()
