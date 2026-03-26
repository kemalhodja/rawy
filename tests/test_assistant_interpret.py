from app.services.assistant_lindy import interpret_user_message


def test_interpret_weekly():
    assert interpret_user_message("Bu hafta ne yaptım?")["intent"] == "weekly_summary"


def test_interpret_tomorrow():
    assert interpret_user_message("Yarın için plan öner")["intent"] == "tomorrow_plan"


def test_interpret_search_quoted():
    r = interpret_user_message("Fikirlerimde 'ürün' geçenleri bul")
    assert r["intent"] == "search"
    assert r["query"] == "ürün"


def test_interpret_search_gecen():
    r = interpret_user_message("fikirlerimde ürün geçenleri bul")
    assert r["intent"] == "search"
    assert r["query"] == "ürün"
