from unittest import TestCase

from inlinestyler.utils import inline_css


class TestUtils(TestCase):

    def setUp(self):
        self.the_document = '<html><head><style>.turn_red{ color: red; }</style></head><body><p class="turn_red">This text should be red.</p></body></html>'

    def test_inline_css(self):
        the_inlined_document = '<html>\n  <head/>\n  <body>\n    <p class="turn_red" style="color: red">This text should be red.</p>\n  </body>\n</html>\n'

        self.assertEqual(inline_css(self.the_document), the_inlined_document)
