from builtins import str as text
from unittest import TestCase
from inlinestyler.utils import inline_css


class TestUtils(TestCase):
    def setUp(self):
        self.the_document = text(
            '<html><head><style>.turn_red{ color: red; }</style></head><body><p class="turn_red">This text should be red.</p></body></html>'
        )

    def test_no_markup(self):
        expected = text("<html><body><p>Hello World!</p></body></html>\n")
        self.assertEqual(inline_css("Hello World!"), expected)

    def test_inline_css(self):
        expected = text(
            '<html>\n<head></head>\n<body><p class="turn_red" style="color: red">This text should be red.</p></body>\n</html>\n'
        )
        self.assertEqual(inline_css(self.the_document), expected)
