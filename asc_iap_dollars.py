#!/usr/bin/env python3
"""Whole-dollar tip ladder: create the d1..d100 products, retire the cents.

Build 23 (Croix 2026-10-27): the $0.99-$49.99 ladder is replaced by
whole dollars only — $1 / $2 / $5 / $10 / $20 / $50 / $100. Creates
the seven new CONSUMABLE products with the same shape as
asc_iap_setup.py (en-US localization, US price schedule picked by
exact customerPrice match, US availability, review screenshot) so
each reaches READY_TO_SUBMIT, then removes availability from the
seven cent products (records kept, never deletable by accident)
so they can never be sold or submitted. Idempotent throughout.
"""
import sys
sys.path.insert(0, "/home/hatch/workspace/neutral-eats")
import asc_iap_setup as s

NEW_PRODUCTS = [
    ("ai.croix.neutraleats.tip.d1",   "1.00",   "Supporter Tip (1.00)"),
    ("ai.croix.neutraleats.tip.d2",   "2.00",   "Supporter Tip (2.00)"),
    ("ai.croix.neutraleats.tip.d5",   "5.00",   "Supporter Tip (5.00)"),
    ("ai.croix.neutraleats.tip.d10",  "10.00",  "Supporter Tip (10.00)"),
    ("ai.croix.neutraleats.tip.d20",  "20.00",  "Supporter Tip (20.00)"),
    ("ai.croix.neutraleats.tip.d50",  "50.00",  "Supporter Tip (50.00)"),
    ("ai.croix.neutraleats.tip.d100", "100.00", "Supporter Tip (100.00)"),
]

OLD_PRODUCTS = [
    "ai.croix.neutraleats.tip.099",
    "ai.croix.neutraleats.tip.199",
    "ai.croix.neutraleats.tip.299",
    "ai.croix.neutraleats.tip.499",
    "ai.croix.neutraleats.tip.999",
    "ai.croix.neutraleats.tip.1999",
    "ai.croix.neutraleats.tip.4999",
]


def lookup_price(price):
    """Apple's customerPrice strings are not zero-padded: the $1.00
    tier is '1.0', $10 is '10.0' (while $0.99 stays '0.99'). Normalize
    the two-decimal form for the exact-match lookup."""
    if "." in price:
        price = price.rstrip("0").rstrip(".")
        if "." not in price:
            price += ".0"
    return price


def ensure_price_schedule_real(token, iap_id, price):
    """asc_iap_setup.ensure_price_schedule checks whether the schedule
    RESOURCE exists — but for fresh V2 IAPs that shell always exists
    with zero prices, a false positive (verified on d1/d100: schedule
    present, manualPrices = 0, state stuck at MISSING_METADATA).
    Check the actual manual prices instead."""
    status, resp = s.call(
        token, "GET", f"/v2/inAppPurchases/{iap_id}/iapPriceSchedule")
    sched = resp.get("data") if status == 200 else None
    if sched:
        status, resp = s.call(
            token, "GET",
            f"/v1/inAppPurchasePriceSchedules/{sched['id']}/manualPrices"
            f"?limit=50")
        if status == 200 and resp.get("data"):
            return "exists"
    pp_id = s.find_price_point(token, iap_id, price)
    if not pp_id:
        print(f"  no US price point found for customerPrice {price}")
        return "FAILED"
    body = {
        "data": {
            "type": "inAppPurchasePriceSchedules",
            "relationships": {
                "inAppPurchase": {"data": {"type": "inAppPurchases",
                                           "id": iap_id}},
                "baseTerritory": {"data": {"type": "territories",
                                           "id": "USA"}},
                "manualPrices": {"data": [{"type": "inAppPurchasePrices",
                                           "id": "${price1}"}]},
            },
        },
        "included": [{
            "type": "inAppPurchasePrices", "id": "${price1}",
            "relationships": {
                "inAppPurchasePricePoint": {
                    "data": {"type": "inAppPurchasePricePoints",
                             "id": pp_id}},
            },
        }],
    }
    status, resp = s.call(token, "POST",
                          "/v1/inAppPurchasePriceSchedules", body)
    if status in (200, 201):
        return "created"
    print(f"  price schedule POST failed: HTTP {status} {s.err_text(resp)}")
    return "FAILED"


