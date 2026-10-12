#!/usr/bin/bash
python3 find_activities_near_coordinates.py -c 5 -f logs/Mtb -g $1  > tiedostot.lst
python3 gpx_to_map.py -r ./tiedostot.lst -p logs/mtb 



