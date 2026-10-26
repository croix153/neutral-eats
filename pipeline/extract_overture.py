#!/usr/bin/env python3
"""
Neutral Eats — Overture Maps food-venue extraction pipeline (Phase 2).

WHAT THIS DOES
--------------
Extracts food & drink venues from the Overture Maps Places dataset (public
Parquet on S3, no API key, no quota) for a bounding box, transforms them to
the Neutral Eats `venues` shape, and loads them into a MySQL *staging* table
(`venues_overture_staging`) in the production database. It also flags which
staging rows match an existing production venue (same normalized name within
50 m — the project's long-standing dedupe rule) and prints a coverage report.

It NEVER writes to the production `venues` table. Merging staging into
production is a separate, reviewed step.

DATA / NEUTRALITY
-----------------
Source: Overture Maps release (theme=places, type=place). Filter: taxonomy
hierarchy contains 'food_and_drink', minus retail categories whose primary
business is not prepared food (supermarket, grocery_store, convenience_store,
liquor_store), minus operating_status='permanently_closed'. Ranking inputs
are never touched — this is a coverage pipeline only. Overture carries no
ratings, which suits the no-sponsored-ranking product rule.

CREDENTIALS
-----------
This script contains no credentials. DDL and stats run through small PHP
helpers (generated at runtime, deleted after) that `require` the live site
config (/var/www/html/minerva/config/database.php) on the host, so the app
DB credentials never leave PHP. The bulk TSV load runs as the host's MySQL
root over the local socket using server-side LOAD DATA INFILE from the
secure_file_priv directory — the app user has no SUPER and local_infile is
off, and this path mutates no server globals.

USAGE
-----
    python3 extract_overture.py                     # Florida gate (default)
    python3 extract_overture.py --release 2026-10-21.0
    python3 extract_overture.py --bbox 25.0,31.5,-88.0,-79.5 --table venues_overture_staging
    python3 extract_overture.py --reuse-raw         # skip S3 scan if raw parquet exists
    python3 extract_overture.py --skip-mysql        # extract + transform only

Requires: duckdb CLI (DUCKDB_BIN env or /root/overture-work/duckdb or PATH),
php CLI on the host, network access to the Overture S3 bucket.
Host notes: built for the small croix.ai Linode (2 cores / 4 GB): DuckDB runs
with memory_limit=2500MB, threads=2, and the bbox predicate is applied to the
parquet `bbox` column so S3 row groups outside the box are pruned.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

S3_BUCKET = "overturemaps-us-west-2"
S3_LIST_URL = (
    "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/"
    "?list-type=2&prefix=release/&delimiter=/"
)
DEFAULT_WORKDIR = "/root/overture-work"
DEFAULT_PHP_CONFIG = "/var/www/html/minerva/config/database.php"
DEFAULT_TABLE = "venues_overture_staging"

# Florida gate bbox: lat 24.4-31.1, lng -87.7..-79.9
BBOX_PRESETS = {
    "florida": (24.4, 31.1, -87.7, -79.9),
}

# Overture categories whose primary business is retail, not prepared food.
EXCLUDED_CATEGORIES = ("supermarket", "grocery_store", "convenience_store", "liquor_store")

# Overture taxonomy.primary -> Neutral Eats venues.type
TYPE_MAP_SQL = """
CASE
  WHEN taxonomy.primary IN ('restaurant','american_restaurant','asian_restaurant',
    'barbecue_restaurant','brazilian_restaurant','breakfast_restaurant','chinese_restaurant',
    'french_restaurant','greek_restaurant','indian_restaurant','italian_restaurant',
    'japanese_restaurant','korean_restaurant','mediterranean_restaurant','mexican_restaurant',
    'middle_eastern_restaurant','pizza_restaurant','seafood_restaurant','spanish_restaurant',
    'steak_house','sushi_restaurant','thai_restaurant','vietnamese_restaurant',
    'other_restaurant') THEN 'restaurant'
  WHEN taxonomy.primary IN ('cafe','coffee_shop','tea_house','cat_cafe','internet_cafe') THEN 'cafe'
  WHEN taxonomy.primary IN ('bar','pub','wine_bar','cocktail_bar','sports_bar','beer_bar',
    'dive_bar','karaoke_bar') THEN 'bar'
  WHEN taxonomy.primary = 'bakery' THEN 'bakery'
  WHEN taxonomy.primary IN ('fast_food_restaurant','food_truck','food_court','sandwich_shop',
    'bagel_shop','donut_shop','hot_dog_restaurant','taco_restaurant','burger_restaurant',
    'chicken_restaurant','ice_cream_shop','frozen_yogurt_shop','juice_shop','smoothie_shop',
    'dessert_shop','deli','butcher_shop','candy_store','chocolate_shop','pretzel_shop',
    'snack_bar','meal_delivery','food_stall') THEN 'fast_food'
  ELSE 'restaurant'
