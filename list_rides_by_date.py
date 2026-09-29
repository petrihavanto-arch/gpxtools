#!/usr/bin/env python3
"""
list_rides_by_date.py

List your Garmin Connect activities within a date range (no GPS/location
filtering — just date + optional activity type).

Requires:
    pip install garminconnect garth python-dotenv

Setup:
    Create a .env file next to this script with:

        GARMIN_EMAIL=you@example.com
        GARMIN_PASSWORD=your-password

    The first run may also prompt for an MFA code if your account has it
    enabled; a session token is cached locally (~/.garminconnect) after
    that so you won't need to log in every time.

Usage:
    python list_rides_by_date.py --start 2020-06-01 --end 2020-06-30
    python list_rides_by_date.py --start 2020-06-01 --activity-type cycling

Note:
    This queries Garmin's date-range search endpoint directly
    (get_activities_by_date), rather than paging through your most-recent
    activities — so it reaches arbitrarily far back, not just the last
    few months.
"""

import argparse
import datetime as dt
import os
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
        # MFA-enabled accounts raise here; prompt for the emailed/app code.
        code = input("Enter MFA code sent to your device: ")
        api.login(code)
    return api


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2000-01-01", help="YYYY-MM-DD (default: 2000-01-01, i.e. 'all history')")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument(
        "--activity-type", default=None,
        help="one of: cycling, running, swimming, multi_sport, fitness_equipment, hiking, walking, other",
    )
    args = ap.parse_args()

    end = args.end or dt.date.today().isoformat()

    api = login()

    print(f"Fetching activities from {args.start} to {end}...", file=sys.stderr)
    activities = api.get_activities_by_date(args.start, end, args.activity_type)

    print(f"\n{len(activities)} matching activities:\n")
    if not activities:
        print("  None found.")
    for act in sorted(activities, key=lambda a: a["startTimeLocal"]):
        date = act["startTimeLocal"][:10]
        name = act.get("activityName", "Unnamed")
        act_id = act["activityId"]
        url = f"https://connect.garmin.com/modern/activity/{act_id}"
        print(f"  {date}  {name}  -> {url}")


if __name__ == "__main__":
    main()
