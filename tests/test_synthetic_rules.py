from collections import defaultdict


CURRENT_GROUP_STATUSES = {"Active", "Needs Revalidation"}


def logical_anchor(record, memberships, groups):
    membership = memberships.get(record["id"])
    if membership and membership["status"] == "Active":
        group = groups[membership["group"]]
        if group["status"] in CURRENT_GROUP_STATUSES:
            return "G:" + membership["group"]
    return "M:" + record["id"]


def canonical_dob(rows):
    usable = {row["dob"] for row in rows if row.get("dob") and row.get("dob_key") != "estimated"}
    if len(usable) > 1:
        return "Conflicting"
    if not usable:
        return "Unknown/Invalid"
    return next(iter(usable))


def canonical_sex(rows):
    trusted = {row["sex"] for row in rows if row.get("sex_mapped") and row.get("sex") in {"M", "F"}}
    if len(trusted) > 1:
        return "Conflicting"
    if not trusted:
        return "Unknown"
    return next(iter(trusted))


def district(row, valid):
    if row.get("res_district") in valid:
        return row["res_district"]
    if row.get("post_district") in valid:
        return row["post_district"]
    return "Unknown"


def governed_district(row, valid, inferred_codes):
    direct = district(row, valid)
    if direct != "Unknown":
        return direct, "direct"
    unique = set(inferred_codes)
    if len(unique) == 1:
        return next(iter(unique)), "inferred"
    return "Unknown", "ambiguous" if len(unique) > 1 else "unmatched"


def growth_dates(rows):
    usable = [row for row in rows if row.get("service_start")]
    overall = min((row["service_start"] for row in usable), default=None)
    by_service = {
        service: min(row["service_start"] for row in usable if row["service"] == service)
        for service in {row["service"] for row in usable}
    }
    return overall, by_service


def test_active_and_revalidation_memberships_collapse_but_ended_do_not():
    records = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
    memberships = {
        "a": {"group": "one", "status": "Active"},
        "b": {"group": "one", "status": "Active"},
        "c": {"group": "ended", "status": "Ended"},
        "d": {"group": "ended", "status": "Ended"},
    }
    groups = {"one": {"status": "Needs Revalidation"}, "ended": {"status": "Ended"}}
    assert len({logical_anchor(row, memberships, groups) for row in records}) == 3


def test_multi_service_people_count_once_globally_and_once_per_service():
    presence = [("person-1", "A"), ("person-1", "B"), ("person-2", "A")]
    assert len({person for person, _ in presence}) == 2
    by_service = defaultdict(set)
    for person, service in presence:
        by_service[service].add(person)
    assert {service: len(people) for service, people in by_service.items()} == {"A": 2, "B": 1}


def test_demographic_conflicts_and_untrusted_placeholder():
    assert canonical_dob([{"dob": "1980-01-01"}, {"dob": "1981-01-01"}]) == "Conflicting"
    assert canonical_dob([{"dob": "1980-01-01", "dob_key": "estimated"}]) == "Unknown/Invalid"
    assert canonical_sex([{"sex": "M", "sex_mapped": False}]) == "Unknown"
    assert canonical_sex(
        [{"sex": "M", "sex_mapped": True}, {"sex": "F", "sex_mapped": True}]
    ) == "Conflicting"


def test_valid_residential_then_postal_fallback():
    valid = {"CW", "ST"}
    assert district({"res_district": "CW", "post_district": "ST"}, valid) == "CW"
    assert district({"res_district": "bad", "post_district": "ST"}, valid) == "ST"
    assert district({"res_district": "bad", "post_district": "bad2"}, valid) == "Unknown"


def test_address_inference_is_last_resort_and_must_be_unique():
    valid = {"CW", "ST"}
    assert governed_district(
        {"res_district": "CW", "post_district": "ST"}, valid, ["YL"]
    ) == ("CW", "direct")
    assert governed_district(
        {"res_district": "bad", "post_district": "ST"}, valid, ["YL"]
    ) == ("ST", "direct")
    assert governed_district({}, valid, ["YL"]) == ("YL", "inferred")
    assert governed_district({}, valid, ["YL", "TM"]) == ("Unknown", "ambiguous")
    assert governed_district({}, valid, []) == ("Unknown", "unmatched")


def test_growth_uses_earliest_overall_and_first_date_within_service():
    rows = [
        {"service": "A", "service_start": "2024-04-01"},
        {"service": "A", "service_start": "2024-02-01"},
        {"service": "B", "service_start": "2024-03-01"},
        {"service": "B", "service_start": None},
    ]
    assert growth_dates(rows) == (
        "2024-02-01",
        {"A": "2024-02-01", "B": "2024-03-01"},
    )
