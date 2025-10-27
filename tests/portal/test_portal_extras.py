from portal.templatetags.portal_extras import as_currency, get_item


def test_get_item_template_filter():

    d = {"a": 1, "b": 2}
    assert get_item(d, "a") == 1
    assert get_item(d, "b") == 2
    assert get_item(d, "c") is None


def test_as_currency():
    assert as_currency(1000) == "$1,000"
    assert as_currency(1234567.89) == "$1,234,568"
    assert as_currency("invalid") == ""
    assert as_currency(None) == ""
