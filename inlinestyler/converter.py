from __future__ import unicode_literals
import os
import sys
import csv
import cssutils
import re
import requests
import logging

from lxml import etree
from lxml.cssselect import CSSSelector, ExpressionError
from builtins import str as text

try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse

_url_re = re.compile(r"""url\((['"]?)([^'"\)]+)(['"]?)\)""", re.I)
log = logging.getLogger(__name__)


def fix_relative_urls(chunk, sourceURL):
    def fix_url(match):
        return (
            "url("
            + text(match.group(1))
            + urlparse.urljoin(text(sourceURL), text(match.group(2)))
            + text(match.group(3))
            + ")"
        )

    return _url_re.sub(fix_url, chunk)


class Conversion(object):
    def __init__(self):
        self.CSSErrors = []
        self.CSSUnsupportErrors = {}
        self.supportPercentage = 100
        self.convertedHTML = ""
        self.mediaRules = ""
        self.supportratios = {}
        self.compliance = {}
        self.client_count = 0

    def perform(self, document, sourceHTML, sourceURL):
        aggregateCSS = ""
        if sourceURL and not sourceURL.endswith("/"):
            sourceURL += "/"

        # retrieve CSS rel links from html pasted and aggregate into one string
        CSSRelSelector = CSSSelector(
            "link[rel=stylesheet],link[rel=StyleSheet],link[rel=STYLESHEET],style,Style"
        )
        matching = CSSRelSelector.evaluate(document)
        for element in matching:
            if element.tag.lower() == "style":
                csstext = element.text
                if sourceURL:
                    csstext = fix_relative_urls(csstext, sourceURL)
            else:
                try:
                    csspath = element.get("href")
                    if sourceURL:
                        csspath = urlparse.urljoin(sourceURL, csspath)
                    r = requests.get(csspath)
                    csstext = fix_relative_urls(r.text, csspath)
                except Exception as e:
                    log.exception(e)
                    raise IOError(
                        "The stylesheet " + element.get("href") + " could not be found"
                    )

            aggregateCSS += csstext
            element.getparent().remove(element)

        # convert  document to a style dictionary compatible with etree
        styledict = self.get_view(document, aggregateCSS)

        # Set inline style attribute if not one of the elements not worth styling
        ignore_list = ["html", "head", "title", "meta", "link", "script"]
        for element, style in styledict.items():
            if element.tag not in ignore_list:
                v = style.getCssText(separator="")
                element.set("style", v)

        if self.mediaRules:
            bodyTag = document.find("body")
            if bodyTag is not None:
                styleTag = etree.Element("style", type="text/css")
                styleTag.text = self.mediaRules
                bodyTag.insert(0, styleTag)

        if sourceURL:
            for attr in ("href", "src"):
                for item in document.xpath("//@%s" % attr):
                    parent = item.getparent()
                    if attr == "href" and parent.attrib[attr].startswith("#"):
                        continue
                    parent.attrib[attr] = urlparse.urljoin(
                        sourceURL, parent.attrib[attr]
                    )

        # convert tree back to plain text html
        self.convertedHTML = etree.tostring(
            document,
            method="html",
            xml_declaration=False,
            pretty_print=True,
            encoding="unicode",
        )
        self.convertedHTML = self.convertedHTML.replace(
            "&#13;", ""
        )  # tedious raw conversion of line breaks.

        return self

    def styleattribute(self, element):
        """
        returns css.CSSStyleDeclaration of inline styles, for html: @style
        """
        css_text = element.get("style")
        if css_text:
            return cssutils.css.CSSStyleDeclaration(cssText=css_text)
        else:
            return None

    def set_compliance_list(self):
        with open(
            os.path.join(os.path.dirname(__file__), "css_compliance.csv")
        ) as csv_file:
            compat_list = csv_file.readlines()

        mycsv = csv.DictReader(compat_list, delimiter=str(","))

        for row in mycsv:
            self.client_count = len(row) - 1
            self.compliance[row["property"].strip()] = dict(row)

    def test_compliance(self, p):
        for client, support in self.compliance[p.name].items():
            if support == "N" or support == "P":
                # Increment client failure count for this property
                self.supportratios[p.name]["failedClients"] += 1
                if p.name not in self.CSSUnsupportErrors:
                    if support == "P":
                        self.CSSUnsupportErrors[p.name] = [
                            client + " (partial support)"
                        ]
                    else:
                        self.CSSUnsupportErrors[p.name] = [client]
                else:
                    if support == "P":
                        self.CSSUnsupportErrors[p.name].append(
                            client + " (partial support)"
                        )
                    else:
                        self.CSSUnsupportErrors[p.name].append(client)

    def get_view(self, document, css):

        view = {}
        specificities = {}
        support_failrate = 0
        support_totalrate = 0

        self.set_compliance_list()

        # Decrement client count to account for first col which is property name

        sheet = cssutils.parseString(css)

        keep_rules = []
        rules = (rule for rule in sheet if rule.type in [rule.STYLE_RULE])
        for rule in rules:
            if any(
                pseudo in rule.selectorText
                for pseudo in [":hover", ":active", ":visited"]
            ):
                keep_rules.append(rule)
                continue

            for selector in rule.selectorList:
                try:
                    cssselector = CSSSelector(selector.selectorText)
                    matching = cssselector.evaluate(document)

                    for element in matching:
                        # add styles for all matching DOM elements
                        if element not in view:
                            # add initial
                            view[element] = cssutils.css.CSSStyleDeclaration()
                            specificities[element] = {}
                            # add inline style if present
                            inlinestyle = self.styleattribute(element)
                            if inlinestyle:
                                for p in inlinestyle:
                                    # set inline style specificity
                                    view[element].setProperty(p)
                                    specificities[element][p.name] = (1, 0, 0, 0)

                        for p in rule.style:
                            if p.name not in self.supportratios:
                                self.supportratios[p.name] = {
                                    "usage": 0,
                                    "failedClients": 0,
                                }

                            self.supportratios[p.name]["usage"] += 1

                            try:
                                if p.name not in self.CSSUnsupportErrors:
                                    self.test_compliance(p)
                            except KeyError:
                                pass

                            # update styles
                            if p not in view[element]:
                                view[element].setProperty(p.name, p.value, p.priority)
                                specificities[element][p.name] = selector.specificity
                            else:
                                sameprio = p.priority == view[
                                    element
                                ].getPropertyPriority(p.name)
                                if (
                                    not sameprio
                                    and bool(p.priority)
                                    or (
                                        sameprio
                                        and selector.specificity
                                        >= specificities[element][p.name]
                                    )
                                ):
                                    # later, more specific or higher prio
                                    view[element].setProperty(
                                        p.name, p.value, p.priority
                                    )
                                    specificities[element][
                                        p.name
                                    ] = selector.specificity

                except ExpressionError:
                    if text(sys.exc_info()[1]) not in self.CSSErrors:
                        self.CSSErrors.append(text(sys.exc_info()[1]))
                    pass

        rules = (rule.cssText.strip() for rule in keep_rules)
        self.mediaRules = "\n".join(rules)

        for props, propvals in self.supportratios.items():
            support_failrate += (propvals["usage"]) * int(propvals["failedClients"])
            support_totalrate += int(propvals["usage"]) * self.client_count

        if support_failrate and support_totalrate:
            self.supportPercentage = 100 - (
                (float(support_failrate) / float(support_totalrate)) * 100
            )
        return view
