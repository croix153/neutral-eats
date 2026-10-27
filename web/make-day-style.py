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

# Per-layer paint overrides for the day palette — realigned
# 2026-10-26 to the Creams Tokyo DAY identity (Croix: "that blue
# and vermillion"): washi-paper land #FAF7F2, pale ai-iro water
# with indigo water labels, warm sand buildings, white roads with
# warm casings, soft shu-iro motorways, warm stone label text on
# washi halos.
LAYER_PAINT = {
    "background":            {"background-color": "#faf7f2"},
    "water":                 {"fill-color": "#b4cfe3"},
    "landcover_ice_shelf":   {"fill-color": "#e8edf3"},
    "landcover_glacier":     {"fill-color": "#dfe7ee"},
    "landuse_residential":   {"fill-color": "#f2ebdf"},
    "landcover_wood":        {"fill-color": "#cddec9"},
    "landuse_park":          {"fill-color": "#cddec9"},
    "waterway":              {"line-color": "#9dbed6"},
    "water_name":            {"text-color": "#165e83"},
    "building":              {"fill-color": "#e7decf",
                              "fill-outline-color": "#d5c9b4"},
    "aeroway-taxiway":       {"line-color": "#d5c9b4"},
    "aeroway-runway-casing": {"line-color": "#c4b69e"},
    "aeroway-area":          {"fill-color": "#f2ebdf"},
    "aeroway-runway":        {"line-color": "#e2d9c8"},
    "road_area_pier":        {"fill-color": "#f2ebdf"},
    "road_pier":             {"line-color": "#d8cfbf"},
    "highway_path":          {"line-color": "#dcd2bf"},
    "highway_minor":         {"line-color": "#ffffff"},
    "highway_major_casing":  {"line-color": "#d8cfbf"},
    "highway_major_inner":   {"line-color": "#ffffff"},
    "highway_major_subtle":  {"line-color": "#e9e2d2"},
    "highway_motorway_casing": {"line-color": "#efb287"},
    "highway_motorway_inner":  {"line-color": "#f9cfb2"},
    "highway_motorway_subtle": {"line-color": "#f5dec6"},
    "railway_transit":         {"line-color": "#a79b8a"},
    "railway_transit_dashline": {"line-color": "#faf7f2"},
    "railway_minor":           {"line-color": "#a79b8a"},
    "railway_minor_dashline":  {"line-color": "#faf7f2"},
    "railway":                 {"line-color": "#a79b8a"},
    "railway_dashline":        {"line-color": "#faf7f2"},
    "highway_name_other":    {"text-color": "#4a463f"},
    "highway_name_motorway": {"text-color": "#4a463f"},
    "boundary_state":        {"line-color": "rgba(90,80,70,0.30)"},
    "boundary_country_z0-4": {"line-color": "rgba(90,80,70,0.38)"},
    "boundary_country_z5-":  {"line-color": "rgba(90,80,70,0.38)"},
    "place_other":           {"text-color": "#6f6a63"},
    "place_suburb":          {"text-color": "#6f6a63"},
    "place_village":         {"text-color": "#6f6a63"},
    "place_town":            {"text-color": "#4a463f"},
    "place_city":            {"text-color": "#2e2b26"},
    "place_city_large":      {"text-color": "#2e2b26"},
    "place_state":           {"text-color": "#9a938c"},
    "place_country_other":   {"text-color": "#6f6a63"},
    "place_country_minor":   {"text-color": "#6f6a63"},
    "place_country_major":   {"text-color": "#4a463f"},
}

# Generic rules applied after the per-layer map: the night halo color
# (#070912, the night bg) becomes a white halo on every symbol layer;
# water_name's slightly different halo target is handled here too.
HALO_NIGHT = "#070912"
HALO_DAY = "#faf7f2"
WATER_HALO_DAY = "#edf3f7"


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
