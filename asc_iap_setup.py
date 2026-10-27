#!/usr/bin/env python3
"""Create the neutral eats tip-jar IAP products via the ASC API.

Usage: asc_iap_setup.py [--dry-list]
Creates the 7 consumable "Supporter Tip" products (ids
ai.croix.neutraleats.tip.*) with an en-US localization, a US price
schedule at the ladder tiers, and US availability. Idempotent:
products that already exist are reported and completed in place
rather than recreated. Every API response that fails is printed
verbatim so a Paid Apps agreement / banking / tax blocker shows
Apple's exact words, not a paraphrase.
"""
import base64, json, sys, time, urllib.request, urllib.error

KEY_ID = "5RFW8JALAL"
ISSUER = "df53a4cb-f9e1-42f3-afc9-64de0ed4743f"
KEY_PATH = "/home/hatch/workspace/croixbrains-signing/AuthKey_5RFW8JALAL.p8"
APP_ID = "6827198241"
BASE = "https://api.appstoreconnect.apple.com"
REVIEW_IMAGE = "/home/hatch/workspace/neutral-eats/appstore-screenshots/01-summary.png"

# Apple's inAppPurchaseLocalizations.description field is capped at 55
# characters (API-verified 2026-10-27: ENTITY_ERROR.ATTRIBUTE.INVALID
# .TOO_LONG) — the full pitch ("A voluntary tip to support Neutral
# Eats. Tips are optional and buy nothing — the app is exactly the
# same either way. Thank you!") cannot fit it. This is the same
# meaning compressed to the field: voluntary, buys nothing, thanks.
# The full wording lives in the app's Support sheet instead.
DESCRIPTION = "A voluntary tip that buys nothing. Thank you!"

