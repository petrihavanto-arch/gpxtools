import argparse
import json
import math
import os
import re
import sys
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

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
        #legend {
            position: absolute;
            top: 15px;
            right: 15px;
            background: white;
            padding: 12px 16px;
            font-family: Arial, sans-serif;
            font-size: 13px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            z-index: 5;
            border-radius: 6px;
            max-width: 340px;
            max-height: 80vh;
            overflow-y: auto;
        }
        #legend h4 {
            margin: 0 0 4px 0;
            font-size: 14px;
            color: #333;
        }
        .legend-subtitle {
            font-size: 11px;
            color: #770000;
            margin-bottom: 8px;
            font-style: italic;
        }
        .legend-item {
            display: flex;
            align-items: center;
            margin-bottom: 6px;
            cursor: pointer;
            padding: 4px;
            border-radius: 4px;
            transition: background 0.2s;
        }
        .legend-item:hover {
            background-color: #f0f0f0;
        }
        .color-box {
            width: 16px;
            height: 16px;
            margin-right: 8px;
            border-radius: 3px;
            flex-shrink: 0;
        }
        .legend-text {
            word-break: break-all;
            color: #555;
        }
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="legend">
        <h4>GPX Tracks Legend</h4>
        <div class="legend-subtitle">Click item to highlight route</div>
        <div id="legend-content"></div>
    </div>
    <script>
        function initMap() {
            const trackData = __TRACK_DATA__;
            const linkedLocation = __GMAP_LOCATION__;
            if (trackData.length === 0 && !linkedLocation) return;

            const defaultCenter = trackData.length > 0 && trackData[0].coordinates.length > 0
                ? trackData[0].coordinates[0] 
                : linkedLocation || {lat: 0, lng: 0};
            
            const mapOptions = {
                zoom: 13,
                center: defaultCenter
            };
            const map = new google.maps.Map(document.getElementById("map"), mapOptions);

            if (linkedLocation) {
                new google.maps.Marker({
                    position: linkedLocation,
                    map: map,
                    icon: {
                        path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                        scale: 7,
                        fillColor: "#FF0000",
                        fillOpacity: 1.0,
                        strokeColor: "#990000",
                        strokeWeight: 2
                    },
                    title: "Google Maps location"
                });
            }
            
            // Distinct track colors
            const colors = ["#E63946", "#1D3557", "#457B9D", "#2A9D8F", "#E9C46A", "#F4A261", "#D62828", "#6A040F"];
            const legendContent = document.getElementById("legend-content");
            const polylines = [];
            
            trackData.forEach((item, index) => {
                const color = colors[index % colors.length];
                const coords = item.coordinates;
                
                if (coords.length > 0) {
                    // Draw Polyline for the track
                    const routePath = new google.maps.Polyline({
                        path: coords,
                        geodesic: true,
                        strokeColor: color,
                        strokeOpacity: 0.85,
                        strokeWeight: 4,
                        zIndex: 1
                    });
                    routePath.setMap(map);
                    polylines.push(routePath);
                    
                    // Add a red arrow marker at the starting point
                    const startPoint = coords[0];
                    new google.maps.Marker({
                        position: startPoint,
                        map: map,
                        icon: {
                            path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                            scale: 6,
                            fillColor: "#FF0000",
                            fillOpacity: 1.0,
                            strokeColor: "#990000",
                            strokeWeight: 2
                        },
                        title: "Start: " + item.name
                    });

                    // Add entry to the map legend with click-to-highlight feature
                    const legendItem = document.createElement("div");
                    legendItem.className = "legend-item";
                    legendItem.innerHTML = `
                        <div class="color-box" style="background-color: ${color};"></div>
                        <div class="legend-text" title="${item.name}">${item.name}</div>
                    `;
                    
                    let isHighlighted = false;
                    legendItem.addEventListener("click", () => {
                        isHighlighted = !isHighlighted;
                        
                        if (isHighlighted) {
                            // Dim all other lines, highlight this one
                            polylines.forEach((line, idx) => {
                                if (idx === index) {
                                    line.setOptions({ strokeWeight: 7, strokeOpacity: 1.0, zIndex: 10 });
                                } else {
                                    line.setOptions({ strokeWeight: 2, strokeOpacity: 0.2, zIndex: 1 });
                                }
                            });
                            legendItem.style.backgroundColor = "#e2e8f0";
                        } else {
                            // Reset all lines back to normal
                            polylines.forEach((line) => {
                                line.setOptions({ strokeWeight: 4, strokeOpacity: 0.85, zIndex: 1 });
                            });
                            legendItem.style.backgroundColor = "transparent";
                        }
                    });

                    legendContent.appendChild(legendItem);
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

def generate_html(track_data, gmap_location=None):
    api_key = os.getenv("GOOGLE_MAPS_JS_API", "YOUR_API_KEY")
    html = HTML_TEMPLATE.replace("__TRACK_DATA__", json.dumps(track_data))
    html = html.replace("__GMAP_LOCATION__", json.dumps(gmap_location))
    html = html.replace("__API_KEY__", api_key)
    return html


def map_coordinates(url):
    """Extract latitude and longitude from a resolved Google Maps URL."""
    decoded_url = unquote(url)
    patterns = (
        r"/maps/(?:search|place)/(-?\d+(?:\.\d+)?),\s*\+?\s*(-?\d+(?:\.\d+)?)(?:[/?]|$)",
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
    return {"lat": latitude, "lng": longitude}


def google_maps_location(url):
    """Resolve a Google Maps link and get its destination coordinates."""
    allowed_host = lambda host: (
        host == "maps.app.goo.gl"
        or host == "goo.gl"
        or host == "google.com"
        or host.endswith(".google.com")
    )
    parsed_url = urlsplit(url)
    host = (parsed_url.hostname or "").casefold()
    if parsed_url.scheme not in {"http", "https"} or not allowed_host(host):
        raise ValueError("The link must be a Google Maps URL")

    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=20) as response:
        resolved_url = response.geturl()
    if not allowed_host((urlsplit(resolved_url).hostname or "").casefold()):
        raise ValueError("The Google Maps link redirected outside Google")
    return map_coordinates(resolved_url)


def main():
    parser = argparse.ArgumentParser(description="Parse GPX file(s) and generate an interactive Google Maps HTML page with markers and legend.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-f", "--file", help="Path to a single GPX file")
    group.add_argument("-r", "--read", help="Path to a text file containing a list of GPX file paths (one per line)")
    parser.add_argument("-g", "--gmap", help="Google Maps link; add its location to the map with a red arrow")
    args = parser.parse_args()

    track_data = []
    gmap_location = None

    if args.gmap:
        try:
            gmap_location = google_maps_location(args.gmap)
        except (OSError, URLError, TimeoutError, ValueError) as e:
            print(f"Error resolving Google Maps link: {e}", file=sys.stderr)
            return 1

    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                coords = parse_gpx_file(f)
                if coords:
                    track_data.append({"name": os.path.basename(args.file), "coordinates": coords})
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
                                track_data.append({"name": os.path.basename(gpx_path), "coordinates": coords})
                    except Exception as e:
                        print(f"Warning: Could not read GPX file '{gpx_path}': {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error reading list file {args.read}: {e}", file=sys.stderr)
            sys.exit(1)
            
    else:
        try:
            coords = parse_gpx_file(sys.stdin)
            if coords:
                track_data.append({"name": "stdin_route", "coordinates": coords})
        except Exception as e:
            print(f"Error reading from stdin: {e}", file=sys.stderr)
            sys.exit(1)

    if not track_data and not gmap_location:
        print("No valid coordinates found in the GPX data.", file=sys.stderr)
        return 1

    html_output = generate_html(track_data, gmap_location)
    print(html_output)
    return 0

if __name__ == "__main__":
    sys.exit(main())
