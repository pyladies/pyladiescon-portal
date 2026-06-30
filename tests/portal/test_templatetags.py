from portal.templatetags.portal_extras import markdownify


class TestMarkdownify:
    def test_renders_markdown(self):
        out = markdownify("**bold** and [link](https://example.com)")
        assert "<strong>bold</strong>" in out
        assert '<a href="https://example.com"' in out

    def test_strips_unsafe_html(self):
        out = markdownify("hi <script>alert(1)</script>")
        assert "<script>" not in out

    def test_empty_value(self):
        assert markdownify("") == ""
        assert markdownify(None) == ""
