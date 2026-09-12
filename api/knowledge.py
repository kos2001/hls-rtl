"""Knowledge base over the repo — retrieval-grounded context for the agents.

Before this, every gateway request got the same fixed 1800-char digest
(`_design_digest`): parameters, the two handshake assigns, and a pass count.
That grounds "what is in_ready?" and nothing else. Ask about backpressure
profiles, the SystemC mirror, or why a pattern exists and the agent had to fall
back on session memory or invention.

This builds a chunked index of the design and its documents and retrieves the
chunks that actually match the question, within a character budget.

Why lexical (BM25) and not embeddings
-------------------------------------
The corpus is ~1300 lines. The queries are full of identifiers — `in_ready`,
`FIFO_DEPTH`, `BP_PROFILE`, `lut_wdata`, `test_lut_reload`. Embeddings blur
exactly those: `rd_ptr` and `wr_ptr` sit next to each other in vector space, and
retrieving the wrong one is worse than retrieving nothing. Exact-term matching is
the right tool for this corpus, and it needs no model, no API key, no network,
and no index-rebuild latency. If the corpus ever grows past a few thousand
chunks, revisit — not before.

Chunks are semantic units (an always-block, a function, a doc section), never
fixed-size windows, so a retrieved chunk is a thing an engineer would quote.
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[1]

# Files worth indexing, with the kind that drives chunking. Ordered by how
# authoritative they are when two chunks say different things.
SOURCES: Tuple[Tuple[str, str], ...] = (
    ("golden/gamma_golden.py", "python"),
    ("rtl/gamma.v", "verilog"),
    ("systemc/gamma_sc.h", "cpp"),
    ("systemc/gamma_sc.cpp", "cpp"),
    ("tb/test_set.py", "python"),
    ("tb/test_gamma.py", "python"),
    ("tb/stimulus.py", "python"),
    ("TESTPLAN.md", "markdown"),
    ("CLAUDE.md", "markdown"),
    ("README.md", "markdown"),
)

# Identifier-aware tokenizer: keep the whole identifier AND its parts, so
# "in_ready" matches a query for "ready" without losing exact-name precision.
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_SPLIT_RE = re.compile(r"_|(?<=[a-z0-9])(?=[A-Z])")

# The corpus is English; the engineers asking are often writing Korean. Without
# a bridge a Korean question tokenises to nothing and retrieval returns an empty
# set — worse than a bad match, because the agent then answers from memory with
# no signal that grounding failed. This maps the domain vocabulary that actually
# comes up; it is a glossary, not a translator, and unmapped Korean simply falls
# through to whatever Latin identifiers the question also contains.
KO_TERMS: Dict[str, Tuple[str, ...]] = {
    "감마": ("gamma",), "채널": ("channel", "lut"), "핸드셰이크": ("handshake", "ready", "valid"),
    "백프레셔": ("backpressure", "stall", "bp"), "역압": ("backpressure", "stall"),
    "지연": ("latency", "cycle"), "레이턴시": ("latency",), "처리율": ("throughput",),
    "파형": ("waveform", "vcd", "trace"), "회로도": ("schematic", "netlist"),
    "리셋": ("reset", "rst_n"), "초기화": ("reset", "init"),
    "포인터": ("ptr", "rd_ptr", "wr_ptr"), "점유": ("count", "occupancy", "depth"),
    "깊이": ("depth", "fifo_depth"), "폭": ("width", "pixel_w"),
    "패턴": ("pattern", "test_set"), "테스트": ("test", "testbench"),
    "검증": ("verification", "verify", "scoreboard"), "회귀": ("regression",),
    "스코어보드": ("scoreboard",), "골든": ("golden", "reference"),
    "합성": ("synthesis", "synth", "yosys"), "린트": ("lint", "verilator"),
    "정형": ("formal", "property"), "등가": ("equivalence", "equiv", "lec"),
    "커버리지": ("coverage",), "사인오프": ("signoff", "sign"), "판정": ("verdict", "status"),
    "해시": ("sha256", "hash"), "불일치": ("mismatch", "fail"), "일치": ("match", "exact"),
    "파라미터": ("parameter",), "모듈": ("module",), "신호": ("signal", "wire", "reg"),
    "메모리": ("mem", "memory"), "클럭": ("clk", "clock"), "픽셀": ("pixel", "px"),
    "입력": ("in", "input"), "출력": ("out", "output"), "계약": ("contract",),
    "시뮬레이터": ("simulator", "sim"), "이유": ("why", "rationale"),
}
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]+")

_STOP = frozenset("""
a an the and or of to in is are be for with on at as by from that this it its if
then else when we you i not no do does did can could should would will shall may
""".split())


def tokenize(text: str, *, expand_korean: bool = False) -> List[str]:
    """Lowercased identifier tokens, plus their sub-words.

    `expand_korean` is for QUERIES only — never for indexing. Expanding the
    corpus would inject English synonyms into chunks that never said them and
    quietly corrupt the document frequencies.
    """
    out: List[str] = []
    if expand_korean:
        for run in _HANGUL_RE.findall(text):
            for ko, en in KO_TERMS.items():
                if ko in run:
                    out.extend(en)
    for m in _WORD_RE.finditer(text):
        w = m.group(0).lower()
        if w in _STOP:
            continue
        out.append(w)
        if "_" in w or any(c.isupper() for c in m.group(0)[1:]):
            out.extend(p.lower() for p in _SPLIT_RE.split(m.group(0))
                       if len(p) > 1 and p.lower() not in _STOP)
    return out


@dataclass
class Chunk:
    id: str
    source: str          # repo-relative path, or "live:..." for computed state
    kind: str            # verilog | python | cpp | markdown | live
    title: str           # human label, e.g. "always @ fifo pointers"
    text: str
    start_line: int = 0
    end_line: int = 0
    pinned: bool = False  # always included, never ranked out
    tokens: List[str] = field(default_factory=list, repr=False)
    # Names this chunk DEFINES (assign LHS, def/class, declarations). Asking
    # "how is in_ready computed" should land on the chunk that drives it, not on
    # the longest chunk that happens to mention it.
    symbols: List[str] = field(default_factory=list, repr=False)

    @property
    def citation(self) -> str:
        if self.start_line:
            return f"{self.source}:{self.start_line}-{self.end_line}"
        return self.source

    def to_dict(self, include_text: bool = False) -> dict:
        d = {
            "id": self.id, "source": self.source, "kind": self.kind,
            "title": self.title, "citation": self.citation,
            "pinned": self.pinned, "chars": len(self.text),
        }
        if include_text:
            d["text"] = self.text
        return d


# --------------------------------------------------------------- chunking ----
def _md_chunks(path: str, text: str) -> List[Chunk]:
    """Split markdown on headings. A doc section is already the unit its author
    chose; re-cutting it by character count would strand the heading."""
    out: List[Chunk] = []
    cur_title, buf, start = Path(path).name, [], 1
    for i, line in enumerate(text.splitlines(), 1):
        if re.match(r"^#{1,4}\s+\S", line):
            if any(b.strip() for b in buf):
                out.append(Chunk(f"{path}#{len(out)}", path, "markdown", cur_title,
                                 "\n".join(buf).strip(), start, i - 1))
            cur_title = line.lstrip("# ").strip()
            buf, start = [line], i
        else:
            buf.append(line)
    if any(b.strip() for b in buf):
        out.append(Chunk(f"{path}#{len(out)}", path, "markdown", cur_title,
                         "\n".join(buf).strip(), start, len(text.splitlines())))
    return out


_V_BLOCK_RE = re.compile(r"^\s*(always\s*@|assign\s+|initial\b|generate\b|function\b|task\b)")


def _verilog_chunks(path: str, text: str) -> List[Chunk]:
    """One chunk per structural construct. The leading comment block is pinned
    separately — it is the module's stated contract, wanted for every question."""
    lines = text.splitlines()
    out: List[Chunk] = []

    header = []
    for line in lines:
        if line.startswith("//"):
            header.append(line)
        elif header:
            break
    if header:
        out.append(Chunk(f"{path}#contract", path, "verilog", "module contract header",
                         "\n".join(header), 1, len(header), pinned=True))

    # port list + parameters: the interface, also always relevant
    decl_end = next((i for i, l in enumerate(lines, 1) if l.strip().startswith(");")), 0)
    if decl_end:
        mod_start = next((i for i, l in enumerate(lines, 1)
                          if l.strip().startswith("module ")), 1)
        out.append(Chunk(f"{path}#ports", path, "verilog", "module declaration + parameters",
                         "\n".join(lines[mod_start - 1:decl_end]), mod_start, decl_end,
                         pinned=True))

    i = decl_end
    while i < len(lines):
        line = lines[i]
        if _V_BLOCK_RE.match(line) and not line.strip().startswith("//"):
            start = i + 1
            # walk back over the comment lines that introduce this block
            j = i - 1
            while j >= decl_end and lines[j].strip().startswith("//"):
                start = j + 1
                j -= 1
            end = i + 1
            depth = 0
            seen_block = False
            while end <= len(lines):
                seg = lines[end - 1]
                depth += len(re.findall(r"\bbegin\b", seg)) - len(re.findall(r"\bend\b(?!case|module|function|task|generate)", seg))
                if "begin" in seg:
                    seen_block = True
                if seen_block and depth <= 0 and end > i + 1:
                    break
                if not seen_block and seg.rstrip().endswith(";") and end > i:
                    break
                end += 1
            body = "\n".join(lines[start - 1:min(end, len(lines))])
            title = re.sub(r"\s+", " ", lines[i].strip())[:70]
            out.append(Chunk(f"{path}#{len(out)}", path, "verilog", title, body,
                             start, min(end, len(lines))))
            i = end
        else:
            i += 1
    return out


