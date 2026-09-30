"""
redcap_logic.py
===============
A small, dependency-free evaluator for the subset of REDCap branching-logic
syntax used by this project's survey queue and form-display-logic (FDL) files.

Supported:
  - field refs:        [int_age], [group], [asd_group], [sex], [parent], ...
  - comparisons:       =  <>  !=  >  >=  <  <=
  - booleans:          and / or  (case-insensitive), && / ||
  - parentheses:       ( ... )
  - numeric + string RHS:  [sex]=1   [status]='2'
  - comment lines:     lines beginning with # or ## are stripped
  - blank condition:   always True (form always administered)
  - "1=0":             always False (inactive / staff-only)

Evaluation is deliberately conservative: if a condition references a field
that is not present/parseable for a record, evaluation raises
`UndeterminedError`, which the caller treats per project policy.
"""

import re


class UndeterminedError(Exception):
    """Raised when a condition cannot be evaluated for a given record."""


# ---- tokenizer -------------------------------------------------------------
_TOKEN_RE = re.compile(r"""
    \s*(?:
        (?P<lparen>\() |
        (?P<rparen>\)) |
        (?P<field>\[[a-zA-Z0-9_]+\](?:\[[0-9]+\])?) |   # [field] or [field][row]
        (?P<op>>=|<=|<>|!=|=|>|<) |
        (?P<andor>(?i:\band\b|\bor\b)|&&|\|\|) |
        (?P<num>-?\d+(?:\.\d+)?) |
        (?P<sqstr>'[^']*') |
        (?P<dqstr>"[^"]*")
    )
""", re.VERBOSE)


def _strip_comments(text: str) -> str:
    """Remove #/## comment lines; join the remaining logic into one line."""
    if text is None:
        return ""
    lines = []
    for ln in str(text).splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return " ".join(lines).strip()


def _tokenize(expr: str):
    tokens = []
    pos = 0
    while pos < len(expr):
        if expr[pos].isspace():
            pos += 1
            continue
        m = _TOKEN_RE.match(expr, pos)
        if not m or m.end() == pos:
            raise ValueError(f"Cannot tokenize near: {expr[pos:pos+20]!r}")
        pos = m.end()
        kind = m.lastgroup
        val = m.group().strip()
        tokens.append((kind, val))
    return tokens


# ---- recursive-descent parser into a nested structure ----------------------
# grammar:
#   expr   := term (OR term)*
#   term   := factor (AND factor)*
#   factor := '(' expr ')' | comparison
#   comparison := FIELD OP VALUE
class _Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def parse(self):
        node = self.parse_or()
        if self.i != len(self.toks):
            raise ValueError("Trailing tokens in expression")
        return node

    def parse_or(self):
        node = self.parse_and()
        while True:
            kind, val = self.peek()
            if kind == "andor" and val.lower() in ("or", "||"):
                self.next()
                rhs = self.parse_and()
                node = ("or", node, rhs)
            else:
                break
        return node

    def parse_and(self):
        node = self.parse_factor()
        while True:
            kind, val = self.peek()
            if kind == "andor" and val.lower() in ("and", "&&"):
                self.next()
                rhs = self.parse_factor()
                node = ("and", node, rhs)
            else:
                break
        return node

    def parse_factor(self):
        kind, val = self.peek()
        if kind == "lparen":
            self.next()
            node = self.parse_or()
            k2, _ = self.peek()
            if k2 != "rparen":
                raise ValueError("Missing closing paren")
            self.next()
            return node
        return self.parse_comparison()

    def parse_comparison(self):
        kind, val = self.next()
        if kind != "field":
            raise ValueError(f"Expected field, got {val!r}")
        field = val
        kind2, op = self.next()
        if kind2 != "op":
            raise ValueError(f"Expected operator, got {op!r}")
        kind3, rhs = self.next()
        if kind3 not in ("num", "sqstr", "dqstr"):
            raise ValueError(f"Expected value, got {rhs!r}")
        if kind3 == "sqstr":
            rhs = rhs[1:-1]
        elif kind3 == "dqstr":
            rhs = rhs[1:-1]
        return ("cmp", field, op, rhs)


def _field_name(token: str) -> str:
    """[int_age] -> int_age ; [foo][2] -> foo (row index ignored)."""
    m = re.match(r"\[([a-zA-Z0-9_]+)\]", token)
    return m.group(1) if m else token


def _coerce(a, b):
    """Try numeric comparison; fall back to string."""
    try:
        return float(a), float(b)
    except (ValueError, TypeError):
        return str(a), str(b)


def _eval_tri(node, record: dict):
    """
    Evaluate a node to a tri-state ``(value, reason)``.

    ``value`` is True, False, or None for UNKNOWN. ``reason`` carries the
    explanation for an UNKNOWN so the caller can re-raise a useful message.
    """
    try:
        return _eval_node(node, record), None
    except UndeterminedError as exc:
        return None, str(exc)


