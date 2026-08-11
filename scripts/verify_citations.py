#!/usr/bin/env python3
"""Verify `path:line @ 863e313` citations in study notes against the baseline tree.

The project's evidence standard is: every assertion about hermes-agent behavior is
followed by `path:line @ <commit>` and a verbatim excerpt, so that reading the
note *is* the verification. That only holds if the line numbers are right.

R7B found 5 line-number offsets by hand-sampling. This script checks every
citation that is immediately followed by an excerpt block:

  1. Parse citations of the form  path:N  or  path:N-M  (optionally ` @ <sha>`),
     appearing inside backticks or bold, at the end of a line.
  2. If the next non-blank line opens an excerpt block, take the block's first
     non-blank line as the expected source line. Two block forms count:
       - a fenced block  ```...```   — the code side (contract: verbatim source);
       - a blockquote    > ...       — the doc side (see "Two block kinds" below).
  3. Compare (whitespace-normalized) against the baseline file at line N.
     If it doesn't match, search +/- WINDOW lines and report the actual offset.

Exit status is 1 if any citation MISMATCHES or points at a missing file/line.
Citations without a following block are counted as UNCHECKED, not failures —
many are prose references to a region, which is legitimate.

Two block kinds, two strictnesses (review-1 M-16a)
--------------------------------------------------
Until R8-fix this script only looked at fenced blocks, so the *code* side of every
doc-vs-code ruling was machine-checked while the *doc* side — which is written as a
`>` blockquote, essentially always — was never checked by anything. A first-pass
review sampling that blind spot hit 5 drifted anchors out of 5 sampled. So
blockquotes are now checked too, but under a deliberately weaker rule:

  - **Fence**: contract is "verbatim source excerpt". Not matching at the cited
    line is a MISMATCH whether or not the text is found elsewhere.
  - **Blockquote**: the corpus uses `>` for verbatim doc excerpts *and* for
    paraphrase. So a blockquote is only failed when its text is found VERBATIM at
    some other line of the cited file within the window — that proves it is a real
    excerpt that is merely mis-anchored. Text found nowhere nearby is treated as
    paraphrase and recorded UNCHECKED. This catches anchor drift without
    manufacturing failures out of every paraphrased quote.

Declared non-source fences
--------------------------
A fenced block whose info string is in NON_SOURCE_LANGS (`text`, `console`,
`verify`, `shell-session`) is a shell transcript, a judgement table, a checklist —
not a source excerpt — and is recorded UNCHECKED. This is an *author declaration*,
not a heuristic sniff: the alternative considered (guessing "this doesn't look like
code") would quietly weaken the gate, which is the one thing a blocking gate must
not do.

Table-row anchors (R9B, closes H-R9A-h)
---------------------------------------
The pairing rule above is "citation, then the block that FOLLOWS it". A Markdown
table row cannot be followed by a block — the next line is the next row — so every
anchor written inside a table was recorded UNCHECKED and *never compared to
anything*. That is 1,569 anchors, 10.1% of the corpus, including the handoff
tables every round hands its successor. The two one-line drifts R8D shipped
(`hermes_cli/env_loader.py:667`, real line 666) survived exactly here, and so had
R9A's own handoff row for H-R9A-d.

A table row carries its excerpt INLINE instead, and it does so in one recognisable
shape: the anchor, then the excerpt right after it —

    `hermes_cli/commands.py:1275`:`_SLACK_VIA_HERMES_ONLY = frozenset({...})`
    `gateway/relay/media.py:92` 的 `is_relay_media_url`

`declared_excerpt()` pairs an anchor with that following span and nothing else.
The first draft of this check compared the anchor against EVERY backticked span
in the row; on this corpus that produced 55 hits of which roughly three quarters
were a cell naming a symbol that merely occurs elsewhere in the file. Guessing
which mention an anchor "meant" is how a gate turns into noise, and NON_SOURCE_LANGS
above already settled the principle for this script: declared, not sniffed.

Given a declared excerpt, the verdict follows the blockquote philosophy — fail only
when the text is found verbatim somewhere else nearby, which proves a real excerpt
that is merely mis-anchored:

  - text found in [start, max(end, start+TABLE_BAND)]         -> TABLE-OK
  - text is on a def/class header the anchor sits inside      -> TABLE-OK
  - text found within +/- WINDOW but neither of the above     -> TABLE-DRIFT (fatal)
  - line number past EOF                                      -> TABLE-OUT-OF-RANGE (fatal)
  - text found nowhere near, or no declared excerpt           -> TABLE-UNCHECKED

The two TABLE-OK routes are the two honest ways a cell points at code. TABLE_BAND
covers `path:N` naming a construct whose body the excerpt is a few lines into;
`enclosing_headers()` covers the reverse — the cell names the *enclosing* function
while the anchor points inside its body (`hermes_cli/mcp_config.py:95` annotated
`_save_mcp_server`, whose `def` is at :88). Neither can mask the shape this check
exists for, because a drifted anchor's true line is an ordinary statement, not a
header above it: the self-test in the R9B report drifts an anchor by 1 line and by
20 lines inside the same function, and both are still caught.

Unlike the two earlier gates (citations R7C->R8A, BLOCK-DRIFT R8C->R8D) this one is
blocking from the round it lands, because its backlog was cleaned in the same
round it was written — the phased rollout those two needed exists to avoid a gate
that shouts about a pre-existing mess, and there is no mess left to shout about.

What this does NOT cover: an anchor written as bare prose in a cell (no declared
excerpt) is still UNCHECKED, and that is most of them — 1,623 of 1,710. The gate
raises the floor from "no table anchor is ever checked" to "a table anchor that
declares what it points at is checked"; CLAUDE.md makes the declared shape
mandatory for handoff tables, which is where the drift actually costs a round.

Table anchors are tallied and reported SEPARATELY from the block-backed citations.
Folding ~1,700 mostly-prose table cells into the main total would move 可校验比例
by ~30 points for reasons that have nothing to do with evidence quality, and that
number is a cross-round metric.

With --fix, a MISMATCH whose block is found at exactly one nearby line is
rewritten in place to the true line number (a `N-M` range is shifted by the same
delta, preserving its length). Ambiguous or not-found cases are never touched —
they are left for a human. Always re-run without --fix afterwards to confirm.

Per-file UNCHECKED ratio hint (R8C)
-----------------------------------
UNCHECKED is not a failure, and legitimately so: a prose reference to a region is
a valid thing to write. But UNCHECKED is also exactly what a *layout* mistake
looks like from in here. The gate pairs a citation with the block that FOLLOWS
it; an author who puts the anchor *after* its code block produces a file whose
every citation is UNCHECKED, and the gate says OK. That is the failure mode this
hint exists to surface: when a single file is at or above UNCHECKED_HINT_RATIO
(and carries at least UNCHECKED_HINT_MIN citations, so a 1-of-1 file cannot trip
it), the run prints a "疑似锚点排版不合规" note naming the file.

It is a HINT, not a failure — it does not change the exit code. A file can
legitimately be nearly all prose. Making it blocking would push authors to
manufacture code blocks to clear a gate, which is worse than the disease.

The run also prints 可校验比例 = OK / (OK + UNCHECKED + failures), the metric R8A
put a 70% floor under. The floor is a reporting standard, not a script gate:
the script computes and prints the number so the round report cannot fudge it.

Usage:
    python3 scripts/verify_citations.py <baseline_repo> <note.md> [note.md ...]
    python3 scripts/verify_citations.py /home/user/hermes-agent notes/r7c-*.md
    python3 scripts/verify_citations.py --fix /home/user/hermes-agent notes/r7c-*.md
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mandatory_scope import format_scope, resolve, take_round_args  # noqa: E402

WINDOW = 40  # how far to search for the real location when a citation misses
STUDY_ROOT = Path(__file__).resolve().parent.parent  # this study repo

# How far past a table anchor an inline token may sit and still count as "at" it.
# Covers the cell-names-the-construct shape (anchor inside a body whose header the
# cell names). See "Table-row anchors" in the module docstring.
TABLE_BAND = 12
TABLE_MIN_TOKEN = 4  # shorter backticked spans are too common to prove anything
TABLE_MAX_HITS = 2   # a token matching more lines than this identifies nothing

# Per-file UNCHECKED-ratio hint (see module docstring). Non-blocking.
UNCHECKED_HINT_RATIO = 0.90
UNCHECKED_HINT_MIN = 5  # below this many citations the ratio says nothing
VERIFIABLE_FLOOR = 0.70  # R8A's reporting floor for OK / all citations

# Extensions an anchor may carry (R10B / H-R10-a).
#
# Until R10B this read `py|md|yaml|yml|toml|c|sh|json|ts|tsx|js`. An anchor whose
# extension was not on it did not become UNCHECKED — it was not recognised as a
# citation *at all*, so it was neither verified nor counted, which is strictly
# more hidden than UNCHECKED. A full-corpus scan
# (`data/r10b/probes/cite_ext_scan.py`) found 17 such anchors in 8 distinct paths
# (.h 13 / .mjs 2 / .nix 2) plus a second gap H-R10-a had not named: 6 `.mdx`
# anchors into `website/docs/` — the very tree CLAUDE.md designates as the
# author's self-drawn map, i.e. the doc side of every ▲ ruling — and 1 `.txt`.
#
# Ordering is longest-first (`mdx` before `md`, `tsx` before `ts`, `mjs` before
# `js`) so the alternation cannot settle on a prefix.
# R11D adds ps1|css|tsv (closes H-R11C-D-a). R11C's full-corpus resolution census
# found 16 anchors that resolve from the repo root yet were not treated as anchors
# at all — 14 `scripts/install.ps1`, 1 `apps/desktop/src/styles.css`, 1 self-citing
# `data/ledger.tsv` — i.e. the state R10B named as strictly more hidden than
# UNCHECKED: they never even entered the denominator. None of the three is a ccTLD,
# so none needs the `sh|js|rs` guard below.
CITE_EXTS = "py|mdx|md|yaml|yml|toml|c|h|sh|json|tsx|ts|mjs|js|nix|rs|txt|ps1|css|tsv"

# `gateway/run.py:1234 @ 863e313`  /  **`cron/jobs.py:10-20`**  /  path:1234
#
# The leading `\.?` is the sibling defect the same note reported alongside
# H-R10-a: the path had to start with a word character, so `.github/…` was
# parsed as `github/…`, which resolves nowhere — a dot-directory anchor could
# never be verified. Measured on the whole corpus, allowing the dot changes the
# parse of exactly 2 occurrences and both go from unresolvable to resolvable.
CITE = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:" + CITE_EXTS + r"))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)

# `sqlite.org:443` is shaped exactly like `path:line`, and H-R10-a warned that a
# naive widening would start "verifying" hostnames. The extension whitelist is
# the primary defence and it holds: the same corpus scan finds 49 host:port-ish
# tokens (`127.0.0.1:18789` x31, `sqlite.org:443` x4, `api.openai.com:443`,
# `homeassistant.local:8123`, `x.test:80`, even `n.lineno:4`) and **not one** of
# them ends in a whitelisted extension.
#
# Three whitelisted extensions are nevertheless also ccTLDs, so keep a second,
# declared guard for exactly that overlap: `name.sh:N` with no directory part is
# genuinely ambiguous between a script and a Saint-Helena hostname, and no rule
# can separate them from the text alone. Such a token counts as a citation only
# when it shows one more bit of evidence that it names a file — a `/`, or a `_`,
# or it resolves in one of the two trees. Measured blast radius on the corpus at
# the time this landed: exactly one anchor, `build.sh:4-6` in
# notes/r10-raw-native-vendor.md, which was a real citation written without its
# directory; it was qualified to `native/fts5_cjk/build.sh:4-6` in the same
# commit rather than left for the guard to hide. Dropping a real anchor would
# reintroduce, in miniature, the exact invisibility this change exists to remove.
TLD_LIKE_EXTS = {"sh", "js", "rs"}


def is_path_citation(m, resolve) -> bool:
    """False when *m* is more plausibly a `host:port` than a `path:line`."""
    path = m.group("path")
    if path.rsplit(".", 1)[-1].lower() not in TLD_LIKE_EXTS:
        return True
    if "/" in path or "_" in path:
        return True
    return resolve(path).is_file()


# ---------------------------------------------------------------------------
# Extensionless anchors (R11A / H-R10B-a)
#
# The whitelist above is *structurally* incapable of reaching `.gitignore:3`,
# `Dockerfile:12` or `docker/s6-rc.d/main-hermes/run:23-26`: there is no
# extension to whitelist. Those anchors sat in exactly the state H-R10-a called
# "more hidden than UNCHECKED" — not verified, and not counted either, so they
# did not even show up as a gap in the numbers the gate prints.
#
# H-R10B-a states the fix must be an explicit filename list rather than a
# looser regex. That is a design assertion, so it gets a measurement:
# `data/r11a/probes/extless_name_census.py` runs the sniffed alternative
# ("accept `word:digits` for any extensionless basename at 863e313") over the
# whole corpus. It captures 26 real anchors and **one** string that is not an
# anchor at all — `base:645` in reports/round-5, a shorthand for a `base.py`
# line that resolves nowhere. One bad catch out of 27 is not a disaster, but it
# is the wrong bad catch: `base`, `run`, `type`, `finish` and `dashboard` are
# all real files at 863e313 (s6-rc service directories under `docker/s6-rc.d/`)
# *and* ordinary English words, so the sniffed variant's error rate is a
# property of this corpus's vocabulary, not a bound.
#
# So: declare the names, and guard the ambiguous ones the same way the ccTLD
# overlap above is guarded — a token counts only when it shows one more bit of
# evidence that it names a file.
#
# The list is every extensionless basename that exists at 863e313, minus the
# three `contributors/emails/*` entries, which contain `@` and therefore cannot
# be written as a path anchor in the first place. Names NOT at 863e313
# (`CODEOWNERS`, `.editorconfig`, `.env`) are deliberately left out: the
# baseline is pinned and never moves, so a name that is not in it can only ever
# add false-positive surface.
EXTLESS_NAMES = frozenset({
    # dotfiles
    ".dockerignore", ".envrc", ".gitattributes", ".gitignore", ".gitkeep",
    ".mailmap", ".nojekyll", ".npmrc", ".nvmrc", ".prettierignore",
    ".prettierrc", ".python-version",
    # build / legal
    "Dockerfile", "LICENSE", "Makefile", "NOTICE",
    # container init and s6-rc service directories (docker/)
    "015-supervise-perms", "02-reconcile-profiles",
    "base", "dashboard", "finish", "hermes", "hermes-gateway",
    "main-hermes", "run", "type",
})

# Longest-first so the alternation cannot settle on a prefix (`hermes` must not
# win over `hermes-gateway`).
_EXTLESS_ALT = "|".join(
    re.escape(n) for n in sorted(EXTLESS_NAMES, key=len, reverse=True)
)

# `docker/s6-rc.d/main-hermes/run:23-26`  /  `.gitignore:3`  /  `Dockerfile:12`
#
# The lookbehind is load-bearing in a way the dotted `CITE` never needed: with
# no extension to anchor on, `notbase:5` would otherwise match its `base:5`
# tail. `CITE` gets away without one because a dotted suffix already pins the
# right-hand edge of the token.
CITE_EXTLESS = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(?P<path>(?:\.?[A-Za-z0-9_][A-Za-z0-9_.-]*/)*(?:" + _EXTLESS_ALT + r"))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?"
)


def is_extless_citation(m, resolve) -> bool:
    """False when *m* is more plausibly prose than a `path:line`.

    Same shape as `is_path_citation`: a directory component, or the token
    resolves to a real file. `docker/s6-rc.d/main-hermes/run:23-26` passes on
    the first test and `LICENSE:5` on the second; bare `base:645` fails both,
    because nothing named `base` sits at either repo's root — every `base` at
    863e313 is nested under `docker/s6-rc.d/*/dependencies.d/`.
    """
    path = m.group("path")
    if "/" in path:
        return True
    return resolve(path).is_file()


def citations(text: str, resolve):
    """Every citation in *text*, host:port and prose lookalikes removed.

    Sorted by position because callers rely on document order — `check_note`
    takes `cands[-1]` as "the citation the following block belongs to".
    """
    found = [m for m in CITE.finditer(text) if is_path_citation(m, resolve)]
    found += [m for m in CITE_EXTLESS.finditer(text) if is_extless_citation(m, resolve)]
    found.sort(key=lambda m: m.start())
    return found


def any_anchor(text: str):
    """An anchor of either kind, without the resolve-dependent guards.

    Used where the question is only "is this token an anchor rather than an
    excerpt", so the guards would be noise.
    """
    return CITE.search(text) or CITE_EXTLESS.search(text)
FENCE = re.compile(r"^\s*```(?P<lang>[A-Za-z0-9_+-]*)")
QUOTE = re.compile(r"^\s*>\s?(?P<body>.*)$")

# Fences the author has declared to be something other than a source excerpt.
NON_SOURCE_LANGS = {"text", "console", "verify", "shell-session"}

# Notes sometimes open a fenced block with a locator comment naming the source,
# e.g. `# gateway/shutdown_flush.py:228-249`. That is annotation, not source —
# skip it and compare against the first real line of the excerpt.
LOCATOR = re.compile(
    r"^\s*(?:#|//|--)\s*(?:"
    r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.\w+"          # dotted path
    r"|(?:\.?[A-Za-z0-9_][A-Za-z0-9_.-]*/)*(?:" + _EXTLESS_ALT + r")"  # extensionless
    r"):\d+"
)

_SRC_CACHE: dict = {}

# --- 自引锚点的 commit 钉子(R11D 立) ---------------------------------------
#
# 基线锚点写作 `路径:行号 @ 863e313`,后面那个 sha 把它**钉死**了:基线只读且永不移动,
# 所以锚点永远有效。而**指向本学习仓库自己的锚点没有任何钉子** —— 它浮在一棵会动的树上。
# 实测规模:全语料 615 处自引锚点,其中 **101 处指向 `chapters/`**
# (`data/r11d/probes/self_citation_census.py`)。R11D 只改了 `chapters/r1` 的几个数,
# 当场打断 7 处;R12 装订要重排全部 21 章,那 101 处会一起断。
#
# 于是给自引锚点开同一个语法:`chapters/r1-what-is-hermes-agent.md:103 @ 82069d6`
# 表示「这一段引的是 82069d6 那一版」,校验器用 `git show` 取那一版来比对。
# 引用一段**后来被有意改掉**的文字时,这是唯一能同时做到两件事的写法:
# 保住原始证据(不把过去改写成对的),又保住可校验性(不退回 UNCHECKED)。
#
# 只对**本仓库路径**生效:`@ 863e313` 指的是基线仓库,在本仓库里 rev-parse 不出来,
# 于是自动退回原行为 —— 存量语料一行都不用改。
_PIN_CACHE: dict = {}
PIN = re.compile(r"\A[\s,]*@\s*(?P<sha>[0-9a-f]{7,40})")


def _pin_exists(sha: str) -> bool:
    if sha not in _PIN_CACHE:
        r = subprocess.run(["git", "-C", str(STUDY_ROOT), "rev-parse", "--verify",
                            f"{sha}^{{commit}}"], capture_output=True, text=True)
        _PIN_CACHE[sha] = r.returncode == 0
    return _PIN_CACHE[sha]


def pinned_source(pth: str, sha: str):
    """`git show sha:pth` 的行;取不到返回 None(调用方退回工作树)。"""
    key = (pth, sha)
    if key not in _SRC_CACHE:
        r = subprocess.run(["git", "-C", str(STUDY_ROOT), "show", f"{sha}:{pth}"],
                           capture_output=True, text=True)
        _SRC_CACHE[key] = r.stdout.splitlines() if r.returncode == 0 else None
    return _SRC_CACHE[key]


def pin_after(text: str, cite) -> str:
    """紧跟锚点的 ` @ <sha>`(本仓库里存在的 commit 才算钉子)。"""
    m = PIN.match(text[cite.end():])
    if m and _pin_exists(m.group("sha")):
        return m.group("sha")
    return ""


def norm(s: str) -> str:
    return " ".join(s.split())


def source_lines(path: Path):
    key = str(path)
    if key not in _SRC_CACHE:
        _SRC_CACHE[key] = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return _SRC_CACHE[key]


def first_source_line(block):
    """First non-blank line of a block, skipping a leading locator comment."""
    for b in block:
        if not b.strip():
            continue
        if LOCATOR.match(b):
            continue
        return b
    return None


def block_locator(block):
    """The `# path:line` comment a block may open with — it, not the prose line,
    is then the authoritative claim about where the excerpt came from."""
    for b in block:
        if not b.strip():
            continue
        if LOCATOR.match(b):
            return any_anchor(b)
        return None
    return None


# Lines an excerpt uses to say "I skipped some source here".
ELISION = re.compile(r"^\s*(?:#\s*)?(?:\.\.\.|…|<snip>|\[\.\.\.\])\s*$")


def block_drift(block, src, start):
    """Compare a fenced block's lines 2..N against the source, not just line 1.

    The gate has always compared ONLY the block's first non-blank line against
    the cited line. Every line after it was unverified — an excerpt could drop a
    closing ``\"\"\"``, rename an identifier, or paraphrase a value, and the run
    stayed green. R8C found two such blocks in one round's draft; there was no
    mechanism that could have caught them.

    Returns a short human-readable report of the differing lines, or "" when the
    block tracks the source verbatim. Comparison stops at the first elision
    marker (``...``), which is an author declaration that the excerpt jumps.

    Reported as BLOCK-DRIFT, which **fails the run** (R8D). It went through the
    same staging the citation gate itself did — added R7C, promoted to blocking
    in R8A — because a check that fails on a backlog it did not cause teaches
    authors to ignore it. R8C added the check and found 115 historical drifts;
    R8D cleared all 116 (the extra one was a scope-of-run difference, not a
    regression) and promoted it here.

    What the cleanup found is why this is now blocking: 115 of 116 were fixable
    by re-copying the baseline verbatim, and only ONE was an excerpt asserting
    something false about the source (a fabricated closing ``\"\"\"`` implying a
    docstring ended 19 lines before it does). So the failure mode this guards is
    not "author mislabeled prose as code" — it is "author transcribed code by
    hand and dropped half a line". That is exactly the class of error a machine
    should catch and a reviewer cannot.
    """
    body = list(block)
    while body and not body[-1].strip():
        body.pop()
    # skip the leading locator comment and any leading blanks, the same way
    # first_source_line does, so index 0 lines up with the cited line.
    k = 0
    while k < len(body) and (not body[k].strip() or LOCATOR.match(body[k])):
        k += 1
    diffs = []
    for off, text in enumerate(body[k:]):
        if ELISION.match(text):
            break
        n = start - 1 + off
        if n >= len(src):
            diffs.append((off + 1, text, "<源码已到文件尾>"))
            break
        if norm(src[n]) != norm(text):
            diffs.append((off + 1, text, src[n]))
    if not diffs:
        return ""
    head = diffs[0]
    more = f"  (共 {len(diffs)} 行不符)" if len(diffs) > 1 else ""
    return (
        f"      块内第 {head[0]} 行与 {start + head[0] - 1} 行不符{more}\n"
        f"      引用: {norm(head[1])[:100]}\n"
        f"      基线: {norm(head[2])[:100]}"
    )


TABLE_ROW = re.compile(r"^\s*\|.*\|")
BACKTICKED = re.compile(r"`([^`]+)`")
HEADER = re.compile(r"^(?P<indent>\s*)(?:async\s+def|def|class)\s")
BARE_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]{1,4}")
CODEISH = re.compile(r"[_/(){}\[\]=<>.\"'|:-]|[A-Z]")


def is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2


def table_cells(line: str):
    s = line.strip().strip("|")
    return s.split("|")


def cell_tokens(cell: str):
    """Backticked spans in a cell that could be a source excerpt.

    Drops the anchors themselves, spans too short to prove anything, and spans
    with no word characters (`-`, `->`, `...` are table filler, not evidence).
    """
    out = []
    for raw in BACKTICKED.findall(cell):
        if any_anchor(raw):
            continue
        t = norm(raw)
        if len(t) < TABLE_MIN_TOKEN or re.fullmatch(r"[\d\W_]+", t):
            continue
        # A bare filename is a pointer, not an excerpt: `cli.py` "found" at some
        # line of cli.py proves nothing about the anchor.
        if BARE_PATH.fullmatch(t):
            continue
        # A plain lowercase word in backticks is a *term* the prose is naming
        # (`private`, `anthropic`), not a source excerpt. Finding it somewhere in
        # the file says nothing about where the anchor should point. Require a
        # shape only code has: punctuation that identifiers/paths/calls carry, or
        # a capital letter.
        if not CODEISH.search(t):
            continue
        out.append(t)
    return out


def declared_excerpt(cell: str, cite):
    """The backticked span the cell puts right after its anchor, if any.

    `hermes_cli/commands.py:1276`:`_SLACK_VIA_HERMES_ONLY = frozenset(...)` and
    `gateway/relay/media.py:92` 的 `is_relay_media_url` both declare "this text
    lives at that line". A symbol named in some other column does not.
    """
    tail = cell[cite.end():]
    # skip the citation's own ` @ 863e313` suffix and closing backtick, then allow
    # a short connector (":", " 的 ", "->", "**:**") before the excerpt itself
    m = re.match(r"[\s,]*(?:@\s*[0-9a-f]{7,40})?[^`]{0,3}`?[^`]{0,8}`([^`]+)`", tail)
    if not m:
        return []
    return cell_tokens(f"`{m.group(1)}`")



def enclosing_headers(src, start: int):
    """1-based lines of the def/class headers whose bodies contain *start*.

    Innermost first, e.g. [def test_..., class TestUnreadable...]. The
    cell-names-the-construct shape looks exactly like drift from outside: the
    token is real, it is in the file, and it is not on the cited line. What
    separates it is that the line it IS on is a header the cited line sits
    under — and that can be the class two levels up, not just the nearest def.
    """
    if not (1 <= start <= len(src)):
        return []
    body = src[start - 1]
    if not body.strip():
        return []
    indent = len(body) - len(body.lstrip())
    found = []
    for n in range(start - 2, -1, -1):
        line = src[n]
        if not line.strip():
            continue
        cur = len(line) - len(line.lstrip())
        if cur >= indent:
            continue
        # Walk outward through every enclosing scope. A `for`/`if`/`with` line at
        # a lower indent is still *inside* the function, so it must not stop the
        # walk — doing so was hiding the `def` that the cell was naming.
        if HEADER.match(line):
            found.append(n + 1)
        indent = cur
        if cur == 0:
            break
    return found


def enclosing_header(src, start: int):
    heads = enclosing_headers(src, start)
    return heads[0] if heads else None


def check_table_row(repo, note, lineno: int, line: str, resolve):
    """Verify anchors written inside a Markdown table row. See module docstring."""
    results = []
    for cell in table_cells(line):
        cites = citations(cell, resolve)
        if not cites:
            continue
        tag = f"{note.name}:{lineno}"
        # The declared inline excerpt is the backticked span that FOLLOWS the
        # anchor in the cell -- `path:N`:`text` or `path:N` 的 `text`. Anything
        # else in the row is prose that merely mentions a symbol, and guessing
        # which mention the anchor "meant" is how a gate quietly turns into
        # noise. Same principle as NON_SOURCE_LANGS: declared, not sniffed.
        if not any(declared_excerpt(cell, c) for c in cites):
            results.append(("TABLE-UNCHECKED", f"{tag}  {cites[0].group(0)} (table cell, no declared inline excerpt)"))
            continue

        verdict, detail = None, None
        for cm in cites:
            tokens = declared_excerpt(cell, cm)
            if not tokens:
                continue
            # 顺序即优先级:基线 -> commit 钉子 -> 本仓库工作树。
            # 钉子必须**优先于工作树**,否则一个仍存在于树上的自引目标(`chapters/r1` 就是)
            # 永远读的是最新版,钉子等于没写 —— 而钉子存在的全部意义正是「引旧版」。
            pth = cm.group("path")
            target = resolve(pth)
            if (repo / pth).is_file():
                src = source_lines(repo / pth)
            else:
                sha = pin_after(cell, cm)      # 自引锚点的 commit 钉子(R11D)
                src = pinned_source(pth, sha) if sha else None
                if src is None and target.is_file():
                    src = source_lines(target)
            if src is None:
                continue  # bare filenames are legal in notes; chapters have their own rule
            start = int(cm.group("start"))
            end = int(cm.group("end") or start)
            if not 1 <= start <= len(src):
                verdict = "TABLE-OUT-OF-RANGE"
                detail = f"{tag}  {cm.group(0)} (file has {len(src)} lines)"
                break
            band = " ".join(norm(x) for x in src[start - 1:min(len(src), max(end, start + TABLE_BAND))])
            if any(t in band for t in tokens):
                verdict = "TABLE-OK"
                break
            # `web_server.py:12296` (`_pairing_store` 的 docstring) is not drift:
            # the cell names the construct the anchor sits inside, and its name
            # is on that construct's header. Legitimate and common, so it counts
            # as anchored rather than merely being excluded from the hit list.
            heads = enclosing_headers(src, start)
            # Indent-walking alone is fooled by a multi-line signature whose
            # closing `) -> T:` sits at column 0 (hermes_cli/debug.py:648), so
            # also take the nearest def/class header above the anchor outright.
            near = next((n + 1 for n in range(start - 2, max(-1, start - 2 - WINDOW), -1)
                         if HEADER.match(src[n])), None)
            if near and near not in heads:
                heads = heads + [near]
            if any(t in norm(src[h - 1]) for h in heads for t in tokens):
                verdict = "TABLE-OK"
                break

            lo, hi = max(0, start - 1 - WINDOW), min(len(src), start - 1 + WINDOW)
            head = enclosing_header(src, start)
            # Only a token that identifies ONE place can testify that the anchor
            # points at the wrong one. `anthropic` matching four lines in the
            # window says the token is common, not that the anchor drifted.
            def counts_as_drift(h):
                if h == head:
                    return False  # the cell names the construct the anchor is in
                if h in heads:
                    return False  # a header the anchor sits under
                return True

            probe = None
            for t in tokens:
                hits = [n + 1 for n in range(lo, hi) if t in norm(src[n])]
                hits = [h for h in hits if counts_as_drift(h)]
                if 1 <= len(hits) <= TABLE_MAX_HITS:
                    probe, shown = hits, t
                    break
            if probe and verdict is None:
                hits = probe
                verdict = "TABLE-DRIFT"
                detail = (
                    f"{tag}  {cm.group(0)} -> 实际在 {hits[:4]}\n"
                    f"      表格内联 token: {shown[:100]}\n"
                    f"      锚点那一行:   {norm(src[start-1])[:100]}"
                )
        if verdict == "TABLE-OK":
            results.append(("TABLE-OK", ""))
        else:
            results.append((
                verdict or "TABLE-UNCHECKED",
                detail or f"{tag}  {cites[0].group(0)} (table cell, token not near anchor)",
            ))
    return results


def read_block(lines, j):
    """Read the excerpt block that starts at line index *j*.

    Returns (kind, body_lines, next_index) where kind is "fence", "quote", or
    None when line *j* does not open a block at all.
    """
    fm = FENCE.match(lines[j])
    if fm:
        k = j + 1
        body = []
        while k < len(lines) and not FENCE.match(lines[k]):
            body.append(lines[k])
            k += 1
        lang = (fm.group("lang") or "").lower()
        kind = "non-source" if lang in NON_SOURCE_LANGS else "fence"
        return kind, body, k + 1

    if QUOTE.match(lines[j]):
        k = j
        body = []
        while k < len(lines):
            qm = QUOTE.match(lines[k])
            if not qm:
                break
            body.append(qm.group("body"))
            k += 1
        return "quote", body, k

    return None, [], j


def check_note(repo: Path, note: Path, fix: bool = False):
    raw = note.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    results = []  # (status, detail)
    fixes = []  # (note_line_index, old_cite, new_cite)

    def resolve(pth):
        t = repo / pth
        # A note may legitimately cite this study repo's own files (prior-round
        # reports, chapters). Resolve against the baseline first, then locally.
        if not t.is_file() and (STUDY_ROOT / pth).is_file():
            t = STUDY_ROOT / pth
        return t

    def source_for(pth, cite, text):
        """The lines to compare against, honouring a `@ <sha>` pin on self-citations.

        Baseline paths ignore the pin: `@ 863e313` names the *baseline* repo, which
        never moves, and that sha does not rev-parse here — so existing corpus is
        untouched. A study path with a pin that IS a commit here reads that version.
        """
        t = resolve(pth)
        if (repo / pth).is_file():
            return t, source_lines(t)
        # 钉子优先于工作树:引的就是被改掉的那一版,读最新版等于钉子没写。
        sha = pin_after(text, cite)
        if sha:
            pinned = pinned_source(pth, sha)
            if pinned is not None:
                return t, pinned
        return t, (source_lines(t) if t.is_file() else None)

    i = 0
    while i < len(lines):
        line = lines[i]

        # Never scan for citations *inside* a fenced block: `path:line` there is a
        # diagram label or an excerpt's own text, not an assertion being sourced.
        if FENCE.match(line):
            i += 1
            while i < len(lines) and not FENCE.match(lines[i]):
                i += 1
            i += 1
            continue

        # Nor inside a blockquote: a quoted doc excerpt may contain `path:line`
        # of its own (docs cite code too), and that is the *quote's* text, not
        # this note asserting something.
        if QUOTE.match(line):
            while i < len(lines) and QUOTE.match(lines[i]):
                i += 1
            continue

        # A table row cannot be followed by a block — the next line is the next
        # row — so the pairing rule below would record every anchor in every
        # table UNCHECKED forever. Its excerpt is inline instead (H-R9A-h).
        if is_table_row(line):
            results.extend(check_table_row(repo, note, i + 1, line, resolve))
            i += 1
            continue

        cands = citations(line, resolve)
        if not cands:
            i += 1
            continue
        m = cands[-1]  # default: the last citation is usually the one the block follows

        # find the next non-blank line; it must open a block for us to check content
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            results.append(("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)}"))
            i += 1
            continue

        kind, block, nxt = read_block(lines, j)
        if kind is None:
            results.append(("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)}"))
            i += 1
            continue
        if kind == "non-source":
            results.append(
                ("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)} (declared non-source block)")
            )
            i = nxt
            continue

        first = first_source_line(block)

        # A `>` excerpt of a prose doc is routinely re-wrapped to the note's own
        # column width, so "quote line 1 == source line N" is too strict: the
        # single source line got split across several quote lines. Joining the
        # quote back into one string and asking whether the source line *starts*
        # with it recovers those. Fences keep strict equality — a code excerpt
        # that got re-wrapped is not a faithful excerpt in the first place.
        joined = norm(" ".join(block)) if kind == "quote" else ""

        def line_matches(text: str) -> bool:
            if first is None:
                return False
            if norm(text) == norm(first):
                return True
            return bool(joined) and len(joined) >= 20 and norm(text).startswith(joined)

        def matches(cand):
            t = resolve(cand.group("path"))
            if not t.is_file() or first is None:
                return False
            src = source_lines(t)
            n = int(cand.group("start"))
            return 1 <= n <= len(src) and line_matches(src[n - 1])

        # A block that opens with its own `# path:line` locator is asserting that
        # location; believe the locator over the surrounding prose citation.
        loc = block_locator(block) if kind == "fence" else None
        if loc is not None and resolve(loc.group("path")).is_file():
            m = loc
        # A prose line may carry several citations (the call site AND the callee).
        # The block belongs to whichever one it actually matches.
        elif len(cands) > 1:
            m = next((c for c in cands if matches(c)), m)

        path, start = m.group("path"), int(m.group("start"))
        target, pinned_lines = source_for(path, m, line)
        if pinned_lines is not None and not target.is_file():
            target = STUDY_ROOT / path  # pinned blob: file may be gone from the tree

        if pinned_lines is None:
            # A blockquote after a prose line that merely happens to name a file is
            # common; only the fence contract makes an unresolvable path an error.
            status = "MISSING-FILE" if kind == "fence" else "UNCHECKED"
            results.append((status, f"{note.name}:{i+1}  {path}"))
        elif first is None:
            results.append(("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)} (empty block)"))
        else:
            src = pinned_lines
            if start < 1 or start > len(src):
                results.append(
                    ("OUT-OF-RANGE", f"{note.name}:{i+1}  {path}:{start} (file has {len(src)} lines)")
                )
            elif line_matches(src[start - 1]):
                results.append(("OK", ""))
                # The first line matched. Everything AFTER it in the block has
                # never been checked by anything (R8C). See block_drift().
                if kind == "fence":
                    d = block_drift(block, src, start)
                    if d:
                        results.append(("BLOCK-DRIFT", f"{note.name}:{i+1}  {path}:{start}\n{d}"))
            else:
                # where does it actually live?
                lo, hi = max(0, start - 1 - WINDOW), min(len(src), start - 1 + WINDOW)
                hits = [n + 1 for n in range(lo, hi) if line_matches(src[n])]
                if kind == "quote" and not hits:
                    # A `>` block whose text appears nowhere near the anchor is a
                    # paraphrase, not drift. Not checkable, so not a failure.
                    results.append(
                        ("UNCHECKED", f"{note.name}:{i+1}  {m.group(0)} (quote, not verbatim)")
                    )
                    i = nxt
                    continue
                where = f" -> actually at {hits}" if hits else " -> not found within +/-%d" % WINDOW
                if len(hits) == 1:
                    delta = hits[0] - start
                    end = m.group("end")
                    old = f"{path}:{start}" + (f"-{end}" if end else "")
                    new = f"{path}:{hits[0]}" + (f"-{int(end)+delta}" if end else "")
                    fixes.append((i, old, new))
                    where += f" [fixable: {old} -> {new}]"
                detail = (
                    f"{note.name}:{i+1}  {path}:{start}{where}\n"
                    f"      cited: {norm(first)[:110]}\n"
                    f"      found: {norm(src[start-1])[:110]}"
                )
                # review-1 M-8: when the prose line carries several citations the
                # block is compared against a *fallback* pick, and printing only
                # that pick sent the last reader hunting an innocent citation.
                # Name every candidate and say which one this verdict is about.
                if len(cands) > 1:
                    listed = "  ".join(c.group(0) for c in cands)
                    detail += (
                        f"\n      note: {len(cands)} citations on this line ({listed});"
                        f" none matched, so the verdict above is about the fallback"
                        f" pick {path}:{start} — the drifted one may be another."
                    )
                results.append(("MISMATCH", detail))
        i = nxt

    if fix and fixes:
        for idx, old, new in fixes:
            lines[idx] = lines[idx].replace(old, new)
        note.write_text("\n".join(lines) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
        results.append(("FIXED", f"{note.name}: rewrote {len(fixes)} citation(s)"))
    return results


def main() -> None:
    argv = [a for a in sys.argv[1:] if a != "--fix"]
    fix = "--fix" in sys.argv
    # `--round <N>` 从 scripts/mandatory_scope.py 展开 CLAUDE.md 的强制范围。
    # 手敲文件清单仍然照旧可用 —— 但报告里的读数请用 --round 取,理由见那份模块的开头:
    # R11F 的 81.1% 少跑了 reading/ 那一段,而关卡当时无从指出这件事。
    rounds, argv = take_round_args(argv)
    scope_line = None
    if rounds:
        if not argv:
            raise SystemExit(__doc__)
        scope_files, breakdown = resolve(rounds)
        scope_line = format_scope(rounds, breakdown)
        targets = [str(p) for p in scope_files]
    else:
        if len(argv) < 2:
            raise SystemExit(__doc__)
        targets = argv[1:]
    repo = Path(argv[0])
    if not repo.is_dir():
        raise SystemExit(f"baseline repo not a directory: {repo}")

    tally = {}
    problems = []
    per_file = {}  # path -> {status: count}
    for arg in targets:
        note = Path(arg)
        if not note.is_file():
            print(f"skip (not a file): {note}")
            continue
        seen = per_file.setdefault(str(note), {})
        for status, detail in check_note(repo, note, fix=fix):
            tally[status] = tally.get(status, 0) + 1
            seen[status] = seen.get(status, 0) + 1
            if status not in ("OK", "UNCHECKED", "TABLE-OK", "TABLE-UNCHECKED"):
                problems.append(f"[{status}] {detail}")
    # BLOCK-DRIFT rides along on a citation that already counted as OK, so it
    # must not inflate the citation total or dilute the verifiable ratio.
    drift = tally.pop("BLOCK-DRIFT", 0)
    for counts in per_file.values():
        counts.pop("BLOCK-DRIFT", None)

    # Table anchors are a separate population with a separate contract; folding
    # them in would swing 可校验比例 for reasons unrelated to evidence quality,
    # and that number is compared across rounds. See module docstring.
    table = {k[len("TABLE-"):]: tally.pop(k) for k in list(tally) if k.startswith("TABLE-")}
    for counts in per_file.values():
        for k in [k for k in counts if k.startswith("TABLE-")]:
            counts.pop(k)

    for p in problems:
        print(p)

    # Files that are almost entirely UNCHECKED. Usually that means the anchors
    # were written AFTER their code blocks, so the gate never paired them up and
    # silently checked nothing. See module docstring — hint only, never fatal.
    suspects = []
    for path, counts in sorted(per_file.items()):
        n = sum(v for k, v in counts.items() if k != "FIXED")
        if n < UNCHECKED_HINT_MIN:
            continue
        ratio = counts.get("UNCHECKED", 0) / n
        if ratio >= UNCHECKED_HINT_RATIO:
            suspects.append((path, counts.get("UNCHECKED", 0), n, ratio))
    if suspects:
        print(
            f"\nHINT: 疑似锚点排版不合规 —— 以下文件 UNCHECKED 占比 >= {UNCHECKED_HINT_RATIO:.0%}"
        )
        print("      按制度锚点 `路径:行号 @ 863e313` 应单独成行、置于代码块/引用块**之前**;")
        print("      写在块后会让每一条引用都配不上块,于是全部记 UNCHECKED —— 关卡看起来是绿的,")
        print("      实际一条都没校验。请逐条确认是真散文引用,还是锚点放错了位置。")
        for path, u, n, ratio in suspects:
            print(f"      - {path}: UNCHECKED {u}/{n} = {ratio:.1%}")
        print("      (提示不影响退出码。)")

    total = sum(tally.values())
    # 取数范围与读数印在一起:一份报告里的引用读数从此自带它的分母是怎么来的。
    print(f"\n{scope_line}" if scope_line else f"\nscope=explicit  files={len(targets)}")
    print(
        f"citations={total}  "
        + "  ".join(f"{k}={v}" for k, v in sorted(tally.items()))
    )
    checkable = total - tally.get("FIXED", 0)
    if checkable:
        rate = tally.get("OK", 0) / checkable
        flag = "" if rate >= VERIFIABLE_FLOOR else f"  << 低于 {VERIFIABLE_FLOOR:.0%} 下限"
        print(f"可校验比例 OK/{checkable} = {rate:.1%}{flag}")
    if drift:
        print(
            f"BLOCK-DRIFT={drift}  (代码块首行之后的行与基线不符;**阻断**,"
            f"见脚本 block_drift() 的说明)"
        )
    table_bad = table.get("DRIFT", 0) + table.get("OUT-OF-RANGE", 0)
    if table:
        t_total = sum(table.values())
        print(
            f"table_anchors={t_total}  "
            + "  ".join(f"{k}={v}" for k, v in sorted(table.items()))
            + "   (表格行内锚点,单独计数;DRIFT/OUT-OF-RANGE **阻断**,见 H-R9A-h)"
        )
    bad = total - tally.get("OK", 0) - tally.get("UNCHECKED", 0) - tally.get("FIXED", 0)
    # BLOCK-DRIFT rides along on a citation already tallied OK, so it stays out
    # of `total` (above) to keep the verifiable ratio honest — but it is a
    # failure, so it counts here. R8D promotion; see block_drift().
    bad += drift + table_bad
    if bad:
        print(f"FAIL: {bad} citation(s) need fixing")
        sys.exit(1)
    print("OK: every code-block-backed citation matches the baseline")


if __name__ == "__main__":
    main()