PRODUCTS = [
    ("ai.croix.neutraleats.tip.099",  "0.99",  "Supporter Tip (0.99)"),
    ("ai.croix.neutraleats.tip.199",  "1.99",  "Supporter Tip (1.99)"),
    ("ai.croix.neutraleats.tip.299",  "2.99",  "Supporter Tip (2.99)"),
    ("ai.croix.neutraleats.tip.499",  "4.99",  "Supporter Tip (4.99)"),
    ("ai.croix.neutraleats.tip.999",  "9.99",  "Supporter Tip (9.99)"),
    ("ai.croix.neutraleats.tip.1999", "19.99", "Supporter Tip (19.99)"),
    ("ai.croix.neutraleats.tip.4999", "49.99", "Supporter Tip (49.99)"),
]


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt() -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    key = serialization.load_pem_private_key(open(KEY_PATH, "rb").read(), password=None)
    now = int(time.time())
    header = {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"}
    payload = {"iss": ISSUER, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"}
    signing_input = (b64u(json.dumps(header).encode()) + "." + b64u(json.dumps(payload).encode())).encode()
    der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return signing_input.decode() + "." + b64u(sig)


def call(token, method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Authorization", "Bearer " + token)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {"raw": raw[:800]}


def err_text(resp):
    return json.dumps(resp)[:900]


def list_existing(token):
    status, resp = call(token, "GET",
                        f"/v1/apps/{APP_ID}/inAppPurchasesV2?limit=200")
    if status != 200:
        print(f"LIST IAPs failed: HTTP {status} {err_text(resp)}")
        return {}
    out = {}
    for item in resp.get("data", []):
        out[item["attributes"].get("productId")] = item
    return out


def find_price_point(token, iap_id, price):
    """Page the IAP's US price points until the tier matches."""
    path = (f"/v2/inAppPurchases/{iap_id}/pricePoints"
            f"?filter[territory]=USA&limit=200")
    seen = 0
    while path and seen < 10:
        status, resp = call(token, "GET", path)
        if status != 200:
            print(f"  pricePoints failed: HTTP {status} {err_text(resp)}")
            return None
        for pp in resp.get("data", []):
            if pp["attributes"].get("customerPrice") == price:
                return pp["id"]
        nxt = (resp.get("links") or {}).get("next")
        path = nxt[len(BASE):] if nxt else None
        seen += 1
    return None


def ensure_localization(token, iap_id, display_name, fallback_name):
    status, resp = call(token, "GET",
                        f"/v2/inAppPurchases/{iap_id}/inAppPurchaseLocalizations?limit=50")
    if status == 200:
        for loc in resp.get("data", []):
            if loc["attributes"].get("locale") == "en-US":
                return "exists"
    for name in (display_name, fallback_name):
        body = {"data": {
            "type": "inAppPurchaseLocalizations",
            "attributes": {"locale": "en-US", "name": name,
                           "description": DESCRIPTION},
            "relationships": {"inAppPurchaseV2": {
                "data": {"type": "inAppPurchases", "id": iap_id}}}}}
        status, resp = call(token, "POST", "/v1/inAppPurchaseLocalizations", body)
        if status in (200, 201):
            return f"created (name={name!r})"
        print(f"  localization with name {name!r} failed: HTTP {status} {err_text(resp)}")
    return "FAILED"


def ensure_price_schedule(token, iap_id, price):
    status, resp = call(token, "GET",
                        f"/v2/inAppPurchases/{iap_id}/iapPriceSchedule")
    if status == 200 and resp.get("data"):
        return "exists"
    pp_id = find_price_point(token, iap_id, price)
    if not pp_id:
        print(f"  no US price point found for tier {price}")
        return "FAILED"
    body = {
        "data": {
            "type": "inAppPurchasePriceSchedules",
            "relationships": {
                "inAppPurchase": {"data": {"type": "inAppPurchases", "id": iap_id}},
                "baseTerritory": {"data": {"type": "territories", "id": "USA"}},
                "manualPrices": {"data": [{"type": "inAppPurchasePrices", "id": "${price1}"}]},
            },
        },
        "included": [{
            "type": "inAppPurchasePrices", "id": "${price1}",
            "relationships": {
                "inAppPurchasePricePoint": {
                    "data": {"type": "inAppPurchasePricePoints", "id": pp_id}},
            },
        }],
    }
    status, resp = call(token, "POST", "/v1/inAppPurchasePriceSchedules", body)
    if status in (200, 201):
        return "created"
    print(f"  price schedule failed: HTTP {status} {err_text(resp)}")
    return "FAILED"


def ensure_availability(token, iap_id):
    status, resp = call(token, "GET",
                        f"/v2/inAppPurchases/{iap_id}/inAppPurchaseAvailability")
    if status == 200 and resp.get("data"):
        return "exists"
    body = {"data": {
        "type": "inAppPurchaseAvailabilities",
        "attributes": {"availableInNewTerritories": False},
        "relationships": {
            "inAppPurchase": {"data": {"type": "inAppPurchases", "id": iap_id}},
            "availableTerritories": {"data": [{"type": "territories", "id": "USA"}]},
        }}}
    status, resp = call(token, "POST", "/v1/inAppPurchaseAvailabilities", body)
    if status in (200, 201):
        return "created"
    print(f"  availability failed: HTTP {status} {err_text(resp)}")
    return "FAILED"


def ensure_screenshot(token, iap_id, image_path):
    """Upload the App Store review screenshot if none exists yet.

    Without one the IAP sits in MISSING_METADATA even with name,
    price and availability set. The image used is the packet's
    01-summary app screenshot as a placeholder \u2014 it must be
    replaced with a capture of the actual tip sheet before the
    build-21 submission (noted in the submission packet).
    """
    import hashlib, os
    status, resp = call(token, "GET",
                        f"/v2/inAppPurchases/{iap_id}/appStoreReviewScreenshot")
    if status == 200 and resp.get("data"):
        return "exists"
    raw = open(image_path, "rb").read()
    body = {"data": {
        "type": "inAppPurchaseAppStoreReviewScreenshots",
        "attributes": {"fileName": os.path.basename(image_path),
                       "fileSize": len(raw)},
        "relationships": {"inAppPurchaseV2": {
            "data": {"type": "inAppPurchases", "id": iap_id}}}}}
    status, resp = call(token, "POST",
                        "/v1/inAppPurchaseAppStoreReviewScreenshots", body)
    if status not in (200, 201):
        print(f"  screenshot reserve failed: HTTP {status} {err_text(resp)}")
        return "FAILED"
    shot = resp["data"]
    for op in shot["attributes"].get("uploadOperations", []):
        chunk = raw[op["offset"]:op["offset"] + op["length"]]
        req = urllib.request.Request(op["url"], method=op.get("method", "PUT"))
        for h in op.get("requestHeaders", []):
            req.add_header(h["name"], h["value"])
        try:
            with urllib.request.urlopen(req, data=chunk, timeout=120) as r:
                if r.status not in (200, 201):
                    print(f"  screenshot chunk upload: HTTP {r.status}")
                    return "FAILED"
        except urllib.error.HTTPError as e:
            print(f"  screenshot chunk upload failed: HTTP {e.code}")
            return "FAILED"
    body = {"data": {
        "type": "inAppPurchaseAppStoreReviewScreenshots", "id": shot["id"],
        "attributes": {"uploaded": True,
                       "sourceFileChecksum": hashlib.md5(raw).hexdigest()}}}
    status, resp = call(token, "PATCH",
                        f"/v1/inAppPurchaseAppStoreReviewScreenshots/{shot['id']}",
                        body)
    if status in (200, 201):
        return "created"
    print(f"  screenshot commit failed: HTTP {status} {err_text(resp)}")
    return "FAILED"


def get_state(token, iap_id):
    status, resp = call(token, "GET", f"/v2/inAppPurchases/{iap_id}")
    if status == 200:
        return resp.get("data", {}).get("attributes", {}).get("state")
    return f"HTTP {status}"


def main():
    token = make_jwt()
    existing = list_existing(token)
    print(f"existing IAPs on app: {sorted(existing.keys()) or 'none'}")
    results = {}
    blocked = None
    for product_id, price, ref_name in PRODUCTS:
        if blocked:
            results[product_id] = f"SKIPPED (agreement blocker above)"
            continue
        print(f"== {product_id} tier ${price} ==")
        item = existing.get(product_id)
        if item:
            iap_id = item["id"]
            print(f"  product exists: id={iap_id} state={item['attributes'].get('state')}")
            created = "exists"
        else:
            body = {"data": {
                "type": "inAppPurchases",
                "attributes": {"name": ref_name, "productId": product_id,
                               "inAppPurchaseType": "CONSUMABLE"},
                "relationships": {"app": {
                    "data": {"type": "apps", "id": APP_ID}}}}}
            status, resp = call(token, "POST", "/v2/inAppPurchases", body)
            if status not in (200, 201):
                print(f"  CREATE FAILED: HTTP {status} {err_text(resp)}")
                results[product_id] = f"CREATE FAILED HTTP {status}: {err_text(resp)}"
                blocked = product_id
                continue
            iap_id = resp["data"]["id"]
            created = "created"
            print(f"  product created: id={iap_id}")
        loc = ensure_localization(token, iap_id, "Supporter Tip", ref_name)
        sched = ensure_price_schedule(token, iap_id, price)
        avail = ensure_availability(token, iap_id)
        shot = ensure_screenshot(token, iap_id, REVIEW_IMAGE)
        state = get_state(token, iap_id)
        results[product_id] = (f"product={created} localization={loc} "
                               f"priceSchedule={sched} availability={avail} "
                               f"screenshot={shot} state={state}")
        print(f"  -> {results[product_id]}")
    print("\n==== SUMMARY ====")
    for pid, line in results.items():
        print(f"{pid}: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