_PY_DEF_RE = re.compile(r"^(def |class |async def )")


def _python_chunks(path: str, text: str) -> List[Chunk]:
    """Top-level def/class bodies, with their decorators and docstring."""
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if _PY_DEF_RE.match(l)]
    out: List[Chunk] = []
    if not starts:
        return [Chunk(f"{path}#0", path, "python", Path(path).name, text, 1, len(lines))]

    head = "\n".join(lines[:starts[0]]).strip()
    if head:
        out.append(Chunk(f"{path}#head", path, "python", f"{Path(path).name} module header",
                         head, 1, starts[0]))
    for n, s in enumerate(starts):
        # pull in decorators sitting above the def
        top = s
        while top > 0 and lines[top - 1].lstrip().startswith("@"):
            top -= 1
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        while end > s and not lines[end - 1].strip():
            end -= 1
        title = lines[s].strip().rstrip(":")[:70]
        out.append(Chunk(f"{path}#{n}", path, "python", title,
                         "\n".join(lines[top:end]), top + 1, end))
    return out


_CPP_DEF_RE = re.compile(r"^[A-Za-z_].*\)\s*\{?\s*$|^(struct|class|SC_MODULE)\b")


def _cpp_chunks(path: str, text: str) -> List[Chunk]:
    """Brace-balanced top-level definitions. Headers are small here, so falling
    back to the whole file when nothing parses is acceptable."""
    lines = text.splitlines()
    out: List[Chunk] = []
    i = 0
    while i < len(lines):
        if _CPP_DEF_RE.match(lines[i]):
            start, depth, end = i, 0, i
            opened = False
            while end < len(lines):
                depth += lines[end].count("{") - lines[end].count("}")
                if "{" in lines[end]:
                    opened = True
                if opened and depth <= 0:
                    break
                end += 1
            out.append(Chunk(f"{path}#{len(out)}", path, "cpp",
                             lines[i].strip()[:70], "\n".join(lines[start:end + 1]),
                             start + 1, min(end + 1, len(lines))))
            i = end + 1
        else:
            i += 1
    if not out:
        out.append(Chunk(f"{path}#0", path, "cpp", Path(path).name, text, 1, len(lines)))
    return out


