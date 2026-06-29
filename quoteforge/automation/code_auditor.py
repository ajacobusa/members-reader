"""Recurring code-outcome auditor - the automatic feeder for the infra-check agent.

Deep, line-by-line "does the code's ACTUAL outcome match its INTENT?" reasoning is
the job of the `code-outcome-auditor` subagent (.claude/agents/), which a human
points at one module and which proposes a grounded infra_check invariant + a
regression test for every confirmed fix.

This module is the cheap, cron-safe HALF of that loop: every day it sweeps ALL
modules (one consistent pass over the whole codebase) and surfaces, with GROUNDED
static analysis only (no LLM, no guessing):

  - outcome SMELLS that an AST can prove: an exception silently swallowed
    (``except ...: pass`` - errors vanish, the project's #1 'silent break'),
    a bare ``except:``, and TODO/FIXME/XXX/HACK markers left in the code.
  - infra-check COVERAGE GAPS: public functions in the module that NO infra_check
    invariant currently references - i.e. the worklist of code not yet protected
    by the daily sentinel.

It RATCHETS against a committed baseline (audit_baseline.json), exactly like the
project's docs ratchet: the daily job ALERTS the owner only on a REGRESSION - a
NEW smell beyond the accepted backlog - so the standing debt never re-nags but a
freshly introduced silent-failure is caught the next morning. The owner works the
backlog down via the subagent and re-accepts with `audit --baseline`.

Sweeping ALL modules on every run (rather than one per day) keeps the signal
CONSISTENT: every module is re-checked each day, so a smell introduced today is
caught tomorrow - no module waits for a round-robin turn.

GROUNDING: every finding is derived from the real source via ``ast`` (smells) or a
real line scan (markers); coverage is computed from infra_check's own AST, not a
substring match. Nothing is imported or executed, so the sweep has no side effects.
"""
from __future__ import annotations

import ast
import io
import json
import logging
import re
import tokenize
from pathlib import Path

logger = logging.getLogger(__name__)

# Markers that flag unfinished/again-look-here code, matched as whole words inside
# real COMMENT tokens only (so a docstring describing them, or a placeholder like
# 'appXXXX', is never a false positive).
_TODO_MARKERS = ("TODO", "FIXME", "XXX", "HACK")
_MARKER_RE = re.compile(r"\b(" + "|".join(_TODO_MARKERS) + r")\b")


def _package_root() -> Path:
    """The quoteforge package directory (…/quoteforge)."""
    import quoteforge
    return Path(quoteforge.__file__).resolve().parent


def list_modules() -> list[str]:
    """Every auditable module, as a POSIX path relative to the package root
    (e.g. 'automation/code_auditor.py'), deterministically sorted. Excludes
    package __init__ files and bytecode caches."""
    root = _package_root()
    mods = [p.relative_to(root).as_posix()
            for p in root.rglob("*.py")
            if "__pycache__" not in p.parts and p.name != "__init__.py"]
    return sorted(mods)


# ── grounded static analysis ─────────────────────────────────────────

