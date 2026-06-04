from spendetector.notion_io import bucket_month, bucket_week


def test_month():
    assert bucket_month("2026-06-04") == "2026-06"
    assert bucket_month("2026-12-31") == "2026-12"


def test_week():
    assert bucket_week("2026-06-04") == "2026-W23"


def test_week_uses_iso_year_at_boundary():
    # 2027-01-01 falls in ISO week 53 of ISO-year 2026
    assert bucket_week("2027-01-01") == "2026-W53"