# LHS of a Verilog assign / declaration, a Python def-or-class, a C++ method.
_SYM_RES = (
    re.compile(r"^\s*assign\s+\{?([^=;]+?)\}?\s*=", re.M),
    re.compile(r"^\s*(?:reg|wire|logic|integer|localparam|parameter(?:\s+integer)?)\s+(?:signed\s+)?(?:\[[^\]]*\]\s*)?([A-Za-z_][A-Za-z0-9_]*)", re.M),
    re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M),
    re.compile(r"^\s*[A-Za-z_][\w:<>, ]*?\b([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{", re.M),
)


def _symbols_of(text: str) -> List[str]:
    out: List[str] = []
    for rx in _SYM_RES:
        for m in rx.finditer(text):
            for name in re.split(r"[,\s]+", m.group(1).strip()):
                name = name.strip()
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""):
                    out.append(name.lower())
    return sorted(set(out))


_CHUNKERS = {"markdown": _md_chunks, "verilog": _verilog_chunks,
             "python": _python_chunks, "cpp": _cpp_chunks}


def _live_chunks() -> List[Chunk]:
    """Computed state — the part of the knowledge base that is not a file.

    Pinned: "does it currently pass" is context for every question, and it is the
    fact most likely to be stale in an agent's session memory.
    """
    out: List[Chunk] = []
    try:
        res = json.loads((_ROOT / "frontend" / "public" / "results.json").read_text())
        s = res["summary"]
        d = res["design"]
        lines = [
            f"Current verification state: {s['passed']}/{s['total_patterns']} patterns "
            f"bit-exact, {s['failed']} failing, {s['total_pixels']} pixels compared.",
            f"Design: module {d['module']}, PIXEL_W={d['pixel_w']}, LUT_DEPTH={d['lut_depth']}.",
            "Per-channel gamma: " + ", ".join(f"{k}={v}" for k, v in res["gammas"].items()),
            "",
            "Patterns (name: pixels, mismatches; SystemC column skipped when "
            "build/sc_out.txt is absent):",
        ]
        for p in res["patterns"]:
            # When the hashes agree, printing all three is three copies of the
            # same hex string. Print one, and only break them out on a mismatch.
            agree = p["rtl_sha256"] == p["golden_sha256"]
            hashes = (f"sha={p['golden_sha256'][:10]}" if agree
                      else f"golden={p['golden_sha256'][:10]} rtl={p['rtl_sha256'][:10]} MISMATCH")
            sc = "" if p["sc_sha256"] else " sc=skipped"
            lines.append(f"  {p['name']}: {p['status']} {p['pixels']}px "
                         f"mism={p['mismatches']} {hashes}{sc}")
        lines.append("")
        lines.append("Note: this regression runs under Verilator (2-state). It does not "
                     "cover X-propagation or reset-initialization behaviour.")
        out.append(Chunk("live:verification", "live:verification", "live",
                         "current verification results", "\n".join(lines), pinned=True))
    except Exception:
        pass
    return out


