#!/usr/bin/env python3
"""Fetch recent TestFlight crash feedback for neutral eats via ASC."""
import sys
sys.path.insert(0, "/home/hatch/workspace/neutral-eats")
from asc_build import make_jwt, call, APP_ID

token = make_jwt()
status, resp = call(token, "GET",
                    f"/v1/apps/{APP_ID}/betaFeedbackCrashSubmissions"
                    "?sort=-createdDate&limit=5"
                    "&include=build&fields[builds]=version,uploadedDate")
print("list HTTP", status)
for item in resp.get("data", []):
    a = item["attributes"]
    print(item["id"], "| created:", a.get("createdDate"),
          "| device:", a.get("deviceModel"), "| os:", a.get("osVersion"),
          "| build rel:", item.get("relationships", {}).get("build", {})
          .get("data", {}).get("id"))
    if len(sys.argv) > 1 and sys.argv[1] == item["id"]:
        s2, log = call(token, "GET",
                       f"/v1/betaFeedbackCrashSubmissions/{item['id']}/crashLog")
        print("crashLog HTTP", s2)
        text = log if isinstance(log, str) else str(log)
        print(text[:12000])
for inc in resp.get("included", []):
    print("included build:", inc["id"], inc["attributes"])
if not resp.get("data"):
    print(str(resp)[:600])