END
"""


def find_duckdb():
    for cand in (os.environ.get("DUCKDB_BIN"), "/root/overture-work/duckdb", "duckdb"):
        if cand and (os.path.sep in cand and os.path.exists(cand) or cand == "duckdb"):
            return cand
    sys.exit("duckdb binary not found (set DUCKDB_BIN)")


def latest_release():
    with urllib.request.urlopen(S3_LIST_URL, timeout=30) as resp:
        xml = resp.read().decode()
    releases = sorted(re.findall(r"<Prefix>release/([0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]+)/</Prefix>", xml))
    if not releases:
        sys.exit("could not list Overture releases")
    return releases[-1]


def run_duckdb(duckdb, sql, workdir):
    proc = subprocess.run([duckdb, "-list", "-noheader"], input=sql,
                          capture_output=True, text=True, cwd=workdir)
    if proc.returncode != 0:
        sys.exit(f"duckdb failed:\n{proc.stderr[-2000:]}")
    return proc.stdout.strip()


def main():
    ap = argparse.ArgumentParser(description="Neutral Eats Overture extraction (staging only)")
    ap.add_argument("--release", help="Overture release, e.g. 2026-10-21.0 (default: latest)")
    ap.add_argument("--bbox", help="min_lat,max_lat,min_lng,max_lng (default: florida preset)")
    ap.add_argument("--preset", default="florida", choices=list(BBOX_PRESETS))
    ap.add_argument("--table", default=DEFAULT_TABLE)
    ap.add_argument("--workdir", default=DEFAULT_WORKDIR)
    ap.add_argument("--php-config", default=DEFAULT_PHP_CONFIG)
    ap.add_argument("--reuse-raw", action="store_true", help="reuse existing raw parquet in workdir")
    ap.add_argument("--skip-mysql", action="store_true")
    ap.add_argument("--nationwide", action="store_true",
                    help="nationwide mode: integrity counts, one US capture, per-state staging loads")
    ap.add_argument("--reuse-counts", action="store_true",
                    help="nationwide: reuse existing per-file integrity counts")
    args = ap.parse_args()

    if args.nationwide:
        if args.table == DEFAULT_TABLE:
            args.table = "venues_overture_staging_us"
        run_nationwide(args)
        return

    if not re.fullmatch(r"[a-z0-9_]+", args.table):
        sys.exit("invalid table name")
    if args.bbox:
        min_lat, max_lat, min_lng, max_lng = (float(x) for x in args.bbox.split(","))
    else:
        min_lat, max_lat, min_lng, max_lng = BBOX_PRESETS[args.preset]

    release = args.release or latest_release()
    duckdb = find_duckdb()
    os.makedirs(args.workdir, exist_ok=True)
    s3_glob = f"s3://{S3_BUCKET}/release/{release}/theme=places/type=place/*.parquet"
    print(f"[extract] release={release} bbox=({min_lat},{min_lng})-({max_lat},{max_lng})")

    raw = os.path.join(args.workdir, "fl_bbox_raw.parquet")
    if not (args.reuse_raw and os.path.exists(raw)):
        sql = f"""
LOAD httpfs; LOAD spatial;
SET memory_limit='2500MB'; SET threads=2;
COPY (
  SELECT id, geometry, bbox, names, taxonomy, basic_category, operating_status,
         addresses, phones, websites,
 brand, confidence, sources
  FROM read_parquet('{s3_glob}')
  WHERE bbox.xmax >= {min_lng} AND bbox.xmin <= {max_lng}
    AND bbox.ymax >= {min_lat} AND bbox.ymin <= {max_lat}
) TO 'fl_bbox_raw.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
SELECT count(*) FROM read_parquet('fl_bbox_raw.parquet');
"""
        n = run_duckdb(duckdb, sql, args.workdir)
        print(f"[extract] raw bbox rows captured: {n}")
    else:
        print("[extract] reusing existing raw parquet")

    excluded = ",".join(f"'{c}'" for c in EXCLUDED_CATEGORIES)
    tsv = os.path.join(args.workdir, "fl_food.tsv")
    # Schema notes for Overture 2026 releases (verified empirically):
    # - addresses is a LIST of structs -> use addresses[1].
    # - addresses.region may be 'FL' or 'US-FL' -> strip an optional 'US-'.
    # - a few geometries are empty WKB (type 0) -> TRY_CAST yields NULL there;
    #   fall back to the bbox center (identical to the point for point places).
    transform_sql = f"""
LOAD spatial;
SET memory_limit='2500MB'; SET threads=2; SET temp_directory='duckdb_tmp';
CREATE OR REPLACE TEMPORARY MACRO clean(x) AS
  replace(replace(replace(replace(x, chr(9), ' '), chr(10), ' '), chr(13), ' '), chr(92), ' ');
