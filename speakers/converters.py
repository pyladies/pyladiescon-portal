"""URL converters for the speaker portal."""


class UnicodeSlugConverter:
    """A slug that may contain letters from any script.

    Django's built-in ``slug`` converter matches ASCII only; presenter and
    session slugs are derived with ``allow_unicode=True`` so that "李华" is
    addressed as /speakers/presenters/李华/ rather than a numbered fallback.
    A word character class in a Python pattern is unicode-aware.
    """

    regex = r"[-\w]+"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
