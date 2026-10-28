#!/usr/bin/env python3
"""Set + verify privacyPolicyUrl on the Neutral Eats app-info localization.

Usage: asc_privacy.py
Finds the editable appInfo for app 6827198241, lists its localizations,
PATCHes the en-US one's privacyPolicyUrl to https://neutraleats.com/privacy,
then reads it back. Idempotent.
"""
import base64, json, sys, time, urllib.request, urllib.error

KEY_ID = "5RFW8JALAL"
ISSUER = "df53a4cb-f9e1-42f3-afc9-64de0ed4743f"
KEY_PATH = "/home/hatch/workspace/croixbrains-signing/AuthKey_5RFW8JALAL.p8"
APP_ID = "6827198241"
BASE = "https://api.appstoreconnect.apple.com"
PRIVACY_URL = "https://neutraleats.com/privacy"


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
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {"raw": raw[:400]}


def main():
    token = make_jwt()
    status, resp = call(token, "GET", f"/v1/apps/{APP_ID}/appInfos")
    if status != 200 or not resp.get("data"):
        print(f"appInfos lookup failed: HTTP {status} {json.dumps(resp)[:400]}")
        return 1
    for info in resp["data"]:
        print(f"appInfo {info['id']} state={info['attributes'].get('state')}")
    # Prefer the editable one (PREPARE_FOR_SUBMISSION / DEVELOPER_REJECTED etc.);
    # fall back to the first.
    editable_states = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED",
                       "METADATA_REJECTED", "WAITING_FOR_REVIEW"}
    info = next((i for i in resp["data"] if i["attributes"].get("state") in editable_states),
                resp["data"][0])
    info_id = info["id"]
    print(f"using appInfo {info_id} ({info['attributes'].get('state')})")

    status, resp = call(token, "GET", f"/v1/appInfos/{info_id}/appInfoLocalizations")
    if status != 200 or not resp.get("data"):
        print(f"localizations lookup failed: HTTP {status} {json.dumps(resp)[:400]}")
        return 1
    loc = None
    for l in resp["data"]:
        a = l["attributes"]
        print(f"loc {l['id']} locale={a.get('locale')} privacyPolicyUrl={a.get('privacyPolicyUrl')!r}")
        if a.get("locale") == "en-US":
            loc = l
    if loc is None:
        print("no en-US localization found")
        return 1

    if loc["attributes"].get("privacyPolicyUrl") != PRIVACY_URL:
        status, resp = call(token, "PATCH", f"/v1/appInfoLocalizations/{loc['id']}",
                            {"data": {"type": "appInfoLocalizations", "id": loc["id"],
                                      "attributes": {"privacyPolicyUrl": PRIVACY_URL}}})
        print(f"PATCH privacyPolicyUrl: HTTP {status}")
        if status not in (200, 201):
            print(json.dumps(resp)[:500])
            return 1
    else:
        print("privacyPolicyUrl already set — skipping PATCH")

    token = make_jwt()
    status, resp = call(token, "GET", f"/v1/appInfoLocalizations/{loc['id']}")
    got = resp.get("data", {}).get("attributes", {}).get("privacyPolicyUrl")
    print(f"read-back: HTTP {status} privacyPolicyUrl={got!r}")
    if got != PRIVACY_URL:
        print("MISMATCH — did not stick")
        return 1
    print("VERIFIED: privacyPolicyUrl is set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
