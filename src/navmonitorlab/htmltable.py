"""Read tables out of HTML with the standard library only.

Cells keep their text and any footnote markers (<sup>) separately, because both published sources mark
caveats with superscripts and those must not leak into numbers or names.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_WS = re.compile(r"\s+")


def clean(text: str) -> str:
    return _WS.sub(" ", text.replace(" ", " ")).strip()


@dataclass
class Cell:
    text: str = ""
    sup: str = ""
    is_header: bool = False


@dataclass
class Table:
    rows: list[list[Cell]] = field(default_factory=list)
    attrs: dict = field(default_factory=dict)

    def texts(self) -> list[list[str]]:
        return [[c.text for c in r] for r in self.rows]


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self._stack: list[Table] = []      # open tables (handles nesting; cells go to the innermost)
        self._row: list[Cell] | None = None
        self._cell: Cell | None = None
        self._buf: list[str] = []
        self._sup: list[str] = []
        self._in_sup = 0
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            t = Table(attrs=dict(attrs)); self._stack.append(t); self.tables.append(t)
        elif tag == "tr" and self._stack:
            self._close_cell(); self._close_row(); self._row = []
        elif tag in ("td", "th") and self._stack:
            self._close_cell()
            if self._row is None:
                self._row = []
            self._cell = Cell(is_header=(tag == "th")); self._buf = []; self._sup = []
        elif tag == "sup":
            self._in_sup += 1
        elif tag in ("br", "p", "li", "div", "tr", "h1", "h2", "h3"):
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "sup":
            self._in_sup = max(0, self._in_sup - 1)
        elif tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_cell(); self._close_row()
        elif tag == "table" and self._stack:
            self._close_cell(); self._close_row(); self._stack.pop()
        if tag in ("p", "li", "div", "tr", "h1", "h2", "h3", "ul", "table"):
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self._cell is not None:
            (self._sup if self._in_sup else self._buf).append(data)
        if not self._in_sup:
            self.text_parts.append(data)

    def _close_cell(self):
        if self._cell is not None and self._row is not None:
            self._cell.text = clean("".join(self._buf)); self._cell.sup = clean("".join(self._sup))
            self._row.append(self._cell)
        self._cell = None

    def _close_row(self):
        if self._row and self._stack:
            self._stack[-1].rows.append(self._row)
        self._row = None


def parse(html: str) -> tuple[list[Table], str]:
    """All tables in document order, plus the page text with one line per block element."""
    p = _Parser(); p.feed(html); p.close()
    lines = [clean(x) for x in "".join(p.text_parts).split("\n")]
    return p.tables, "\n".join(x for x in lines if x)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9%]+", "", s.lower())


def find_table(tables: list[Table], required: dict[str, list[str]]) -> tuple[Table, int, dict[str, int]] | None:
    """Locate the table whose header row carries every required column.

    `required` maps a field name to acceptable header spellings. Returns the table, the index of its
    header row, and field -> column index. Matching ignores case, spacing and punctuation, so
    "Fair Value ($m)", "Fair Value($m)" and "Fair Value" can all be listed as aliases.
    """
    for t in tables:
        for i, row in enumerate(t.rows[:5]):
            heads = [_norm(c.text) for c in row]
            cols: dict[str, int] = {}
            for name, aliases in required.items():
                for a in aliases:
                    if _norm(a) in heads:
                        cols[name] = heads.index(_norm(a)); break
            if len(cols) == len(required):
                return t, i, cols
    return None