def _public_defs(tree: ast.AST) -> list[str]:
    """Top-level public function/method names (not _private) defined in a tree."""
    return [n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")]


def _swallows(handler: ast.ExceptHandler) -> bool:
    """True iff an except handler SILENTLY swallows the error - its body is only
    ``pass``/``...``, with no logging, no re-raise, and no owner alert. This is the
    project's #1 silent-failure smell ('except: pass' strands an order quietly)."""
    body = handler.body
    only_noop = all(isinstance(s, ast.Pass)
                    or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                    for s in body)
    if not only_noop:
        return False
    # A handler that re-raises or logs/alerts is NOT silent - but a pure pass/... is.
    return True


def _smells(source: str) -> list[dict]:
    """Grounded outcome smells in one module's source. Each: {kind, line, detail}."""
    found: list[dict] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [{"kind": "syntax_error", "line": exc.lineno or 0,
                 "detail": str(exc)}]
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                found.append({"kind": "bare_except", "line": node.lineno,
                              "detail": "bare 'except:' catches everything, even "
                                        "KeyboardInterrupt/SystemExit"})
            elif _swallows(node):
                found.append({"kind": "silent_except", "line": node.lineno,
                              "detail": "exception swallowed (pass/...) - the error "
                                        "vanishes with no log, alert, or re-raise"})
    # Marker scan over real COMMENT tokens only (not strings/docstrings/identifiers).
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT and _MARKER_RE.search(tok.string):
                found.append({"kind": "todo_marker", "line": tok.start[0],
                              "detail": tok.string.strip()[:120]})
    except (tokenize.TokenError, IndentationError) as exc:
        logger.debug("marker scan skipped an unparseable tail: %s", exc)
    return found


def _infra_referenced_names() -> set:
    """Every symbol name the infra_check agent references (imported names, called
    names, attribute names) - computed from its AST, not a substring match. A
    module function appearing here is considered protected by the daily sentinel."""
    from quoteforge.automation import infra_check
    tree = ast.parse(Path(infra_check.__file__).read_text(encoding="utf-8"))
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Some guards are checked by NAME-as-string (e.g.
            # _references(resume, "route_order")), so real string literals count
            # as coverage too. Comments are not Constants, so this stays grounded.
            names.add(node.value)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
            if node.module:
                names.add(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[-1])
    return names


def audit_module(rel_path: str, protected: "set | None" = None) -> dict:
    """Grounded static audit of ONE module. Returns {module, smells, coverage_gaps,
    public_defs, ok}. Reads the source only - never imports or runs it. Pass
    `protected` (infra-referenced names) to avoid recomputing it on a full sweep."""
    src_path = _package_root() / rel_path
    source = src_path.read_text(encoding="utf-8")
    smells = _smells(source)
    if protected is None:
        protected = _infra_referenced_names()
    try:
        tree = ast.parse(source)
        pub = _public_defs(tree)
        gaps = [fn for fn in pub if fn not in protected]
    except SyntaxError:
        pub, gaps = [], []
    return {"module": rel_path, "smells": smells, "coverage_gaps": gaps,
            "public_defs": pub, "ok": not smells}


def _baseline_path() -> Path:
    """The committed baseline of ACCEPTED smells (a ratchet, like the docs ratchet)."""
    return _package_root() / "automation" / "audit_baseline.json"


def load_baseline() -> dict:
    """The accepted-smell baseline: {module: {kind: count}}. {} if absent/corrupt."""
    p = _baseline_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 - a corrupt baseline just means "nothing accepted"
            return {}
    return {}


def smell_counts(results: list) -> dict:
    """Per-module smell tally {module: {kind: count}} (modules with smells only)."""
    counts: dict = {}
    for r in results:
        if not r["smells"]:
            continue
        per: dict = {}
        for s in r["smells"]:
            per[s["kind"]] = per.get(s["kind"], 0) + 1
        counts[r["module"]] = per
    return counts


def regressions(results: list, baseline: dict) -> list:
    """Smells BEYOND the accepted baseline - the only thing worth a daily alert.
    Returns [{module, kind, count, accepted}] where current count exceeds baseline."""
    out = []
    for module, per in smell_counts(results).items():
        accepted = baseline.get(module, {})
        for kind, count in per.items():
            if count > accepted.get(kind, 0):
                out.append({"module": module, "kind": kind, "count": count,
                            "accepted": accepted.get(kind, 0)})
    return out


def write_baseline(results: list) -> dict:
    """Accept the current smell inventory as the baseline (owner-invoked). Returns it."""
    counts = smell_counts(results)
    _baseline_path().write_text(json.dumps(counts, indent=1, sort_keys=True),
                                encoding="utf-8")
    return counts


def run_full_audit(send: bool = False) -> dict:
    """Sweep ALL modules in one consistent pass and ratchet against the accepted
    baseline. Returns {modules, flagged, total_smells, regressions, results, ok,
    alerted}. The daily job alerts ONCE only on a REGRESSION (a new smell beyond
    the baseline) - the standing backlog never re-nags."""
    protected = _infra_referenced_names()
    results = [audit_module(m, protected) for m in list_modules()]
    flagged = [r["module"] for r in results if r["smells"]]
    total_smells = sum(len(r["smells"]) for r in results)
    regs = regressions(results, load_baseline())
    summary = {
        "modules": len(results),
        "flagged": flagged,
        "total_smells": total_smells,
        "regressions": regs,
        "results": results,
        "ok": not regs,                # green when nothing is BEYOND the baseline
        "alerted": False,
    }
    if send and regs:
        from quoteforge.admin import _alert
        _alert(f"🔎 Code audit: {len(regs)} NEW outcome smell(s) beyond baseline",
               "<pre>" + format_full_audit_text(summary) + "</pre>",
               what="code-audit")
        summary["alerted"] = True
    return summary


def format_audit_text(result: dict) -> str:
    """Human-readable one-module audit report."""
    mod = result.get("module") or "(no module)"
    lines = [f"Code audit - {mod}", "=" * 56]
    smells = result.get("smells", [])
    if smells:
        lines.append(f"OUTCOME SMELLS ({len(smells)}):")
        lines += [f"  [{s['kind']}] line {s['line']}: {s['detail']}" for s in smells]
    else:
        lines.append("OUTCOME SMELLS: none")
    gaps = result.get("coverage_gaps", [])
    lines.append("")
    lines.append(f"INFRA-CHECK COVERAGE GAPS ({len(gaps)} public fn not yet "
                 f"protected by an invariant):")
    lines += [f"  - {fn}()" for fn in gaps[:20]]
    if len(gaps) > 20:
        lines.append(f"  … and {len(gaps) - 20} more")
    lines.append("")
    lines.append("Next: run the `code-outcome-auditor` subagent on this module to "
                 "confirm fixes and add grounded checks to infra_check.")
    return "\n".join(lines)


def format_full_audit_text(summary: dict) -> str:
    """Human-readable whole-codebase sweep report: NEW smells (beyond baseline)
    first, then the accepted backlog total."""
    regs = summary.get("regressions", [])
    lines = [f"Code audit sweep - {summary['modules']} module(s)", "=" * 56]
    if regs:
        lines.append(f"NEW smells beyond baseline ({len(regs)}) - action needed:")
        for r in regs:
            lines.append(f"  {r['module']}: {r['kind']} "
                         f"{r['accepted']} -> {r['count']}")
        lines.append("")
        lines.append("Run `audit <module>` for line numbers, then the "
                     "`code-outcome-auditor` subagent to fix + add a grounded "
                     "infra_check invariant. After fixing, `audit --baseline` "
                     "re-accepts the (now smaller) inventory.")
    else:
        lines.append("NEW smells beyond baseline: none.")
    lines.append("")
    lines.append(f"(Accepted backlog: {summary['total_smells']} smell(s) in "
                 f"{len(summary['flagged'])} module(s) - tracked, not alerted.)")
    return "\n".join(lines)
