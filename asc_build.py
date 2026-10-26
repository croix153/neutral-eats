#!/usr/bin/env python3
"""Finish a neutral eats TestFlight release via the ASC API.

Usage: asc_build.py <build-number>
Finds the build for app 6827198241 with that version string; if it is
VALID, declares usesNonExemptEncryption=false and attaches it to the
Internal Testers group, then prints the internalBuildState. If it is
still processing, says so (exit 3) — safe to re-run; every step is
idempotent.
"""
import base64, json, sys, time, urllib.request, urllib.error

KEY_ID = "5RFW8JALAL"
ISSUER = "df53a4cb-f9e1-42f3-afc9-64de0ed4743f"
KEY_PATH = "/home/hatch/workspace/croixbrains-signing/AuthKey_5RFW8JALAL.p8"
APP_ID = "6827198241"
GROUP_ID = "bd9e8edd-c932-480e-9f8f-253229e45049"
BASE = "https://api.appstoreconnect.apple.com"


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
    version = sys.argv[1]
    token = make_jwt()
    status, resp = call(token, "GET",
                        f"/v1/builds?filter[app]={APP_ID}&filter[version]={version}&limit=1")
    if status != 200 or not resp.get("data"):
        print(f"build lookup failed: HTTP {status} {json.dumps(resp)[:300]}")
        return 1
    build = resp["data"][0]
    bid = build["id"]
    state = build["attributes"].get("processingState")
    print(f"build {version}: id={bid} processingState={state} expired={build['attributes'].get('expired')}")
    if state != "VALID":
        print("not VALID yet — re-run later")
        return 3
    status, resp = call(token, "PATCH", f"/v1/builds/{bid}",
                        {"data": {"type": "builds", "id": bid,
                                  "attributes": {"usesNonExemptEncryption": False}}})
    print(f"compliance PATCH: HTTP {status}")
    if status not in (200, 201):
        print(json.dumps(resp)[:300])
        return 1
    status, resp = call(token, "POST", f"/v1/betaGroups/{GROUP_ID}/relationships/builds",
                        {"data": [{"type": "builds", "id": bid}]})
    print(f"group attach POST: HTTP {status}")
    if status not in (200, 201, 204):
        print(json.dumps(resp)[:300])
        return 1
    status, resp = call(token, "GET", f"/v1/builds/{bid}/buildBetaDetail")
    detail = resp.get("data", {}).get("attributes", {})
    print(f"internalBuildState={detail.get('internalBuildState')} "
          f"externalBuildState={detail.get('externalBuildState')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
