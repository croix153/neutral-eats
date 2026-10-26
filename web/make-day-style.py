#!/usr/bin/env python3
"""Generate tokyo-style-day.json from tokyo-style.json.

The day style is a pure recolor of the night style: identical sources,
glyphs, sprite, layer ids/order/types/filters/layout — only paint colors
(and the style name) change. Every paint color in the night style must be
covered by an explicit mapping below (per-layer, or the generic
text-halo rule); the script fails loudly on anything unmapped so a
future night-style edit can't silently leak a night color into day.

Run:  python3 web/make-day-style.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "tokyo-style.json")
DST = os.path.join(HERE, "tokyo-style-day.json")

# Per-layer paint overrides for the day ("daytime Tokyo") palette:
# bright clean land, pale blue water, white roads with indigo-slate
# casing, soft peach motorways, slate labels on white halos.
LAYER_PAINT = {
    "background":            {"background-color": "#eef0f6"},
    "water":                 {"fill-color": "#b7cde9"},
    "landcover_ice_shelf":   {"fill-color": "#e3e9f7"},
    "landcover_glacier":     {"fill-color": "#dfe7f5"},
    "landuse_residential":   {"fill-color": "#e3e8f5"},
    "landcover_wood":        {"fill-color": "#cfe0cd"},
    "landuse_park":          {"fill-color": "#cfe0cd"},
    "waterway":              {"line-color": "#a9c4e4"},
    "water_name":            {"text-color": "#5b78a8"},
    "building":              {"fill-color": "#dbe1f0",
                              "fill-outline-color": "#c6cfe4"},
    "aeroway-taxiway":       {"line-color": "#c6cfe4"},
    "aeroway-runway-casing": {"line-color": "#b4c0da"},
    "aeroway-area":          {"fill-color": "#e3e8f5"},
    "aeroway-runway":        {"line-color": "#d3daee"},
    "road_area_pier":        {"fill-color": "#e3e8f5"},
    "road_pier":             {"line-color": "#c9d1e6"},
    "highway_path":          {"line-color": "#ccd4e8"},
    "highway_minor":         {"line-color": "#ffffff"},
    "highway_major_casing":  {"line-color": "#c9d1e6"},
    "highway_major_inner":   {"line-color": "#ffffff"},
    "highway_major_subtle":  {"line-color": "#d5dbee"},
    "highway_motorway_casing": {"line-color": "#e5c184"},
    "highway_motorway_inner":  {"line-color": "#ffdca9"},
    "highway_motorway_subtle": {"line-color": "#f0d9ac"},
    "railway_transit":         {"line-color": "#9aa7c7"},
    "railway_transit_dashline": {"line-color": "#f4f6fb"},
    "railway_minor":           {"line-color": "#9aa7c7"},
    "railway_minor_dashline":  {"line-color": "#f4f6fb"},
    "railway":                 {"line-color": "#9aa7c7"},
    "railway_dashline":        {"line-color": "#f4f6fb"},
    "highway_name_other":    {"text-color": "#46506e"},
    "highway_name_motorway": {"text-color": "#46506e"},
    "boundary_state":        {"line-color": "rgba(70,80,110,0.30)"},
    "boundary_country_z0-4": {"line-color": "rgba(70,80,110,0.38)"},
    "boundary_country_z5-":  {"line-color": "rgba(70,80,110,0.38)"},
    "place_other":           {"text-color": "#5d6a8c"},
    "place_suburb":          {"text-color": "#5d6a8c"},
    "place_village":         {"text-color": "#5d6a8c"},
    "place_town":            {"text-color": "#46506e"},
    "place_city":            {"text-color": "#333d5e"},
    "place_city_large":      {"text-color": "#333d5e"},
    "place_state":           {"text-color": "#71809e"},
    "place_country_other":   {"text-color": "#5d6a8c"},
    "place_country_minor":   {"text-color": "#5d6a8c"},
    "place_country_major":   {"text-color": "#46506e"},
}

# Generic rules applied after the per-layer map: the night halo color
# (#070912, the night bg) becomes a white halo on every symbol layer;
# water_name's slightly different halo target is handled here too.
HALO_NIGHT = "#070912"
HALO_DAY = "#ffffff"
WATER_HALO_DAY = "#eef4fb"


def is_color(v):
    return isinstance(v, str) and (v.startswith("#") or v.startswith("rgb"))


def main():
    with open(SRC) as f:
        night = json.load(f)
    day = copy.deepcopy(night)
    day["name"] = "Neutral Eats Tokyo Day (based on OpenFreeMap Dark)"

    unmapped = []
    for layer in day["layers"]:
        lid = layer["id"]
        paint = layer.get("paint", {})
        overrides = LAYER_PAINT.get(lid, {})
        for prop, val in paint.items():
            if prop in overrides:
                paint[prop] = overrides[prop]
            elif prop == "text-halo-color" and val == HALO_NIGHT:
                paint[prop] = WATER_HALO_DAY if lid == "water_name" else HALO_DAY
            elif is_color(val):
                unmapped.append(f"{lid}.{prop} = {val}")
            # non-color paint (widths, opacity, dash...) carries over as-is
        extra = set(overrides) - set(paint)
        if extra:
            unmapped.append(f"{lid}: overrides for absent props {sorted(extra)}")

    if unmapped:
        print("UNMAPPED paint colors (extend LAYER_PAINT):", file=sys.stderr)
        for u in unmapped:
            print("  " + u, file=sys.stderr)
        return 1

    # Structural proof: everything except paint + name is identical.
    assert len(day["layers"]) == len(night["layers"])
    for a, b in zip(day["layers"], night["layers"]):
        assert a["id"] == b["id"] and a["type"] == b["type"]
        aa = {k: v for k, v in a.items() if k != "paint"}
        bb = {k: v for k, v in b.items() if k != "paint"}
        assert aa == bb, f"non-paint drift in layer {a['id']}"
    for key in ("sources", "glyphs", "sprite", "version"):
        assert day.get(key) == night.get(key), f"top-level drift: {key}"

    with open(DST, "w") as f:
        json.dump(day, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {DST}: {len(day['layers'])} layers, structure identical, "
          "all paint colors mapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
