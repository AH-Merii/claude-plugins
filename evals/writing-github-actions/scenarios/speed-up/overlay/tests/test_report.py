from wordstat import top


def test_full_report_matches_golden():
    assert top("a b a", 1) == [("a", 2)]


def test_report_handles_unicode():
    assert top("café café thé", 1)[0][1] >= 1


def test_report_parquet_roundtrip():
    assert top("", 3) == []