COPY (
  WITH base AS (
    SELECT * FROM read_parquet('fl_bbox_raw.parquet')
    WHERE addresses[1].country IN ('US','PR','GU','VI','AS','MP') OR addresses[1].country IS NULL
  ), pt AS (
    SELECT *,
      coalesce(ST_X(TRY_CAST(geometry AS GEOMETRY)), (bbox.xmin + bbox.xmax) / 2) AS lng,
      coalesce(ST_Y(TRY_CAST(geometry AS GEOMETRY)), (bbox.ymin + bbox.ymax) / 2) AS lat,
      addresses[1] AS addr
    FROM base
  ), food AS (
    SELECT * FROM pt
    WHERE lat BETWEEN {min_lat} AND {max_lat} AND lng BETWEEN {min_lng} AND {max_lng}
      AND list_contains(taxonomy.hierarchy, 'food_and_drink')
      AND coalesce(taxonomy.primary, basic_category) NOT IN ({excluded})
      AND (operating_status IS NULL OR operating_status <> 'permanently_closed')
      AND names.primary IS NOT NULL AND names.primary <> ''
  )
  SELECT
    'overture:' || id,
    clean(substr(names.primary, 1, 500)),
    round(lat, 8), round(lng, 8),
    {TYPE_MAP_SQL},
    clean(NULLIF(substr(coalesce(array_to_string(list_filter(taxonomy.alternates,
      a -> a NOT IN ('eat_and_drink','food_and_drink','restaurant','cafe','bar')), ' + '), ''), 1, 200), '')),
    clean(substr(coalesce(nullif(brand.names.primary, ''), ''), 1, 200)),
    'overture',
    id,
    clean(substr(coalesce(addr.freeform, ''), 1, 500)),
    clean(substr(coalesce(addr.locality, ''), 1, 200)),
    clean(substr(regexp_replace(coalesce(addr.region, ''), '^US-', ''), 1, 100)),
    clean(substr(coalesce(addr.postcode, ''), 1, 20)),
    clean(substr(coalesce(phones[1], ''), 1, 50)),
    clean(substr(coalesce(websites[1], ''), 1, 500)),
    round(coalesce(confidence, 0.5), 2),
    clean(substr(coalesce(taxonomy.primary, basic_category, ''), 1, 200)),
    clean(regexp_replace(lower(trim(names.primary)), '[^a-z0-9 ]', '', 'g'))
  FROM food
) TO 'fl_food.tsv' (HEADER false, DELIM '\\t', QUOTE '');
"""
    run_duckdb(duckdb, transform_sql, args.workdir)
    print(f"[transform] TSV written: {tsv}")

    if args.skip_mysql:
        print("[done] --skip-mysql: staging load skipped")
        return

    def run_php(name, code, argv):
        path = os.path.join(args.workdir, name)
        with open(path, "w") as fh:
            fh.write(code)
        try:
            proc = subprocess.run(["php", path] + argv, capture_output=True, text=True)
            sys.stdout.write(proc.stdout)
            if proc.returncode != 0:
                sys.exit(f"{name} failed:\n{proc.stderr[-2000:]}")
        finally:
            os.unlink(path)

    bbox_args = [str(min_lat), str(max_lat), str(min_lng), str(max_lng)]
    # 1) DDL as the app user (its grant covers the neutraleats schema).
    run_php("_ddl.php", PHP_DDL, [args.php_config, args.table])
    # 2) Bulk load as root over the local socket, server-side INFILE
    #    (secure_file_priv dir), so no local_infile / SUPER is needed.
    priv = subprocess.run(["mysql", "-u", "root", "-N", "-e",
                           "SELECT @@GLOBAL.secure_file_priv"],
                          capture_output=True, text=True).stdout.strip()
    if not priv:
        sys.exit("secure_file_priv is empty/disabled; cannot stage the TSV for LOAD DATA INFILE")
    staged_tsv = os.path.join(priv, os.path.basename(tsv))
    subprocess.run(["cp", tsv, staged_tsv], check=True)
    subprocess.run(["chown", "mysql:mysql", staged_tsv], check=True)
    cols = ("id,name,lat,lng,type,cuisine,brand,source,source_id,address,city,state,"
            "zip,phone,website,confidence_score,category_primary,norm_name")
    load_sql = (f"LOAD DATA INFILE '{staged_tsv}' INTO TABLE `{args.table}` "
                f"CHARACTER SET utf8mb4 FIELDS TERMINATED BY '\\t' "
                f"LINES TERMINATED BY '\\n' ({cols}); "
                f"SELECT ROW_COUNT();")
    proc = subprocess.run(["mysql", "-u", "root", "-N", "neutraleats", "-e", load_sql],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"mysql load failed:\n{proc.stderr[-2000:]}")
    print(f"[load] rows loaded into {args.table}: {proc.stdout.strip()}")
    os.unlink(staged_tsv)
    # 3) Dedupe flag + summary stats as the app user.
    run_php("_stats.php", PHP_STATS, [args.php_config, args.table] + bbox_args)
    print("[done] staging load + dedupe report complete")


# PHP helpers: require the live site config (credentials stay inside PHP).
# PHP_DDL (re)creates the staging table mirroring `venues`; the bulk load
# itself runs as root (server-side LOAD DATA INFILE from secure_file_priv),
# because the app user has no SUPER and local_infile is off.
# PHP_STATS flags production matches (normalized name + haversine <= 50 m)
# and prints JSON summary counts.
PHP_DDL = r"""<?php
[$_s, $cfg, $table] = $argv;
require_once $cfg;
$pdo = getDatabaseConnection();
$pdo->exec("DROP TABLE IF EXISTS `$table`");
$pdo->exec("CREATE TABLE `$table` (
  id varchar(255) NOT NULL, name varchar(500) NOT NULL,
  lat decimal(10,8) NOT NULL, lng decimal(11,8) NOT NULL,
  type varchar(100) NOT NULL, cuisine varchar(200) DEFAULT NULL,
  brand varchar(200) DEFAULT NULL, source varchar(50) NOT NULL,
  source_id varchar(255) DEFAULT NULL, address varchar(500) DEFAULT NULL,
  city varchar(200) DEFAULT NULL, state varchar(100) DEFAULT NULL,
  zip varchar(20) DEFAULT NULL, phone varchar(50) DEFAULT NULL,
  website varchar(500) DEFAULT NULL, confidence_score decimal(3,2) DEFAULT 0.50,
  category_primary varchar(200) DEFAULT NULL, norm_name varchar(500) DEFAULT NULL,
  matched_prod tinyint NOT NULL DEFAULT 0,
  PRIMARY KEY (id), KEY idx_lat (lat), KEY idx_lng (lng),
  KEY idx_norm (norm_name), KEY idx_matched (matched_prod)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
echo "staging table ready\n";
"""

PHP_STATS = r"""<?php
[$_s, $cfg, $table, $minLat, $maxLat, $minLng, $maxLng] = $argv;
require_once $cfg;
$pdo = getDatabaseConnection();
$hav = "6371000 * 2 * ASIN(SQRT(POW(SIN(RADIANS(%s - %s)/2),2) + COS(RADIANS(%s)) * COS(RADIANS(%s)) * POW(SIN(RADIANS(%s - %s)/2),2)))";
$band = 0.0006; // ~66 m lat band prefilter
$pdo->exec("CREATE TEMPORARY TABLE prod_norm AS
  SELECT id, REGEXP_REPLACE(LOWER(TRIM(name)), '[^a-z0-9 ]', '') AS nn, lat, lng
  FROM venues WHERE lat BETWEEN $minLat AND $maxLat AND lng BETWEEN $minLng AND $maxLng");
$pdo->exec("UPDATE `$table` s SET s.matched_prod = 1 WHERE EXISTS (
  SELECT 1 FROM prod_norm p WHERE p.nn = s.norm_name
    AND s.lat BETWEEN p.lat - $band AND p.lat + $band
    AND s.lng BETWEEN p.lng - $band AND p.lng + $band
    AND " . sprintf($hav, 's.lat','p.lat','p.lat','s.lat','s.lng','p.lng') . " <= 50)");
function c($pdo, $sql) { return (int)$pdo->query($sql)->fetchColumn(); }
$out = [
  'staging_total'   => c($pdo, "SELECT COUNT(*) FROM `$table`"),
  'staging_matched' => c($pdo, "SELECT COUNT(*) FROM `$table` WHERE matched_prod = 1"),
  'prod_in_bbox'    => c($pdo, "SELECT COUNT(*) FROM venues WHERE lat BETWEEN $minLat AND $maxLat AND lng BETWEEN $minLng AND $maxLng"),
];
$out['staging_net_new'] = $out['staging_total'] - $out['staging_matched'];
echo json_encode($out, JSON_PRETTY_PRINT), "\n";
"""


# ------------------------------------------------------- nationwide mode ---
# State bboxes (min_lat, max_lat, min_lng, max_lng) used ONLY to assign a
# state to rows whose Overture address region is missing/invalid; a valid
# region always wins. Alaska gets a second box for the Aleutian chain east
# of the antimeridian.
STATE_BBOXES = {
    "AL": [(30.2, 35.0, -88.5, -84.9)],
    "AK": [(51.0, 71.5, -168.0, -129.9), (51.0, 65.0, 172.0, 180.0)],
    "AZ": [(31.3, 37.1, -114.8, -109.0)],
    "AR": [(33.0, 36.5, -94.6, -89.6)],
    "CA": [(32.5, 42.0, -124.4, -114.1)],
    "CO": [(37.0, 41.0, -109.1, -102.0)],
    "CT": [(40.9, 42.1, -73.8, -71.8)],
    "DE": [(38.4, 39.9, -75.8, -75.0)],
    "DC": [(38.8, 39.0, -77.1, -76.9)],
    "FL": [(24.4, 31.1, -87.7, -79.9)],
    "GA": [(30.4, 35.0, -85.6, -80.8)],
    "HI": [(18.8, 22.3, -161.1, -154.7)],
    "ID": [(42.0, 49.0, -117.2, -111.0)],
    "IL": [(37.0, 42.5, -91.5, -87.5)],
    "IN": [(37.8, 41.8, -88.1, -84.8)],
    "IA": [(40.4, 43.5, -96.5, -91.1)],
    "KS": [(37.0, 40.0, -102.1, -94.6)],
    "KY": [(36.5, 39.1, -89.6, -82.6)],
    "LA": [(28.9, 33.0, -94.1, -88.9)],
    "ME": [(43.0, 47.5, -71.1, -66.9)],
    "MD": [(37.9, 39.7, -79.5, -75.0)],
    "MA": [(41.2, 42.9, -73.5, -69.9)],
    "MI": [(41.7, 47.5, -90.4, -82.4)],
    "MN": [(43.5, 49.4, -97.2, -89.5)],
    "MS": [(30.2, 35.0, -91.7, -88.1)],
    "MO": [(36.0, 40.6, -95.8, -89.1)],
    "MT": [(44.4, 49.0, -116.1, -104.0)],
    "NE": [(40.0, 43.0, -104.1, -95.3)],
    "NV": [(35.0, 42.0, -120.0, -114.0)],
    "NH": [(42.7, 45.3, -72.6, -70.7)],
    "NJ": [(38.9, 41.4, -75.6, -73.9)],
    "NM": [(31.3, 37.0, -109.1, -103.0)],
    "NY": [(40.5, 45.0, -79.8, -71.9)],
    "NC": [(33.8, 36.6, -84.3, -75.4)],
    "ND": [(45.9, 49.0, -104.1, -97.0)],
    "OH": [(38.4, 42.3, -84.8, -80.5)],
    "OK": [(33.6, 37.0, -103.0, -94.4)],
    "OR": [(42.0, 46.3, -124.6, -116.5)],
    "PA": [(39.7, 42.3, -80.5, -74.7)],
    "RI": [(41.3, 42.0, -71.9, -71.1)],
    "SC": [(32.0, 35.2, -83.4, -78.5)],
    "SD": [(42.5, 45.9, -104.1, -96.4)],
    "TN": [(35.0, 36.7, -90.3, -81.6)],
    "TX": [(25.8, 36.5, -106.6, -93.5)],
    "UT": [(37.0, 42.0, -114.1, -109.0)],
    "VT": [(42.7, 45.0, -73.4, -71.5)],
    "VA": [(36.5, 39.5, -83.7, -75.2)],
    "WA": [(45.9, 49.0, -124.7, -117.0)],
    "WV": [(37.2, 40.6, -82.6, -77.7)],
    "WI": [(42.5, 46.9, -92.9, -86.8)],
    "WY": [(41.0, 45.0, -111.1, -104.0)],
    "PR": [(17.9, 18.5, -67.3, -65.6)],
    "VI": [(17.6, 18.4, -65.1, -64.6)],
    "GU": [(13.2, 13.7, 144.6, 145.0)],
    "MP": [(14.0, 16.1, 145.2, 146.1)],
    "AS": [(-14.6, -14.0, -171.1, -168.9)],
}
# Capture boxes (bbox-column overlap) whose union covers the US + territories.
US_CAPTURE_BOXES = [
    (-125.0, -66.0, 24.0, 49.5), (-180.0, -129.9, 51.0, 71.5),
    (172.0, 180.0, 51.0, 65.0), (-161.5, -154.5, 18.0, 23.5),
    (-67.4, -65.4, 17.5, 18.7), (-65.2, -64.5, 17.5, 18.5),
    (144.5, 145.1, 13.1, 13.8), (145.5, 146.1, 15.0, 16.2),
    (-171.0, -169.4, -14.6, -14.0),
]


def _capture_where():
    return " OR ".join(
        f"(bbox.xmax >= {a} AND bbox.xmin <= {b} AND bbox.ymax >= {c} AND bbox.ymin <= {d})"
        for a, b, c, d in US_CAPTURE_BOXES)


def run_nationwide(args):
    """Nationwide extraction: integrity counts -> one US capture -> transform
    with state assignment -> per-state staging loads with reconciliation.

    Writes into <workdir>/gate2 by default. Re-runnable: --reuse-raw skips the
    S3 capture when us_raw.parquet already exists, --reuse-counts skips the
    per-file integrity recount."""
    import collections

    duckdb = find_duckdb()
    wd = os.path.join(args.workdir, "gate2")
    os.makedirs(wd, exist_ok=True)
    release = args.release or latest_release()
    glob = f"s3://{S3_BUCKET}/release/{release}/theme=places/type=place/*.parquet"
    print(f"[us] release={release} workdir={wd}")

    # 1) Integrity + local mirror. NOTE: DuckDB's httpfs reads S3 in a slow
    #    serialized way (~0.5 MB/s observed on this host vs ~90 MB/s for
    #    parallel curl), so the release is mirrored to local disk first with
    #    parallel downloads; every later step reads the local glob. Byte
    #    sizes are verified against the S3 listing, then rows are counted
    #    per file and asserted against the mirror.
    import xml.etree.ElementTree as ET
    list_url = (f"https://{S3_BUCKET}.s3.us-west-2.amazonaws.com/"
                f"?list-type=2&prefix=release/{release}/theme=places/type=place/")
    with urllib.request.urlopen(list_url, timeout=30) as resp:
        xml_bytes = resp.read()
    ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
    root_el = ET.fromstring(xml_bytes)
    listing = [(c.find("s:Key", ns).text, int(c.find("s:Size", ns).text))
               for c in root_el.findall("s:Contents", ns)]
    assert listing, "no files in release glob"
    s3dir = os.path.join(wd, "s3")
    os.makedirs(s3dir, exist_ok=True)
    missing = [(k, s) for k, s in listing
               if not os.path.exists(os.path.join(s3dir, os.path.basename(k)))
               or os.path.getsize(os.path.join(s3dir, os.path.basename(k))) != s]
    if missing:
        urls_path = os.path.join(wd, "urls.txt")
        with open(urls_path, "w") as fh:
            for k, _s in missing:
                fh.write(f"https://{S3_BUCKET}.s3.us-west-2.amazonaws.com/{k}\n")
        dl = subprocess.run(
            f"cat {urls_path} | xargs -P 8 -I{{}} sh -c 'f={s3dir}/$(basename {{}}); "
            f"curl -fSL --retry 3 --retry-delay 2 -o $f.tmp {{}} && mv $f.tmp $f'",
            shell=True, capture_output=True, text=True)
        if dl.returncode != 0:
            sys.exit(f"mirror download failed:\n{dl.stderr[-1500:]}")
    for k, s in listing:
        p = os.path.join(s3dir, os.path.basename(k))
        assert os.path.getsize(p) == s, f"size mismatch for {k}"
    print(f"[us] mirror verified: {len(listing)} files, "
          f"{sum(s for _k, s in listing) / 1073741824:.2f} GiB")
    local_glob = os.path.join(s3dir, "*.parquet")
    counts_path = os.path.join(wd, "file_counts.tsv")
    if args.reuse_counts and os.path.exists(counts_path):
        total_release = sum(int(l.split("\t")[1]) for l in open(counts_path) if "\t" in l)
        print(f"[us] reusing per-file counts: {len(listing)} files, {total_release} rows total")
    else:
        total_release = 0
        with open(counts_path, "w") as out:
            for k, _s in listing:
                p = os.path.join(s3dir, os.path.basename(k))
                n = run_duckdb(duckdb, f"SELECT count(*) FROM read_parquet('{p}');", wd)
                total_release += int(n)
                out.write(f"{os.path.basename(k)}\t{n}\n")
        print(f"[us] integrity: {len(listing)} files, {total_release} rows total")

    # 2) Capture: one pass over the local glob with the US bbox union;
    #    recount with an independent query and assert equality.
    raw = os.path.join(wd, "us_raw.parquet")
    if not (args.reuse_raw and os.path.exists(raw)):
        sql = f"""
LOAD spatial;
SET memory_limit='2500MB'; SET threads=2;
COPY (SELECT id, geometry, bbox, names, taxonomy, basic_category, operating_status,
       addresses, phones, websites, brand, confidence, sources
  FROM read_parquet('{local_glob}') WHERE {_capture_where()}) TO 'us_raw.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
SELECT count(*) FROM read_parquet('us_raw.parquet');
"""
        n = run_duckdb(duckdb, sql, wd)
        print(f"[us] captured rows: {n}")
    else:
        n = run_duckdb(duckdb, "SELECT count(*) FROM read_parquet('us_raw.parquet');", wd)
        print(f"[us] reusing raw capture: {n} rows")
    recount = run_duckdb(duckdb, f"SET memory_limit='2500MB'; SET threads=2; "
                                 f"SELECT count(*) FROM read_parquet('{local_glob}') WHERE {_capture_where()};", wd)
    assert int(recount) == int(n), f"capture mismatch: parquet={n} recount={recount}"
    print(f"[us] capture reconciled: {n} == {recount}")

    # 3) Transform with state assignment + funnel accounting.
    codes = ",".join(f"'{c}'" for c in sorted(STATE_BBOXES))
    states_values = ",".join(
        f"('{code}', {b[0]}, {b[1]}, {b[2]}, {b[3]})"
        for code, boxes in sorted(STATE_BBOXES.items()) for b in boxes)
    excluded = ",".join(f"'{c}'" for c in EXCLUDED_CATEGORIES)
    # Funnel counts as independent column-pruned scans. Do NOT materialize
    # temp tables of the raw rows here: an unbounded DuckDB temp table of
    # ~20M wide rows gets OOM-killed on this host (observed in Gate 2).
    setts = f"SET memory_limit='2500MB'; SET threads=2; SET temp_directory='{wd}/duckdb_tmp';"
    funnel = {}
    funnel["raw"] = int(run_duckdb(
        duckdb, f"{setts} SELECT count(*) FROM read_parquet('us_raw.parquet');", wd))
    funnel["country_pass"] = int(run_duckdb(
        duckdb, f"{setts} SELECT count(*) FROM read_parquet('us_raw.parquet') "
                f"WHERE addresses[1].country IN ('US','PR','GU','VI','AS','MP') OR addresses[1].country IS NULL;", wd))
    funnel["food_open_named"] = int(run_duckdb(
        duckdb, f"{setts} SELECT count(*) FROM read_parquet('us_raw.parquet') "
                f"WHERE (addresses[1].country IN ('US','PR','GU','VI','AS','MP') OR addresses[1].country IS NULL) "
                f"AND list_contains(taxonomy.hierarchy, 'food_and_drink') "
                f"AND coalesce(taxonomy.primary, basic_category) NOT IN ({excluded}) "
                f"AND (operating_status IS NULL OR operating_status <> 'permanently_closed') "
                f"AND names.primary IS NOT NULL AND names.primary <> '';", wd))
    print(f"[us] funnel (pre-assignment): {funnel}")

    transform_sql = f"""
LOAD spatial;
SET memory_limit='2500MB'; SET threads=2; SET temp_directory='{wd}/duckdb_tmp';
CREATE OR REPLACE TEMPORARY MACRO clean(x) AS
  replace(replace(replace(replace(x, chr(9), ' '), chr(10), ' '), chr(13), ' '), chr(92), ' ');
CREATE TEMP TABLE states(code VARCHAR, min_lat DOUBLE, max_lat DOUBLE, min_lng DOUBLE, max_lng DOUBLE);
INSERT INTO states VALUES {states_values};
COPY (
  WITH base AS (
    SELECT * FROM read_parquet('us_raw.parquet')
    WHERE addresses[1].country IN ('US','PR','GU','VI','AS','MP') OR addresses[1].country IS NULL
  ), pt AS (
    SELECT *,
      coalesce(ST_X(TRY_CAST(geometry AS GEOMETRY)), (bbox.xmin + bbox.xmax) / 2) AS lng,
      coalesce(ST_Y(TRY_CAST(geometry AS GEOMETRY)), (bbox.ymin + bbox.ymax) / 2) AS lat,
      addresses[1] AS addr FROM base
  ), food AS (
    SELECT * FROM pt
    WHERE list_contains(taxonomy.hierarchy, 'food_and_drink')
      AND coalesce(taxonomy.primary, basic_category) NOT IN ({excluded})
      AND (operating_status IS NULL OR operating_status <> 'permanently_closed')
      AND names.primary IS NOT NULL AND names.primary <> ''
  ), cand AS (
    SELECT f.*, s.code AS bbox_state,
      (s.max_lat - s.min_lat) * (s.max_lng - s.min_lng) AS area
    FROM food f LEFT JOIN states s
      ON f.lat BETWEEN s.min_lat AND s.max_lat AND f.lng BETWEEN s.min_lng AND s.max_lng
  ), picked AS (
    SELECT * FROM cand QUALIFY row_number() OVER (PARTITION BY id ORDER BY area NULLS LAST) = 1
  ), assigned AS (
    SELECT *,
      CASE WHEN regexp_replace(coalesce(addr.region, ''), '^US-', '') IN ({codes})
           THEN regexp_replace(coalesce(addr.region, ''), '^US-', '')
           ELSE bbox_state END AS batch_state
    FROM picked
  )
  SELECT
    'overture:' || id,
    clean(substr(names.primary, 1, 500)),
    round(lat, 8), round(lng, 8),
    {TYPE_MAP_SQL},
    clean(NULLIF(substr(coalesce(array_to_string(list_filter(taxonomy.alternates,
      a -> a NOT IN ('eat_and_drink','food_and_drink','restaurant','cafe','bar')), ' + '), ''), 1, 200), '')),
    clean(substr(coalesce(nullif(brand.names.primary, ''), ''), 1, 200)),
    'overture',
    id,
    clean(substr(coalesce(addr.freeform, ''), 1, 500)),
    clean(substr(coalesce(addr.locality, ''), 1, 200)),
    clean(substr(regexp_replace(coalesce(addr.region, ''), '^US-', ''), 1, 100)),
    clean(substr(regexp_replace(coalesce(addr.postcode, ''), '[^0-9A-Za-z\\- ]', '', 'g'), 1, 20)),
    clean(substr(coalesce(phones[1], ''), 1, 50)),
    clean(substr(coalesce(websites[1], ''), 1, 500)),
    round(coalesce(confidence, 0.5), 2),
    clean(substr(coalesce(taxonomy.primary, basic_category, ''), 1, 200)),
    clean(regexp_replace(lower(trim(names.primary)), '[^a-z0-9 ]', '', 'g')),
    batch_state
  FROM assigned WHERE batch_state IS NOT NULL
  ORDER BY 18, 3, 4
) TO 'us_food.tsv' (HEADER false, DELIM '\\t', QUOTE '');
"""
    run_duckdb(duckdb, transform_sql, wd)
    state_counts = run_duckdb(
        duckdb,
        "SELECT batch_state, count(*) FROM read_csv('us_food.tsv', header=false, sep='\t', "
        "columns={'c1':'VARCHAR','c2':'VARCHAR','c3':'DOUBLE','c4':'DOUBLE','c5':'VARCHAR','c6':'VARCHAR',"
        "'c7':'VARCHAR','c8':'VARCHAR','c9':'VARCHAR','c10':'VARCHAR','c11':'VARCHAR','c12':'VARCHAR',"
        "'c13':'VARCHAR','c14':'VARCHAR','c15':'VARCHAR','c16':'DOUBLE','c17':'VARCHAR','c18':'VARCHAR',"
        "'batch_state':'VARCHAR'}) GROUP BY batch_state ORDER BY batch_state;", wd)
    expected = {}
    for line in state_counts.splitlines():
        parts = line.split("|") if "|" in line else line.split("\t")
        if len(parts) == 2:
            expected[parts[0].strip()] = int(parts[1])
    total_food = sum(expected.values())
    print(f"[us] assigned food venues: {total_food} across {len(expected)} states/territories")
    unassigned = funnel.get("food_open_named", 0) - total_food
    print(f"[us] funnel: raw={funnel.get('raw')} country_pass={funnel.get('country_pass')} "
          f"food={funnel.get('food_open_named')} assigned={total_food} unassigned_dropped={unassigned}")

    if args.skip_mysql:
        print("[done] --skip-mysql: nationwide staging load skipped")
        return

    # 4) Per-state loads into the staging table, reconciled against the
    #    transform counts above.
    def run_php(name, code, argv):
        path = os.path.join(wd, name)
        with open(path, "w") as fh:
            fh.write(code)
        try:
            proc = subprocess.run(["php", path] + argv, capture_output=True, text=True)
            sys.stdout.write(proc.stdout)
            if proc.returncode != 0:
                sys.exit(f"{name} failed:\n{proc.stderr[-2000:]}")
        finally:
            os.unlink(path)

    run_php("_ddl_us.php", PHP_DDL_US, [args.php_config, args.table])
    priv = subprocess.run(["mysql", "-u", "root", "-N", "-e", "SELECT @@GLOBAL.secure_file_priv"],
                          capture_output=True, text=True).stdout.strip()
    if not priv:
        sys.exit("secure_file_priv is empty/disabled; cannot stage TSVs")
    by_state = collections.defaultdict(list)
    with open(os.path.join(wd, "us_food.tsv"), encoding="utf-8") as fh:
        for line in fh:
            by_state[line.rstrip("\n").split("\t")[-1]].append(line)
    cols = ("id,name,lat,lng,type,cuisine,brand,source,source_id,address,city,state,"
            "zip,phone,website,confidence_score,category_primary,norm_name,batch_state")
    loaded_total = 0
    for state in sorted(by_state):
        rows = by_state[state]
        part = os.path.join(wd, f"state_{state}.tsv")
        with open(part, "w", encoding="utf-8") as out:
            out.writelines(rows)
        staged = os.path.join(priv, os.path.basename(part))
        subprocess.run(["cp", part, staged], check=True)
        subprocess.run(["chown", "mysql:mysql", staged], check=True)
        proc = subprocess.run(["mysql", "-u", "root", "-N", "neutraleats", "-e",
                               f"LOAD DATA INFILE '{staged}' INTO TABLE `{args.table}` "
                               f"CHARACTER SET utf8mb4 FIELDS TERMINATED BY '\\t' "
                               f"LINES TERMINATED BY '\\n' ({cols}); SELECT ROW_COUNT();"],
                              capture_output=True, text=True)
        os.unlink(staged)
        if proc.returncode != 0:
            sys.exit(f"mysql load failed for {state}:\n{proc.stderr[-2000:]}")
        loaded = int(proc.stdout.strip())
        status = "OK" if loaded == expected.get(state) == len(rows) else "MISMATCH"
        print(f"[load] {state}: {loaded} (expected {expected.get(state)}) {status}")
        if status != "OK":
            sys.exit(f"per-state reconciliation failed for {state}")
        loaded_total += loaded
    print(f"[us] staging load reconciled: {loaded_total} rows into {args.table}")


PHP_DDL_US = r"""<?php
[$_s, $cfg, $table] = $argv;
require_once $cfg;
$pdo = getDatabaseConnection();
$pdo->exec("DROP TABLE IF EXISTS `$table`");
$pdo->exec("CREATE TABLE `$table` (
  id varchar(255) NOT NULL, name varchar(500) NOT NULL,
  lat decimal(10,8) NOT NULL, lng decimal(11,8) NOT NULL,
  type varchar(100) NOT NULL, cuisine varchar(200) DEFAULT NULL,
  brand varchar(200) DEFAULT NULL, source varchar(50) NOT NULL,
  source_id varchar(255) DEFAULT NULL, address varchar(500) DEFAULT NULL,
  city varchar(200) DEFAULT NULL, state varchar(100) DEFAULT NULL,
  zip varchar(20) DEFAULT NULL, phone varchar(50) DEFAULT NULL,
  website varchar(500) DEFAULT NULL, confidence_score decimal(3,2) DEFAULT 0.50,
  category_primary varchar(200) DEFAULT NULL, norm_name varchar(500) DEFAULT NULL,
  batch_state varchar(10) DEFAULT NULL,
  matched_prod tinyint NOT NULL DEFAULT 0,
  PRIMARY KEY (id), KEY idx_lat (lat), KEY idx_lng (lng),
  KEY idx_norm (norm_name), KEY idx_batch (batch_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
echo "nationwide staging table ready\n";
"""


if __name__ == "__main__":
    main()
