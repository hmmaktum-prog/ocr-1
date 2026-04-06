"""
Pure-Python DOCX writer — no lxml dependency.

Generates valid .docx (Office Open XML) files using only Python stdlib:
  - zipfile for the .docx container
  - xml.etree.ElementTree for XML generation

This replaces python-docx for Android builds where lxml cannot be compiled.
"""

import os
import re
import zipfile
import io
from xml.etree.ElementTree import Element, SubElement, tostring

# ── Office Open XML namespaces ────────────────────────────────────────────────

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"

# OOXML relationship types
RT_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
RT_STYLES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
RT_NUMBERING = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering"


def _el(tag, attrib=None, text=None, nsmap=None):
    """Create an Element with optional namespace prefix expansion."""
    e = Element(tag, attrib or {})
    if text is not None:
        e.text = text
    return e


def _sub(parent, tag, attrib=None, text=None):
    """Create a SubElement."""
    e = SubElement(parent, tag, attrib or {})
    if text is not None:
        e.text = text
    return e


def _xml_declaration(root_el):
    """Serialize an Element tree to UTF-8 bytes with XML declaration."""
    raw = tostring(root_el, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + raw).encode("utf-8")


# ── Minimal styles.xml ────────────────────────────────────────────────────────

def _build_styles_xml():
    """Generate a minimal styles.xml with heading + list styles."""
    root = Element(f"{{{NS_W}}}styles")
    root.set(f"xmlns:w", NS_W)

    # Default document font
    doc_defaults = _sub(root, f"{{{NS_W}}}docDefaults")
    rpd = _sub(doc_defaults, f"{{{NS_W}}}rPrDefault")
    rpr = _sub(rpd, f"{{{NS_W}}}rPr")
    _sub(rpr, f"{{{NS_W}}}rFonts", {
        f"{{{NS_W}}}ascii": "Calibri",
        f"{{{NS_W}}}hAnsi": "Calibri",
        f"{{{NS_W}}}cs": "Noto Sans Bengali",
    })
    _sub(rpr, f"{{{NS_W}}}sz", {f"{{{NS_W}}}val": "22"})

    # Normal style
    _add_style(root, "Normal", "paragraph", "Normal", font_size=22)

    # Heading styles
    for level in range(1, 4):
        sz = {1: 32, 2: 28, 3: 24}[level]
        _add_style(root, f"Heading{level}", "paragraph", f"heading {level}",
                   font_size=sz, bold=True)

    # List Bullet
    _add_style(root, "ListBullet", "paragraph", "List Bullet", font_size=22)

    # List Number  
    _add_style(root, "ListNumber", "paragraph", "List Number", font_size=22)

    # Table Grid style
    _add_style(root, "TableGrid", "table", "Table Grid", font_size=22, is_table=True)

    return _xml_declaration(root)


def _add_style(parent, style_id, style_type, name, font_size=22, bold=False, is_table=False):
    """Add a w:style element."""
    style = _sub(parent, f"{{{NS_W}}}style", {
        f"{{{NS_W}}}type": style_type,
        f"{{{NS_W}}}styleId": style_id,
    })
    _sub(style, f"{{{NS_W}}}name", {f"{{{NS_W}}}val": name})
    if not is_table:
        rpr = _sub(style, f"{{{NS_W}}}rPr")
        _sub(rpr, f"{{{NS_W}}}sz", {f"{{{NS_W}}}val": str(font_size)})
        _sub(rpr, f"{{{NS_W}}}szCs", {f"{{{NS_W}}}val": str(font_size)})
        if bold:
            _sub(rpr, f"{{{NS_W}}}b")
    else:
        tpr = _sub(style, f"{{{NS_W}}}tblPr")
        borders = _sub(tpr, f"{{{NS_W}}}tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            _sub(borders, f"{{{NS_W}}}{edge}", {
                f"{{{NS_W}}}val": "single",
                f"{{{NS_W}}}sz": "4",
                f"{{{NS_W}}}space": "0",
                f"{{{NS_W}}}color": "auto",
            })


# ── Document builder ──────────────────────────────────────────────────────────