def create_products(token, existing):
    results = {}
    for product_id, price, ref_name in NEW_PRODUCTS:
        print(f"== {product_id} tier ${price} ==")
        item = existing.get(product_id)
        if item:
            iap_id = item["id"]
            created = "exists"
            print(f"  product exists: id={iap_id} "
                  f"state={item['attributes'].get('state')}")
        else:
            body = {"data": {
                "type": "inAppPurchases",
                "attributes": {"name": ref_name, "productId": product_id,
                               "inAppPurchaseType": "CONSUMABLE"},
                "relationships": {"app": {
                    "data": {"type": "apps", "id": s.APP_ID}}}}}
            status, resp = s.call(token, "POST", "/v2/inAppPurchases", body)
            if status not in (200, 201):
                print(f"  CREATE FAILED: HTTP {status} {s.err_text(resp)}")
                results[product_id] = f"CREATE FAILED HTTP {status}"
                continue
            iap_id = resp["data"]["id"]
            created = "created"
            print(f"  product created: id={iap_id}")
        loc = s.ensure_localization(token, iap_id, "Supporter Tip", ref_name)
        sched = ensure_price_schedule_real(token, iap_id, lookup_price(price))
        avail = s.ensure_availability(token, iap_id)
        shot = s.ensure_screenshot(token, iap_id, s.REVIEW_IMAGE)
        state = s.get_state(token, iap_id)
        results[product_id] = (f"id={iap_id} product={created} "
                               f"localization={loc} priceSchedule={sched} "
                               f"availability={avail} screenshot={shot} "
                               f"state={state}")
        print(f"  -> {results[product_id]}")
    return results


def get_availability(token, iap_id):
    status, resp = s.call(
        token, "GET", f"/v2/inAppPurchases/{iap_id}/inAppPurchaseAvailability")
    if status == 200 and resp.get("data"):
        return resp["data"]
    return None


def get_territories(token, iap_id):
    """Territory ids currently on the product's availability."""
    avail = get_availability(token, iap_id)
    if not avail:
        return None
    status, resp = s.call(
        token, "GET",
        f"/v1/inAppPurchaseAvailabilities/{avail['id']}/availableTerritories"
        f"?limit=200")
    if status != 200:
        return f"HTTP {status}"
    return [t["id"] for t in resp.get("data", [])]


def retire_products(token, existing):
    results = {}
    for product_id in OLD_PRODUCTS:
        item = existing.get(product_id)
        if not item:
            results[product_id] = "NOT FOUND on app"
            print(f"== retire {product_id}: not found ==")
            continue
        iap_id = item["id"]
        print(f"== retire {product_id} (id={iap_id}) ==")
        avail = get_availability(token, iap_id)
        if not avail:
            outcome = "availability already absent"
        else:
            # inAppPurchaseAvailabilities allows only CREATE/GET (DELETE
            # and PATCH both 403, API-verified) — but CREATE is an
            # upsert: re-POSTing with zero territories replaces the
            # availability wholesale. That is the remove-from-sale path.
            body = {"data": {
                "type": "inAppPurchaseAvailabilities",
                "attributes": {"availableInNewTerritories": False},
                "relationships": {
                    "inAppPurchase": {
                        "data": {"type": "inAppPurchases", "id": iap_id}},
                    "availableTerritories": {"data": []}}}}
            status, resp = s.call(token, "POST",
                                  "/v1/inAppPurchaseAvailabilities", body)
            if status in (200, 201):
                outcome = f"availability replaced with ZERO territories (HTTP {status})"
            else:
                outcome = (f"FAILED: re-POST HTTP {status} "
                           f"{s.err_text(resp)}")
        # Verify: the territories list must now be empty.
        territories = get_territories(token, iap_id)
        state = s.get_state(token, iap_id)
        if territories == []:
            verified = "territories=[] (verified)"
        elif territories is None:
            verified = "no availability resource (verified)"
        else:
            verified = f"territories STILL SET: {territories}"
        results[product_id] = f"{outcome}; {verified}; state={state}"
        print(f"  -> {results[product_id]}")
    return results


def main():
    token = s.make_jwt()
    existing = s.list_existing(token)
    print(f"existing IAPs on app: {sorted(existing.keys()) or 'none'}")
    print("\n--- CREATE whole-dollar ladder ---")
    created = create_products(token, existing)
    print("\n--- RETIRE cent ladder (availability off, records kept) ---")
    retired = retire_products(token, existing)
    print("\n==== SUMMARY: NEW ====")
    for pid, line in created.items():
        print(f"{pid}: {line}")
    print("==== SUMMARY: RETIRED ====")
    for pid, line in retired.items():
        print(f"{pid}: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
