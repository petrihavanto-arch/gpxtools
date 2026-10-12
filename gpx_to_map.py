import argparse
import json
import os
import sys
import gpxpy
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>GPX Routes on Google Maps</title>
    <style>
        #map { height: 100vh; width: 100%; }
        html, body { height: 100%; margin: 0; padding: 0; }
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        function initMap() {
            const allPaths = __PATHS__;
            const defaultCenter = allPaths.length > 0 && allPaths[0].length > 0 ? allPaths[0][0] : {lat: 0, lng: 0};
            
            const mapOptions = {
                zoom: 13,
                center: defaultCenter
            };
            const map = new google.maps.Map(document.getElementById("map"), mapOptions);
            
            // Distinct colors for multiple tracks
            const colors = ["#FF0000", "#0000FF", "#008000", "#FF8C00", "#800080", "#00FFFF", "#FF1493"];
            
            allPaths.forEach((pathCoords, index) => {
                if (pathCoords.length > 0) {
                    const routePath = new google.maps.Polyline({
                        path: pathCoords,
                        geodesic: true,
                        strokeColor: colors[index % colors.length],
                        strokeOpacity: 1.0,
                        strokeWeight: 3
                    });
                    routePath.setMap(map);
                }
            });
        }
    </script>
    <script async defer src="https://maps.googleapis.com/maps/api/js?key=__API_KEY__&callback=initMap"></script>
</body>
</html>
"""

def parse_gpx_file(file_obj):
    gpx = gpxpy.parse(file_obj)
    coordinates = []
    
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                coordinates.append({"lat": point.latitude, "lng": point.longitude})
                
    if not coordinates:
        for route in gpx.routes:
            for point in route.points:
                coordinates.append({"lat": point.latitude, "lng": point.longitude})
                
    return coordinates

def generate_html(paths):
    api_key = os.getenv("GOOGLE_MAPS_JS_API", "YOUR_API_KEY")
    html = HTML_TEMPLATE.replace("__PATHS__", json.dumps(paths))
    html = html.replace("__API_KEY__", api_key)
    return html

def main():
    parser = argparse.ArgumentParser(description="Parse GPX file(s) and generate an interactive Google Maps HTML page.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-f", "--file", help="Path to a single GPX file")
    group.add_argument("-r", "--read", help="Path to a text file containing a list of GPX file paths (one per line)")
    args = parser.parse_args()

    paths = []

    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                coords = parse_gpx_file(f)
                if coords:
                    paths.append(coords)
        except Exception as e:
            print(f"Error reading file {args.file}: {e}", file=sys.stderr)
            sys.exit(1)
            
    elif args.read:
        try:
            with open(args.read, "r", encoding="utf-8") as r_file:
                for line in r_file:
                    gpx_path = line.strip()
                    if not gpx_path or gpx_path.startswith("#"):
                        continue
                    try:
                        with open(gpx_path, "r", encoding="utf-8") as g_file:
                            coords = parse_gpx_file(g_file)
                            if coords:
                                paths.append(coords)
                    except Exception as e:
                        print(f"Warning: Could not read GPX file '{gpx_path}': {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error reading list file {args.read}: {e}", file=sys.stderr)
            sys.exit(1)
            
    else:
        try:
            coords = parse_gpx_file(sys.stdin)
            if coords:
                paths.append(coords)
        except Exception as e:
            print(f"Error reading from stdin: {e}", file=sys.stderr)
            sys.exit(1)

    if not paths or all(len(p) == 0 for p in paths):
        print("No valid coordinates found in the GPX data.", file=sys.stderr)
        sys.exit(1)

    html_output = generate_html(paths)
    print(html_output)

if __name__ == "__main__":
    main()

