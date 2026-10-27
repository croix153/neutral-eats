#!/usr/bin/env python3
"""successor_apply.py — ambiguity guards for the successor sweep apply.

Reads successor_census_v3_candidates.csv (7,120 post-containment-guard
candidates) and splits it into:
  - successor_apply_set.csv          -> venues to suppress
  - successor_ambiguity_review.csv   -> excluded by ambiguity guard (a)/(b),
                                        stays ACTIVE, for later review

Guards (user-approved 2026-10-27, "Guard the ambiguous classes, then apply"):
  (a) multi-brand survivor: survivor_name contains a comma
      (comma-joined operator/brand lists, e.g. Taqueria Gonzalez's survivor).
  (b) generic-only agreement: survivor_name and license_business share no
      distinctive token after stripping the pilot's GENERIC set
      (fl_dbpr_match.norm_text / GENERIC). Archetype: Tiano's Italian ->
      survivor "The Grille", license business "GRILLE" — both distinctive
      sets are empty, so the agreement rests on a generic word only.

Token sharing test: exact token equality, or substring containment
either direction for tokens of length >= 3 (catches squished/abbrev
variants like MICHOACANA vs MICHOACANA2 without matching junk pairs).
"""
import csv
import sys

sys.path.insert(0, "pipeline/licensing")
from fl_dbpr_match import GENERIC, norm_text  # noqa: E402

SRC = "successor_census_v3_candidates.csv"
APPLY_OUT = "successor_apply_set.csv"
REVIEW_OUT = "successor_ambiguity_review.csv"

HABANEROS_ID = "overture:688e947c-c3e2-4e1f-977b-f8dd62afc5b3"

# The pilot GENERIC set spells it GRILL; GRILLE is the same generic word
# (French spelling, ubiquitous in restaurant names) and the Tiano's
# archetype turns on it being generic: survivor "The Grille" vs license
# business "GRILLE" must leave BOTH distinctive sets empty.
GENERIC_EXTRA = {"GRILLE"}


def distinctive(name):
    return [t for t in norm_text(name)
            if t not in GENERIC and t not in GENERIC_EXTRA and len(t) > 1]


def shares_distinctive(a_name, b_name):
    a, b = distinctive(a_name), distinctive(b_name)
    if not a or not b:
        return False
    for s in a:
        for t in b:
            if s == t:
                return True
            if len(s) >= 3 and len(t) >= 3 and (s in t or t in s):
                return True
    return False


def main():
    rows = list(csv.DictReader(open(SRC, newline="", encoding="utf-8")))
    assert len(rows) == 7120, len(rows)

    apply_rows, review_rows = [], []
    n_a = n_b = 0
    for r in rows:
        if "," in r["survivor_name"]:
            review_rows.append({**r, "guard": "a_multibrand_survivor"})
            n_a += 1
        elif not shares_distinctive(r["survivor_name"], r["license_business"]):
            review_rows.append({**r, "guard": "b_generic_only_agreement"})
            n_b += 1
        else:
            apply_rows.append(r)

    # Archetype checks — hard requirements of the apply brief.
    by_id = {r["candidate_id"]: r for r in rows}
    tiano = next(r for r in rows if r["candidate_name"].startswith("Tiano"))
    taq = next(r for r in rows if r["candidate_name"] == "Taqueria Gonzalez")
    rev_ids = {r["candidate_id"] for r in review_rows}
    app_ids = {r["candidate_id"] for r in apply_rows}
    assert tiano["candidate_id"] in rev_ids, "Tiano's NOT excluded!"
    tiano_guard = next(r["guard"] for r in review_rows
                       if r["candidate_id"] == tiano["candidate_id"])
    assert tiano_guard == "b_generic_only_agreement", tiano_guard
    assert taq["candidate_id"] in rev_ids, "Taqueria Gonzalez NOT excluded!"
    taq_guard = next(r["guard"] for r in review_rows
                     if r["candidate_id"] == taq["candidate_id"])
    assert taq_guard == "a_multibrand_survivor", taq_guard
    assert HABANEROS_ID in app_ids, "Habaneros NOT in apply set!"
    assert not (app_ids & rev_ids)

    fields = list(rows[0].keys())
    with open(APPLY_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(apply_rows)
    with open(REVIEW_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields + ["guard"])
        w.writeheader()
        w.writerows(review_rows)

    print(f"v3 set:            {len(rows)}")
    print(f"guard (a) exclude: {n_a}")
    print(f"guard (b) exclude: {n_b}")
    print(f"review total:      {len(review_rows)}")
    print(f"APPLY SET:         {len(apply_rows)}")
    print(f"Tiano's excluded by: {tiano_guard}  ({tiano['candidate_name']} -> {tiano['survivor_name']})")
    print(f"Taqueria Gonzalez excluded by: {taq_guard}  (survivor: {taq['survivor_name']})")
    print(f"Habaneros in apply set: YES ({by_id[HABANEROS_ID]['candidate_name']} -> {by_id[HABANEROS_ID]['survivor_name']})")


if __name__ == "__main__":
    main()
