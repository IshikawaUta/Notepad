"""Sanitize untrusted HTML (markdown output) before storage/display."""
from __future__ import annotations

import nh3

_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "code", "dd", "del",
    "details", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "kbd", "li", "mark",
    "ol", "p", "pre", "q", "rp", "rt", "ruby", "s", "samp", "section",
    "small", "span", "strong", "sub", "summary", "sup", "table", "tbody",
    "td", "tfoot", "th", "thead", "tr", "u", "ul", "var", "input",
}

_ATTRS = {
    "*": {"class", "id", "title", "dir", "lang"},
    "a": {"href", "target", "name", "title", "class", "id"},
    "img": {"src", "alt", "width", "height", "loading", "decoding", "title", "class", "id"},
    "p": {"align", "class", "id", "dir", "lang", "title"},
    "div": {"align", "class", "id", "dir", "lang", "title"},
    "td": {"colspan", "rowspan", "style", "align", "valign"},
    "th": {"colspan", "rowspan", "scope", "style", "align", "valign"},
    "ol": {"start", "type"},
    "ul": {"type"},
    "input": {"type", "checked", "disabled"},
}

_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def sanitize_html(html: str) -> str:
    if not html:
        return ""
    return nh3.clean(
        html,
        tags=_TAGS,
        attributes=_ATTRS,
        url_schemes=_URL_SCHEMES,
        url_relative="pass_through",
        link_rel="noopener noreferrer",
        strip_comments=True,
    )
