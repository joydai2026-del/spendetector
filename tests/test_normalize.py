from spendetector.extract import normalize_name


def test_collapses_case_and_size_tokens():
    assert normalize_name("Oat Milk 64oz") == "oat milk"
    assert normalize_name("OAT MILK") == "oat milk"
    assert normalize_name("Oat Milk") == "oat milk"


def test_strips_punctuation_and_size():
    assert normalize_name("Coca-Cola 12pk") == "coca cola"


def test_keeps_first_three_significant_words():
    assert normalize_name("Organic Whole Milk Gallon") == "organic whole milk"


def test_edge_cases():
    assert normalize_name("") == ""
    assert normalize_name("   ") == ""
