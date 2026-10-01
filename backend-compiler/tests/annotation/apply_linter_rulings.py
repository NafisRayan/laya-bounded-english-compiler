"""Apply the adjudicator-of-record's LINTER_RULINGS.md to human gold.

60 removals: 39 authentication pins (kept only in the 6 auth-vocabulary
cases), all edge_functions corpus-wide (16), saved_items_favorites
bookings+renter, moderator_role/staff_role admin roles, and the
role_names_two_roles verification.method=admin_approval pin. Moderator
and staff are not ontology-valid roles, so the roles collector ends empty
while role_names carries the sentence's own naming.
"""


import sys

sys.path.insert(0, ".")

import yaml  # noqa: E402

from tests.annotation.build_human_gold import HUMAN_GOLD_PATH  # noqa: E402

AUTH_KEEP = {
    "alias_and_phrase_decide", "laya_high_decides", "github_auth_alias",
    "oauth_google_alias", "magic_link_alias", "bucket_purpose_avatars",
}

gold = yaml.safe_load(HUMAN_GOLD_PATH.read_text(encoding="utf-8"))

gold = yaml.safe_load(HUMAN_GOLD_PATH.read_text(encoding="utf-8"))

removed = {"authentication": 0, "edges": 0, "other": 0}
for case, entry in gold.items():
    if case in AUTH_KEEP:
        pass
    elif entry["features"].get("authentication") is True:
        del entry["features"]["authentication"]
        removed["authentication"] += 1
    if entry["edge_functions"]:
        removed["edges"] += len(entry["edge_functions"])
        entry["edge_functions"] = []

for case, drops in {
    "saved_items_favorites": [("features", "bookings"), ("roles", "renter")],
    "moderator_role": [("roles", "admin")],
    "staff_role": [("roles", "admin")],
}.items():
    for kind, item in drops:
        if kind == "features":
            gold[case]["features"].pop(item, None)
        else:
            gold[case]["roles"] = [r for r in gold[case]["roles"] if r != item]
        removed["other"] += 1

gold["role_names_two_roles"]["parameters"].pop("verification.method", None)
removed["other"] += 1

HUMAN_GOLD_PATH.write_text(yaml.safe_dump(gold, sort_keys=True), encoding="utf-8")
print("removed:", removed, "| total:", sum(removed.values()))
