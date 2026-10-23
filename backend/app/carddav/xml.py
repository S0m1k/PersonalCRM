"""
XML WebDAV/CardDAV: разбор запросов PROPFIND/REPORT и сборка ответов 207 Multi-Status.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Callable, Optional

DAV = "DAV:"
CARD = "urn:ietf:params:xml:ns:carddav"
CS = "http://calendarserver.org/ns/"

ET.register_namespace("d", DAV)
ET.register_namespace("card", CARD)
ET.register_namespace("cs", CS)


def q(ns: str, name: str) -> str:
    """Имя в нотации ElementTree: {ns}name."""
    return f"{{{ns}}}{name}"


# Значение свойства: функция, которая дописывает содержимое в готовый элемент свойства
PropValue = Callable[[ET.Element], None]


def text(value: str) -> PropValue:
    def fill(el: ET.Element) -> None:
        el.text = value

    return fill


def href(value: str) -> PropValue:
    def fill(el: ET.Element) -> None:
        ET.SubElement(el, q(DAV, "href")).text = value

    return fill


def children(*names: str) -> PropValue:
    """Пустые дочерние элементы, напр. resourcetype → <d:collection/><card:addressbook/>."""

    def fill(el: ET.Element) -> None:
        for name in names:
            ET.SubElement(el, name)

    return fill


def privileges(*names: str) -> PropValue:
    def fill(el: ET.Element) -> None:
        for name in names:
            ET.SubElement(ET.SubElement(el, q(DAV, "privilege")), q(DAV, name))

    return fill


def reports(*names: str) -> PropValue:
    def fill(el: ET.Element) -> None:
        for name in names:
            report = ET.SubElement(ET.SubElement(el, q(DAV, "supported-report")), q(DAV, "report"))
            ET.SubElement(report, name)

    return fill


def address_data_types() -> PropValue:
    def fill(el: ET.Element) -> None:
        ET.SubElement(el, q(CARD, "address-data-type"), {"content-type": "text/vcard", "version": "3.0"})

    return fill


def requested_props(body: bytes) -> Optional[list[str]]:
    """Список запрошенных свойств; None — allprop / пустое тело (вернуть всё)."""
    if not body.strip():
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    prop = root.find(q(DAV, "prop"))
    if prop is None:
        return None
    return [child.tag for child in prop]


def multiget_hrefs(root: ET.Element) -> list[str]:
    return [el.text.strip() for el in root.findall(q(DAV, "href")) if el.text]


def parse(body: bytes) -> Optional[ET.Element]:
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        return None


class MultiStatus:
    def __init__(self) -> None:
        self.root = ET.Element(q(DAV, "multistatus"))

    def add(self, path: str, available: dict[str, PropValue], wanted: Optional[list[str]]) -> None:
        """Ответ для ресурса: найденные свойства — 200, неизвестные — 404 (как требует RFC 4918)."""
        response = ET.SubElement(self.root, q(DAV, "response"))
        ET.SubElement(response, q(DAV, "href")).text = path
        names = list(available) if wanted is None else wanted
        found = [n for n in names if n in available]
        missing = [n for n in names if n not in available]
        if found:
            self._propstat(response, found, available, "HTTP/1.1 200 OK")
        if missing:
            self._propstat(response, missing, {}, "HTTP/1.1 404 Not Found")

    def add_missing(self, path: str) -> None:
        response = ET.SubElement(self.root, q(DAV, "response"))
        ET.SubElement(response, q(DAV, "href")).text = path
        ET.SubElement(response, q(DAV, "status")).text = "HTTP/1.1 404 Not Found"

    @staticmethod
    def _propstat(response: ET.Element, names: list[str], values: dict[str, PropValue], status: str) -> None:
        propstat = ET.SubElement(response, q(DAV, "propstat"))
        prop = ET.SubElement(propstat, q(DAV, "prop"))
        for name in names:
            el = ET.SubElement(prop, name)
            if name in values:
                values[name](el)
        ET.SubElement(propstat, q(DAV, "status")).text = status

    def to_bytes(self) -> bytes:
        return ET.tostring(self.root, encoding="utf-8", xml_declaration=True)