# ------------------------------------------------------------------ index ----
@dataclass
class Index:
    chunks: List[Chunk]
    df: Counter                      # document frequency per term
    avg_len: float
    built_at: float
    signature: Tuple               # mtimes, for invalidation

    @property
    def pinned(self) -> List[Chunk]:
        return [c for c in self.chunks if c.pinned]


_index: Optional[Index] = None


def _signature() -> Tuple:
    sig = []
    for rel, _ in SOURCES:
        p = _ROOT / rel
        sig.append((rel, p.stat().st_mtime_ns if p.exists() else 0))
    live = _ROOT / "frontend" / "public" / "results.json"
    sig.append(("live", live.stat().st_mtime_ns if live.exists() else 0))
    return tuple(sig)


def build(force: bool = False) -> Index:
    """(Re)build the index. Cheap — the corpus is small — and invalidated by
    source mtime, so an edited RTL file is reflected on the next request."""
    global _index
    sig = _signature()
    if _index is not None and not force and _index.signature == sig:
        return _index

    chunks: List[Chunk] = []
    for rel, kind in SOURCES:
        p = _ROOT / rel
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chunks.extend(_CHUNKERS[kind](rel, text))
    chunks.extend(_live_chunks())

    # drop trivia (a lone `endmodule`, a blank section)
    chunks = [c for c in chunks if len(c.text.strip()) >= 40 or c.pinned]

    df: Counter = Counter()
    total = 0
    for c in chunks:
        c.tokens = tokenize(f"{c.title}\n{c.text}")
        c.symbols = _symbols_of(c.text)
        # A generate/always block titled just "generate" says nothing; naming the
        # signals it drives makes the title useful in a citation list too.
        if c.kind == "verilog" and c.symbols and len(c.title) < 24:
            c.title = f"{c.title} → {', '.join(c.symbols[:5])}"
        total += len(c.tokens)
        df.update(set(c.tokens))

    _index = Index(chunks=chunks, df=df,
                   avg_len=(total / len(chunks)) if chunks else 1.0,
                   built_at=time.time(), signature=sig)
    return _index


