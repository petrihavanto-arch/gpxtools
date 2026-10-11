import argparse
import json
import sys
import gpxpy

def parse_gpx(file_obj):
    gpx = gpxpy.parse(file_obj)
    coordinates = []

    # Extract points from tracks
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                coordinates.append({"lat": point.latitude, "lng": point.longitude})
                
    # Fallback to routes if tracks are empty
    if not coordinates:
        for route in gpx.routes:
            for point in route.points:
                coordinates.append({"lat": point.latitude, "lng": point.longitude})
                
    return coordinates

def generate_html(coordinates):
    center = coordinates[0] if coordinates else {"lat": 0, "lng": 0}
    
    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <title>GPX Route on Google Maps</title>
    <style>
        #map {{ height: 100vh; width: 100%; }}
        html, body {{ height: 100%; margin: 0; padding: 0; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        function initMap() {{
            const coordinates = {json.dumps(coordinates)};
            const mapOptions = {{
                zoom: 13,
                center: {json.dumps(center)}
            }};
            const map = new google.maps.Map(document.getElementById("map"), mapOptions);
            
            const routePath = new google.maps.Polyline({{
                path: coordinates,
                geodesic: true,
                strokeColor: "#FF0000",
                strokeOpacity: 1.0,
                strokeWeight: 3
            }});
            routePath.setMap(map);
        }
    </script>
    <script async defer src="https://maps.googleapis.com/maps/api/js?key=YOUR_API_KEY&callback=initMap"></script>
</body>
</html>
"""
    return html_template

def main():
    parser = argparse.ArgumentParser(description="Parse GPX file and generate an interactive Google Maps HTML page.")
    parser.add_argument("-f", "--file", help="Path to the GPX file", default=None)
    args = parser.parse_args()

    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                coords = parse_gpx(f)
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            coords = parse_gpx(sys.stdin)
        except Exception as e:
            print(f"Error reading from stdin: {e}", file=sys.stderr)
            sys.exit(1)

    if not coords:
        print("No coordinates found in the GPX data.", file=sys.stderr)
        sys.exit(1)

    html_output = generate_html(coords)
    print(html_output)

if __name__ == "__main__":
    main()
