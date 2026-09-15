from django.template import engines

from speakers.markdown import render_md


class TestRenderMd:
    def test_empty(self):
        assert render_md("") == ""
        assert render_md(None) == ""

    def test_renders_markdown(self):
        html = render_md("Hello **world**")
        assert html == "<p>Hello <strong>world</strong></p>"

    def test_strips_script_tag(self):
        html = render_md('Hi <script>alert("x")</script> there')
        assert "<script" not in html
        assert "alert" not in html
        assert "Hi" in html and "there" in html

    def test_strips_event_handlers_and_keeps_links(self):
        html = render_md('<a href="https://example.com" onclick="steal()">x</a>')
        assert "onclick" not in html
        assert 'href="https://example.com"' in html
        assert 'rel="noopener noreferrer"' in html

    def test_drops_javascript_urls(self):
        html = render_md("[x](javascript:alert(1))")
        assert "javascript:" not in html

    def test_template_filter(self):
        template = engines["django"].from_string(
            "{% load speakers_extras %}{{ text|speaker_md }}"
        )
        rendered = template.render({"text": "*hi* <script>x</script>"})
        assert rendered == "<p><em>hi</em> </p>"
