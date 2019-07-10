from unittest import TestCase
from mock import patch, Mock

from lxml import etree
from lxml.cssselect import ExpressionError
from inlinestyler.converter import Conversion, fix_relative_urls


class TestConversion(TestCase):

    def setUp(self):
        self.converter = Conversion()

    def test_fix_relative_urls(self):
        source = "https://www.mytesturl.com"
        link = "url('assets/stylesheets/main.css')"

        self.assertEqual((fix_relative_urls(link, source)), "url('https://www.mytesturl.com/assets/stylesheets/main.css')")

    def test_init(self):
        self.assertEqual(self.converter.CSSErrors, [])
        self.assertEqual(self.converter.CSSUnsupportErrors, {})
        self.assertEqual(self.converter.supportPercentage, 100)
        self.assertEqual(self.converter.convertedHTML, "")
        self.assertEqual(self.converter.mediaRules, "")

    def test_styleattribute(self):
        element = etree.XML('<p style="color: red;">Test</p>')

        self.assertEqual(self.converter.styleattribute(element).color, 'red')

    def test_get_view(self):
        document = etree.XML('<html><head></head><body><p class="turn_red">This text should be red.</p><p class="turn_red" style="font-weight: bold;">This text should also be red, but bold too.</p><p>This text should be default.</p></body></html>')
        css = '.turn_red{ color: red; }'
        view = self.converter.get_view(document, css)

        self.assertEqual(len(view.items()), 2)
        for element, style in view.items():
            self.assertEqual(element.tag, 'p')
            self.assertEqual(style.getProperty('color').value, 'red')
            if style.length == 2:
                self.assertEqual(style.getProperty('font-weight').value, 'bold')

    def test_get_view_pseudoclass(self):
        document = etree.XML('<html><head></head><body><p class="turn_red">This text should be red.</p><p class="turn_red" style="font-weight: bold;">This text should also be red, but bold too.</p><p>This text should be default.</p></body></html>')
        css = '.turn_red{ color: red; } .turn_red:hover{ color: magenta; }'
        view = self.converter.get_view(document, css)

        self.assertEqual(len(view.items()), 2)
        for element, style in view.items():
            self.assertEqual(element.tag, 'p')
            self.assertEqual(style.getProperty('color').value, 'red')
            if style.length == 2:
                self.assertEqual(style.getProperty('font-weight').value, 'bold')
        self.assertIn('magenta', self.converter.mediaRules)

    def test_get_view_partial_and_unsupported(self):
        document = etree.XML('<html><head></head><body><p class="pad_me">Give me all the background and the padding.</p><p>Do not pad me.</p></body></html>')
        css = '.pad_me{ background: black; padding: 10px 10px 10px 15px; transition: 3s; }'
        view = self.converter.get_view(document, css)

        self.assertEqual(len(view.items()), 1)
        for element, style in view.items():
            self.assertEqual(element.tag, 'p')
            self.assertEqual(style.getProperty('padding').value, '10px 10px 10px 15px')
            self.assertEqual(style.getProperty('background').value, 'black')
        self.assertEqual(len(self.converter.CSSUnsupportErrors), 2)

    def test_get_view_with_important(self):
        document = etree.XML('<html><head></head><body><p class="big_bold">This text should be big and bold.</p><p class="big_bold not_as_bold">This text should be big and less bold.</p><p>This text should be default.</p></body></html>')
        css = '.big_bold{ font-size: 20px; font-weight: bold; } .not_as_bold{ font-weight: 600 !important; }'
        view = self.converter.get_view(document, css)

        self.assertEqual(len(view.items()), 2)
        for element, style in view.items():
            self.assertEqual(element.tag, 'p')
            self.assertEqual(style.getProperty('font-size').value, '20px')
            if 'not_as_bold' in element.get('class'):
                self.assertEqual(style.getProperty('font-weight').value, '600')
            else:
                self.assertEqual(style.getProperty('font-weight').value, 'bold')

    @patch('lxml.cssselect.CSSSelector.evaluate')
    def test_get_view_with_error(self, evaluate_mock):
        document = etree.XML('<html><head></head><body><p class="turn_red">This text should be red.</p><p class="turn_red" style="font-weight: bold;">This text should also be red, but bold too.</p><p>This text should be default.</p></body></html>')
        css = '.turn_red{ color: red; }'
        evaluate_mock.side_effect = ExpressionError('Something is wrong!')
        view = self.converter.get_view(document, css)

        self.assertEqual(len(view.items()), 0)
        self.assertEqual(len(self.converter.CSSErrors), 1)

    def test_perform(self):
        html = '<html><head><style>.turn_red{ color: red; } .turn_red:hover{ color: magenta; }</style></head><body><p class="turn_red">This text should be red.</p><p class="turn_red" style="font-weight: bold;">This text should also be red, but bold too.</p><p>This text should be default.</p></body></html>'
        document = etree.XML(html)
        sourceURL = None

        performed = self.converter.perform(document, html, sourceURL)
        self.assertIn('magenta', self.converter.mediaRules)

    def test_perform_source_url(self):
        html = '<html><head><style>.turn_red{ color: red; } .turn_red:hover{ color: magenta; }</style></head><body><p class="turn_red">This text should be red.</p><p class="turn_red" style="font-weight: bold;">This text should also be red, but bold too.</p><p>This text should be default.</p><img src="test.jpg" alt="fake image" /></body></html>'
        document = etree.XML(html)
        sourceURL = 'https://mycss.com'

        performed = self.converter.perform(document, html, sourceURL)
        self.assertIn('magenta', self.converter.mediaRules)

    @patch('requests.get')
    def test_perform_linked_file(self, csstext_mock):
        html = '<html><head><link rel="stylesheet" href="style.css" type="text/css" /></head><body><a href="#">Skip</a><p class="turn_red">This text should be red.</p><p class="turn_red" style="font-weight: bold;">This text should also be red, but bold too.</p><p>This text should be default.</p></body></html>'
        document = etree.XML(html)
        sourceURL = 'https://mycss.com'

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '.turn_red{ color: red; } .turn_red:hover{ color: magenta; }'
        csstext_mock.return_value = mock_response

        performed = self.converter.perform(document, html, sourceURL)
        self.assertIn('magenta', self.converter.mediaRules)

    @patch('requests.get')
    def test_perform_linked_file_fail(self, csstext_mock):
        html = '<html><head><link rel="stylesheet" href="style.css" type="text/css" /></head><body><p class="turn_red">This text should be red.</p><p class="turn_red" style="font-weight: bold;">This text should also be red, but bold too.</p><p>This text should be default.</p></body></html>'
        document = etree.XML(html)
        sourceURL = 'https://mycss.com'

        mock_response = Mock()
        mock_response.status_code = 404
        csstext_mock.return_value = mock_response

        with self.assertRaises(IOError):
            self.converter.perform(document, html, sourceURL)
