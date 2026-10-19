from wordstat import count, top


def test_counts_case_insensitively():
    assert count("The the THE cat") == {"the": 3, "cat": 1}


def test_top_breaks_ties_alphabetically():
    assert top("b a b a c", 2) == [("a", 2), ("b", 2)]
