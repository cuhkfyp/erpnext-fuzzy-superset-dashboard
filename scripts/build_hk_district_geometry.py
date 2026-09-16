#!/usr/bin/env python3
"""Build compact, reproducible Hong Kong district geometry for the dashboard.

Input is the Home Affairs Department's public 18-district boundary GeoJSON:
https://www.had.gov.hk/psi/hong-kong-administrative-boundaries/
hksar_18_district_boundary.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


DISTRICT_CODES = {
    "Central and Western District": "CW",
    "Eastern District": "EST",
    "Southern District": "SOU",
    "Wan Chai District": "WC",
    "Kowloon City District": "KC",
    "Kwun Tong District": "KWT",
    "Sham Shui Po District": "SSP",
    "Wong Tai Sin District": "WTS",
    "Yau Tsim Mong District": "YTM",
    "Islands District": "IS",
    "Kwai Tsing District": "KUI",
    "North District": "NOR",
    "Sai Kung District": "SK",
    "Sha Tin District": "ST",
    "Tai Po District": "TP",
    "Tsuen Wan District": "TW",
    "Tuen Mun District": "TM",
    "Yuen Long District": "YL",
}


def perpendicular_distance(point: list[float], start: list[float], end: list[float]) -> float:
    if start == end:
        return math.dist(point, start)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    numerator = abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0])
    return numerator / math.hypot(dx, dy)


def simplify_line(points: list[list[float]], tolerance: float) -> list[list[float]]:
    if len(points) <= 2:
        return points
    maximum = 0.0
    index = 0
    for offset, point in enumerate(points[1:-1], start=1):
        distance = perpendicular_distance(point, points[0], points[-1])
        if distance > maximum:
            maximum = distance
            index = offset
    if maximum <= tolerance:
        return [points[0], points[-1]]
    left = simplify_line(points[: index + 1], tolerance)
    right = simplify_line(points[index:], tolerance)
    return left[:-1] + right


def simplify_ring(ring: list[list[float]], tolerance: float) -> list[list[float]]:
    open_ring = ring[:-1] if ring and ring[0] == ring[-1] else ring[:]
    if len(open_ring) < 4:
        return ring
    # Rotate away from an arbitrary closure point before applying RDP.
    split = max(range(len(open_ring)), key=lambda i: math.dist(open_ring[0], open_ring[i]))
    rotated = open_ring[split:] + open_ring[: split + 1]
    simplified = simplify_line(rotated, tolerance)
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified if len(simplified) >= 4 else ring


def build(source: Path, output: Path, tolerance: float) -> None:
    payload = json.loads(source.read_text())
    features = []
    seen = set()
    for feature in payload["features"]:
        name = feature["properties"]["District"]
        code = DISTRICT_CODES[name]
        geometry = feature["geometry"]
        if geometry["type"] != "Polygon":
            raise ValueError(f"Unexpected geometry for {name}: {geometry['type']}")
        rings = [simplify_ring(ring, tolerance) for ring in geometry["coordinates"]]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "district_code": code,
                    "district": name,
                    "district_zh": feature["properties"]["地區"],
                },
                "geometry": {"type": "Polygon", "coordinates": rings},
            }
        )
        seen.add(code)
    if seen != set(DISTRICT_CODES.values()):
        raise ValueError(f"District coverage mismatch: {sorted(seen)}")
    result = {
        "type": "FeatureCollection",
        "source": "Hong Kong Home Affairs Department 18-district boundary",
        "source_url": (
            "https://www.had.gov.hk/psi/hong-kong-administrative-boundaries/"
            "hksar_18_district_boundary.json"
        ),
        "simplification_tolerance_degrees": tolerance,
        "features": sorted(features, key=lambda item: item["properties"]["district_code"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tolerance", type=float, default=0.0002)
    args = parser.parse_args()
    build(args.source, args.output, args.tolerance)


if __name__ == "__main__":
    main()