# --------------------------------------------------------------- retrieval ---
_K1, _B = 1.5, 0.75


def _bm25(query_tokens: Iterable[str], chunk: Chunk, idx: Index) -> float:
    tf = Counter(chunk.tokens)
    n = len(idx.chunks)
    dl = len(chunk.tokens) or 1
    score = 0.0
    for t in query_tokens:
        f = tf.get(t)
        if not f:
            continue
        # +0.5/+0.5 smoothing keeps a term that appears in most chunks from
        # going negative, which would let a common term *penalise* a match.
        idf = math.log(1 + (n - idx.df[t] + 0.5) / (idx.df[t] + 0.5))
        score += idf * (f * (_K1 + 1)) / (f + _K1 * (1 - _B + _B * dl / idx.avg_len))
    return score


@dataclass
class Retrieved:
    chunk: Chunk
    score: float


# How much one exact "this chunk defines that name" hit is worth. Tuned so a
# definition outranks a passing mention but cannot beat several strong BM25
# terms on its own.
_SYMBOL_BONUS = 4.0


def search(query: str, limit: int = 8) -> List[Retrieved]:
    idx = build()
    qt = tokenize(query, expand_korean=True)
    if not qt:
        return []
    qset = set(qt)
    scored = [(c, _bm25(qt, c, idx) + _SYMBOL_BONUS * len(qset & set(c.symbols)))
              for c in idx.chunks if not c.pinned]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return [Retrieved(c, round(s, 3)) for c, s in scored[:limit] if s > 0]


def context_for(query: str, *, budget: int = 9000, limit: int = 10) -> Tuple[str, List[dict]]:
    """Grounding block for a question, plus the citations that went into it.

    Pinned chunks go first and are never displaced: the module contract and the
    current pass/fail state are context for every question, and they are exactly
    what a stale session transcript gets wrong. Retrieved chunks fill whatever
    budget remains, best match first, and a chunk that does not fit whole is
    skipped rather than truncated mid-block — half an always-block is a good way
    to make an agent confidently describe logic that is not there.
    """
    idx = build()
    parts: List[str] = [
        "\n\n=== DESIGN KNOWLEDGE BASE (read from disk just now; authoritative) ===",
        "If your session memory conflicts with anything below, the below wins.",
        "Cite the [path:lines] label when you rely on a passage.",
    ]
    used: List[dict] = []
    spent = sum(len(p) for p in parts)

    def add(c: Chunk, score: Optional[float]) -> bool:
        nonlocal spent
        block = f"\n--- [{c.citation}] {c.title} ---\n{c.text.strip()}"
        if spent + len(block) > budget:
            return False
        parts.append(block)
        spent += len(block)
        d = c.to_dict()
        d["score"] = score
        used.append(d)
        return True

    for c in idx.pinned:
        add(c, None)
    for r in search(query, limit=limit):
        add(r.chunk, r.score)

    return "\n".join(parts), used


def stats() -> dict:
    idx = build()
    by_source: Dict[str, int] = {}
    for c in idx.chunks:
        by_source[c.source] = by_source.get(c.source, 0) + 1
    return {
        "chunks": len(idx.chunks),
        "pinned": len(idx.pinned),
        "terms": len(idx.df),
        "avg_chunk_tokens": round(idx.avg_len, 1),
        "sources": by_source,
        "built_at": idx.built_at,
        "retrieval": "bm25-lexical",
    }
