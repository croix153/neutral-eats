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
    args = ap.parse_args()

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
CREATE OR REPLACE TEMPORARY MACRO clean(x) AS
  replace(replace(replace(replace(x, chr(9), ' '), chr(10), ' '), chr(13), ' '), chr(92), ' ');
COPY (
  WITH base AS (
    SELECT * FROM read_parquet('fl_bbox_raw.parquet')
    WHERE addresses[1].country = 'US' OR addresses[1].country IS NULL
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


if __name__ == "__main__":
    main()