def _eval_node(node, record: dict):
    op = node[0]
    if op in ("and", "or"):
        # Three-valued (Kleene) logic. An operand that cannot be evaluated is
        # UNKNOWN rather than fatal: `False and UNKNOWN` is still False, and
        # `True or UNKNOWN` is still True. Propagating the exception instead
        # would throw away an answer the expression already determines -- the
        # practical case being a rule that references a field absent from the
        # export alongside one that is present.
        l, l_why = _eval_tri(node[1], record)
        r, r_why = _eval_tri(node[2], record)
        if op == "and":
            if l is False or r is False:
                return False
            if l is True and r is True:
                return True
        else:
            if l is True or r is True:
                return True
            if l is False and r is False:
                return False
        raise UndeterminedError(l_why or r_why or "undetermined operand")
    # comparison
    _, field_tok, cmp_op, rhs = node
    fname = _field_name(field_tok)
    if fname not in record:
        raise UndeterminedError(f"field '{fname}' not in record")
    raw = record.get(fname, "")
    if raw is None or str(raw).strip() == "":
        # A blank field value can't satisfy a positive comparison. REDCap
        # treats blank as not-equal to a concrete value; for >/< it's undetermined.
        if cmp_op in ("=",):
            return str(rhs).strip() == ""
        if cmp_op in ("<>", "!="):
            return str(rhs).strip() != ""
        raise UndeterminedError(f"field '{fname}' is blank for {cmp_op}")
    lhs = str(raw).strip()
    if cmp_op == "=":
        a, b = _coerce(lhs, rhs)
        return a == b
    if cmp_op in ("<>", "!="):
        a, b = _coerce(lhs, rhs)
        return a != b
    a, b = _coerce(lhs, rhs)
    if isinstance(a, str) or isinstance(b, str):
        # non-numeric with an ordering operator -> undetermined
        raise UndeterminedError(f"non-numeric compare {lhs!r} {cmp_op} {rhs!r}")
    if cmp_op == ">":
        return a > b
    if cmp_op == ">=":
        return a >= b
    if cmp_op == "<":
        return a < b
    if cmp_op == "<=":
        return a <= b
    raise ValueError(f"Unknown operator {cmp_op}")


def evaluate(condition: str, record: dict):
    """
    Evaluate a REDCap condition string against a record dict (field->raw str).
    Returns True/False. Raises UndeterminedError if it can't be determined.

    Special cases:
      - blank/whitespace/comment-only condition -> True  (always administered)
      - "1=0" (or any constant-false) -> False
    """
    cleaned = _strip_comments(condition)
    if cleaned == "":
        return True
    # constant expressions with no field refs (e.g. "1=0", "1=1")
    if "[" not in cleaned:
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*=\s*(-?\d+(?:\.\d+)?)\s*",
                         cleaned)
        if m:
            return float(m.group(1)) == float(m.group(2))
        # unknown constant expr -> undetermined
        raise UndeterminedError(f"constant expr not understood: {cleaned!r}")
    tokens = _tokenize(cleaned)
    tree = _Parser(tokens).parse()
    return _eval_node(tree, record)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        # (condition, record, expected)
        ("[int_age]>=228", {"int_age": "300"}, True),
        ("[int_age]>=228", {"int_age": "200"}, False),
        ("[int_age]<228", {"int_age": "200"}, True),
        ("[group]=1 and [int_age]>=228", {"group": "1", "int_age": "240"}, True),
        ("[group]=1 and [int_age]>=228", {"group": "1", "int_age": "200"}, False),
        ("[sex]=1", {"sex": "1"}, True),
        ("[sex]=2", {"sex": "1"}, False),
        ("", {"anything": "x"}, True),
        ("1=0", {}, False),
        ("1=1", {}, True),
        ("[parent]=1 and [int_age]<228", {"parent": "1", "int_age": "200"}, True),
        ("([group] = 1 AND [int_age]>=192) OR (([int_age] >= 180) AND ([group] = 2 OR [group] = 3))",
         {"group": "3", "int_age": "185"}, True),
        ("([group] = 1 AND [int_age]>=192) OR (([int_age] >= 180) AND ([group] = 2 OR [group] = 3))",
         {"group": "1", "int_age": "100"}, False),
        ("[group]=1 and ([int_age]>=192 and [int_age]<228)",
         {"group": "1", "int_age": "200"}, True),
        ("([asd_group]=4 or [group]=2 or [group]=3) and [parent]=1 and [int_age]<228",
         {"asd_group": "4", "group": "1", "parent": "1", "int_age": "100"}, True),
        ("[ados_module]=2", {"ados_module": "2"}, True),
        # comment stripping
        ("## Need to update this with correct logic eventually\n\n[group]=1",
         {"group": "1"}, True),
        # --- three-valued (Kleene) logic: a determinable branch still wins
        # even when the other operand references an unavailable field.
        ("[start_page_complete]=2 and [int_age]>=192",
         {"start_page_complete": "1"}, False),          # False and UNKNOWN
        ("[group]=1 or [int_age]>=192", {"group": "1"}, True),   # True or UNKNOWN
        ("[int_age]>=192 and [group]=9", {"group": "1"}, False),  # UNKNOWN and False
        ("[int_age]>=192 or [group]=1", {"group": "1"}, True),    # UNKNOWN or True
    ]
    passed = 0
    for cond, rec, exp in tests:
        try:
            got = evaluate(cond, rec)
        except Exception as e:
            got = f"ERR({e})"
        ok = (got == exp)
        passed += ok
        flag = "ok " if ok else "FAIL"
        print(f"[{flag}] {cond[:55]!r:58} -> {got}  (exp {exp})")
    # undetermined cases: still raise when no branch decides the expression
    extra = 0
    for cond, rec, label in [
        ("[missing_field]=1", {"other": "1"}, "missing field"),
        ("[start_page_complete]=2 and [int_age]>=192",
         {"start_page_complete": "2"}, "True and UNKNOWN"),
        ("[group]=2 or [int_age]>=192", {"group": "1"}, "False or UNKNOWN"),
    ]:
        extra += 1
        try:
            evaluate(cond, rec)
            print(f"[FAIL] expected UndeterminedError for {label}")
        except UndeterminedError:
            passed += 1
            print(f"[ok ] UndeterminedError raised for {label}")
    print(f"\n{passed}/{len(tests)+extra} passed")