class DocxDocument:
    """
    Minimal DOCX document builder.
    
    API is intentionally similar to python-docx's Document class:
        doc = DocxDocument()
        doc.add_heading("Title", level=1)
        doc.add_paragraph("Hello world")
        doc.add_table(rows=2, cols=3)
        doc.add_page_break()
        doc.save("output.docx")
    """

    def __init__(self):
        self._body_elements = []  # list of Element objects for w:body

    # ── Public API ────────────────────────────────────────────────────────

    def add_heading(self, text, level=1):
        """Add a heading paragraph."""
        p = Element(f"{{{NS_W}}}p")
        ppr = _sub(p, f"{{{NS_W}}}pPr")
        _sub(ppr, f"{{{NS_W}}}pStyle", {f"{{{NS_W}}}val": f"Heading{level}"})
        run = _sub(p, f"{{{NS_W}}}r")
        rpr = _sub(run, f"{{{NS_W}}}rPr")
        _sub(rpr, f"{{{NS_W}}}b")
        _sub(run, f"{{{NS_W}}}t", text=text).set("xml:space", "preserve")
        self._body_elements.append(p)
        return p

    def add_paragraph(self, text, style=None):
        """Add a paragraph with optional style (e.g. 'List Bullet')."""
        p = Element(f"{{{NS_W}}}p")
        if style:
            ppr = _sub(p, f"{{{NS_W}}}pPr")
            style_id = style.replace(" ", "")
            _sub(ppr, f"{{{NS_W}}}pStyle", {f"{{{NS_W}}}val": style_id})

            # Add bullet/number prefix for list styles
            if style == "List Bullet":
                run_prefix = _sub(p, f"{{{NS_W}}}r")
                _sub(run_prefix, f"{{{NS_W}}}t", text="• ").set("xml:space", "preserve")
            elif style == "List Number":
                # Numbering handled by caller usually, just prefix with dash
                pass

        if text:
            run = _sub(p, f"{{{NS_W}}}r")
            _sub(run, f"{{{NS_W}}}t", text=text).set("xml:space", "preserve")
        self._body_elements.append(p)
        return _ParagraphProxy(p)

    def add_table(self, rows, cols):
        """Add a table with the given dimensions. Returns a TableProxy."""
        tbl = Element(f"{{{NS_W}}}tbl")

        # Table properties with borders
        tpr = _sub(tbl, f"{{{NS_W}}}tblPr")
        _sub(tpr, f"{{{NS_W}}}tblStyle", {f"{{{NS_W}}}val": "TableGrid"})
        _sub(tpr, f"{{{NS_W}}}tblW", {
            f"{{{NS_W}}}w": "0",
            f"{{{NS_W}}}type": "auto",
        })
        borders = _sub(tpr, f"{{{NS_W}}}tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            _sub(borders, f"{{{NS_W}}}{edge}", {
                f"{{{NS_W}}}val": "single",
                f"{{{NS_W}}}sz": "4",
                f"{{{NS_W}}}space": "0",
                f"{{{NS_W}}}color": "000000",
            })

        # Grid columns
        grid = _sub(tbl, f"{{{NS_W}}}tblGrid")
        col_width = 9000 // cols  # distribute evenly (in twips)
        for _ in range(cols):
            _sub(grid, f"{{{NS_W}}}gridCol", {f"{{{NS_W}}}w": str(col_width)})

        # Rows & cells
        table_data = []
        for r in range(rows):
            tr = _sub(tbl, f"{{{NS_W}}}tr")
            row_cells = []
            for c in range(cols):
                tc = _sub(tr, f"{{{NS_W}}}tc")
                tcp = _sub(tc, f"{{{NS_W}}}tcPr")
                _sub(tcp, f"{{{NS_W}}}tcW", {
                    f"{{{NS_W}}}w": str(col_width),
                    f"{{{NS_W}}}type": "dxa",
                })
                # Every cell must have at least one paragraph
                p = _sub(tc, f"{{{NS_W}}}p")
                row_cells.append(_CellProxy(tc, p))
            table_data.append(row_cells)

        self._body_elements.append(tbl)
        return _TableProxy(table_data, rows, cols)

    def add_page_break(self):
        """Add a page break."""
        p = Element(f"{{{NS_W}}}p")
        run = _sub(p, f"{{{NS_W}}}r")
        _sub(run, f"{{{NS_W}}}br", {f"{{{NS_W}}}type": "page"})
        self._body_elements.append(p)

    def save(self, path):
        """Save the document as a .docx file."""
        buf = self._build_docx_bytes()
        with open(path, "wb") as f:
            f.write(buf)

    # ── Internal ──────────────────────────────────────────────────────────

    def _build_docx_bytes(self):
        """Build the complete .docx ZIP archive in memory."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # [Content_Types].xml
            zf.writestr("[Content_Types].xml", self._content_types())

            # _rels/.rels
            zf.writestr("_rels/.rels", self._root_rels())

            # word/_rels/document.xml.rels
            zf.writestr("word/_rels/document.xml.rels", self._doc_rels())

            # word/styles.xml
            zf.writestr("word/styles.xml", _build_styles_xml())

            # word/document.xml
            zf.writestr("word/document.xml", self._document_xml())

        return buf.getvalue()

    def _content_types(self):
        types = Element("Types")
        types.set("xmlns", NS_CT)
        _sub(types, "Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
        _sub(types, "Default", {"Extension": "xml", "ContentType": "application/xml"})
        _sub(types, "Override", {
            "PartName": "/word/document.xml",
            "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        })
        _sub(types, "Override", {
            "PartName": "/word/styles.xml",
            "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml",
        })
        return _xml_declaration(types)

    def _root_rels(self):
        rels = Element("Relationships")
        rels.set("xmlns", NS_REL)
        _sub(rels, "Relationship", {
            "Id": "rId1",
            "Type": RT_DOC,
            "Target": "word/document.xml",
        })
        return _xml_declaration(rels)

    def _doc_rels(self):
        rels = Element("Relationships")
        rels.set("xmlns", NS_REL)
        _sub(rels, "Relationship", {
            "Id": "rId1",
            "Type": RT_STYLES,
            "Target": "styles.xml",
        })
        return _xml_declaration(rels)

    def _document_xml(self):
        doc = Element(f"{{{NS_W}}}document")
        doc.set(f"xmlns:w", NS_W)
        doc.set(f"xmlns:r", NS_R)

        body = _sub(doc, f"{{{NS_W}}}body")
        for el in self._body_elements:
            body.append(el)

        return _xml_declaration(doc)


# ── Proxy objects (mimic python-docx API) ─────────────────────────────────────

class _ParagraphProxy:
    """Mimics python-docx Paragraph for alignment setting."""
    def __init__(self, p_element):
        self._p = p_element
        self._alignment = None

    @property
    def alignment(self):
        return self._alignment

    @alignment.setter
    def alignment(self, value):
        self._alignment = value
        if value is not None:
            # Find or create pPr
            ppr = self._p.find(f"{{{NS_W}}}pPr")
            if ppr is None:
                ppr = Element(f"{{{NS_W}}}pPr")
                self._p.insert(0, ppr)
            align_map = {0: "left", 1: "center", 2: "right", 3: "both"}
            val = align_map.get(value, "left")
            jc = ppr.find(f"{{{NS_W}}}jc")
            if jc is None:
                _sub(ppr, f"{{{NS_W}}}jc", {f"{{{NS_W}}}val": val})
            else:
                jc.set(f"{{{NS_W}}}val", val)


class _CellProxy:
    """Mimics python-docx table Cell."""
    def __init__(self, tc_element, p_element):
        self._tc = tc_element
        self._p = p_element
        self._text = ""

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value
        # Clear existing runs and set new text
        for run_el in self._p.findall(f"{{{NS_W}}}r"):
            self._p.remove(run_el)
        if value:
            run = _sub(self._p, f"{{{NS_W}}}r")
            t = _sub(run, f"{{{NS_W}}}t", text=value)
            t.set("xml:space", "preserve")


class _TableProxy:
    """Mimics python-docx Table for cell access."""
    def __init__(self, data, rows, cols):
        self._data = data
        self._rows = rows
        self._cols = cols
        self.style = "Table Grid"

    def cell(self, row, col):
        return self._data[row][col]


# ── Alignment constants (mimic python-docx WD_ALIGN_PARAGRAPH) ────────────────

class WD_ALIGN_PARAGRAPH:
    LEFT = 0
    CENTER = 1
    RIGHT = 2
    JUSTIFY = 3
