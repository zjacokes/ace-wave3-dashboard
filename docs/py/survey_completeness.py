"""
survey_completeness.py
======================
Combines REDCap instrument-status fields with Survey Queue and Form Display
Logic (FDL) rules to produce a branching-aware completion picture.

REDCap's standard instrument status fields are named ``<form>_complete``:

    0 = Incomplete, 1 = Unconfirmed, 2 = Complete

Older dashboard prototypes used ``<form>_iscomplete``. Both suffixes remain
supported, but ``_complete`` is canonical.

The administration logic is applied *before* the exported completion status:

  1. If Queue/FDL logic says the form does not apply, that participant-form
     combination is excluded from the survey table entirely. This is important
     because REDCap may export a default ``0`` completion value even for forms
     that were hidden and never intended for that participant.
  2. If eligibility cannot be evaluated, the participant-form combination is
     excluded rather than guessed.
  3. For eligible participant-form combinations, the only displayed outcomes
     are Complete, Unconfirmed, and Incomplete.

A further gate applies to the in-person battery. Queue/FDL logic describes who
a form is *for*, but not *when* it becomes due. Surveys administered at the
in-person visit only become expected once the participant has attended, so
they are gated on an anchor instrument (the BDI, which opens every visit) that
proves attendance. Participants without a complete anchor are dropped from
those denominators instead of being counted as incomplete. The anchor is
itself gated, so its eligible count is the visit-attendance count. See
:func:`build_visit_gate`.

Policy:
  - Form in BOTH queue and FDL -> both conditions must be true.
  - Form in only one source -> that source governs.
  - ``1=0`` / inactive -> never administered.
  - Blank condition -> always administered.
  - No rule for a returned form -> assume it is generally administered.
  - Gated in-person form + anchor not complete -> not yet expected.
"""

import csv
import io
import os
import re
from collections import Counter, defaultdict

from redcap_logic import evaluate, UndeterminedError


COMPLETION_SUFFIXES = ("_complete", "_iscomplete")
COMPLETION_LABELS = {"0": "Incomplete", "1": "Unconfirmed", "2": "Complete"}

# Backward-compatible names for older imports.
ISCOMPLETE_SUFFIX = "_iscomplete"
ISCOMPLETE_LABELS = COMPLETION_LABELS

OUTCOME_ORDER = ["Complete", "Unconfirmed", "Incomplete"]

_FIELD_REF_RE = re.compile(r"\[([A-Za-z0-9_]+)\](?:\[[0-9]+\])?")


def normalize_form_name(value):
    """Normalize a REDCap instrument/form name for cross-file matching."""
    name = str(value or "").strip().lower()
    for suffix in COMPLETION_SUFFIXES:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name


def _require_existing_file(path, label):
    """Return False for an omitted optional path; raise for a broken path."""
    if not path:
        return False
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label} file not found: {path}")
    return True


# ---------------------------------------------------------------------------
# Load the two logic files
# ---------------------------------------------------------------------------
def load_queue_logic(path):
    if not _require_existing_file(path, "Survey Queue"):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return load_queue_logic_from_text(handle.read())


def load_queue_logic_from_text(text):
    """Return ``form_name -> condition string`` for Survey Queue rows.

    REDCap's Survey Queue export stores two possible activation requirements:

    * ``condition_surveycomplete_form_name`` — a prerequisite survey that must
      be complete; and
    * ``condition_logic`` — optional record-level branching logic.

    ``condition_andor`` determines how those two requirements combine. The
    prerequisite survey is translated to its standard REDCap status field,
    e.g. ``start_page`` becomes ``[start_page_complete]=2``.
    """
    out = {}
    if not text:
        return out
    with io.StringIO(text.lstrip("\ufeff"), newline="") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        required = {
            "form_name", "active", "condition_surveycomplete_form_name",
            "condition_andor", "condition_logic",
        }
        missing = required - headers
        if missing:
            raise ValueError(
                "Survey Queue CSV is missing required column(s): "
                + ", ".join(sorted(missing))
            )
        for row in reader:
            name = normalize_form_name(row.get("form_name"))
            if not name:
                continue

            active = str(row.get("active") or "").strip()
            if active == "0":
                out[name] = "1=0"
                continue

            record_logic = str(row.get("condition_logic") or "").strip()
            prerequisite = normalize_form_name(
                row.get("condition_surveycomplete_form_name")
            )
            prerequisite_logic = (
                f"[{prerequisite}_complete]=2" if prerequisite else ""
            )

            if prerequisite_logic and record_logic:
                joiner = str(row.get("condition_andor") or "AND").strip().lower()
                if joiner not in {"and", "or"}:
                    joiner = "and"
                out[name] = (
                    f"({prerequisite_logic}) {joiner} ({record_logic})"
                )
            else:
                out[name] = prerequisite_logic or record_logic
    return out


def load_fdl_logic(path):
    if not _require_existing_file(path, "Form Display Logic"):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return load_fdl_logic_from_text(handle.read())


def load_fdl_logic_from_text(text):
    """Return ``form_name -> control_condition`` for FDL rows."""
    out = {}
    if not text:
        return out
    with io.StringIO(text.lstrip("\ufeff"), newline="") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        required = {"form_name", "control_condition"}
        missing = required - headers
        if missing:
            raise ValueError(
                "FDL CSV is missing required column(s): "
                + ", ".join(sorted(missing))
            )
        for row in reader:
            name = normalize_form_name(row.get("form_name"))
            if not name:
                continue
            out[name] = str(row.get("control_condition") or "").strip()
    return out


# ---------------------------------------------------------------------------
# Discover status columns and inspect logic dependencies
# ---------------------------------------------------------------------------
def discover_survey_forms(columns, excluded_forms=None):
    """
    Return ``{form_name: status_column}`` for every supported completion field.

    Standard REDCap ``*_complete`` columns take precedence if an export happens
    to contain both a canonical and a legacy ``*_iscomplete`` field.

    ``excluded_forms`` names instruments that are no longer collected. They are
    dropped here so that they never reach discovery, diagnostics, or the
    rendered table -- even when an older saved export still carries the column.
    """
    excluded = {normalize_form_name(f) for f in (excluded_forms or ())}
    forms = {}
    suffix_rank = {suffix: i for i, suffix in enumerate(COMPLETION_SUFFIXES)}
    chosen_rank = {}

    for raw_col in columns:
        col = str(raw_col or "").strip()
        lower = col.lower()
        for suffix in COMPLETION_SUFFIXES:
            if not lower.endswith(suffix):
                continue
            form = normalize_form_name(lower[:-len(suffix)])
            if not form or form in excluded:
                break
            rank = suffix_rank[suffix]
            if form not in forms or rank < chosen_rank[form]:
                forms[form] = col
                chosen_rank[form] = rank
            break
    return forms


def missing_expected_fields(columns, expected_fields):
    """Return configured completion fields absent from the current export."""
    present = {str(c).strip().lower() for c in columns}
    return [f for f in expected_fields if str(f).strip().lower() not in present]


def referenced_logic_fields(queue_logic, fdl_logic):
    """Return all REDCap fields referenced by the loaded administration logic."""
    fields = set()
    for cond in list(queue_logic.values()) + list(fdl_logic.values()):
        fields.update(_FIELD_REF_RE.findall(str(cond or "")))
    return fields


def missing_logic_fields(columns, queue_logic, fdl_logic):
    """Return logic-referenced fields that are absent from the API report."""
    present = {str(c).strip().lower() for c in columns}
    return sorted(f for f in referenced_logic_fields(queue_logic, fdl_logic)
                  if f.lower() not in present)


def form_rule_missing_fields(form, columns, queue_logic, fdl_logic):
    """
    Return the fields *one form's* governing rules reference that are absent
    from the export.

    A non-empty result means the rule cannot be resolved for any record, which
    is structurally different from a rule that is merely blank for some
    participants. Callers use it to distinguish "this participant is not
    eligible" from "eligibility is unknowable with the columns we were given",
    and to degrade visibly rather than silently emptying a denominator.
    """
    form = normalize_form_name(form)
    present = {str(c).strip().lower() for c in (columns or [])}
    fields = set()
    for source in (queue_logic or {}, fdl_logic or {}):
        if form in source:
            fields.update(_FIELD_REF_RE.findall(str(source[form] or "")))
    return sorted(f for f in fields if f.lower() not in present)


# ---------------------------------------------------------------------------
# In-person visit gate
# ---------------------------------------------------------------------------
def build_visit_gate(columns, anchor_form, gated_forms, complete_codes=("2",)):
    """
    Build the descriptor used to gate in-person forms on visit attendance.

    Surveys administered at the in-person visit are only *expected* once the
    participant has actually attended. ``anchor_form`` is the instrument used
    as proof of attendance (the BDI, which every participant starts the visit
    with): when its REDCap status is one of ``complete_codes``, the in-person
    battery is treated as expected for that participant. Otherwise the
    participant is dropped from those forms' denominators rather than counted
    as incomplete.

    The anchor is normally a member of ``gated_forms`` and therefore gates
    itself. Its completion percentage is then 100% by construction, and the
    informative number for that row becomes its eligible count -- the number
    of participants who have attended a visit.

    Returns ``None`` -- meaning "gate disabled" -- when gating is not
    configured or when the anchor's status column is absent from the export.
    Failing open is deliberate: silently gating on a column that is not there
    would empty every gated denominator at once.
    """
    anchor = normalize_form_name(anchor_form)
    forms = {normalize_form_name(f) for f in (gated_forms or ())}
    if not anchor or not forms:
        return None

    status_col = discover_survey_forms(columns).get(anchor)
    if not status_col:
        return None

    return {
        "anchor_form": anchor,
        "anchor_status_col": status_col,
        "complete_codes": frozenset(str(c).strip() for c in complete_codes),
        "forms": frozenset(forms),
    }


def visit_attended(gate, record):
    """
    Return True when ``record`` has attended the in-person visit.

    Attendance is defined by the anchor instrument alone: every visit opens
    with the anchor (the BDI), so a qualifying status on it means the
    participant came in. This is the single definition used both to gate
    in-person form denominators and to report attendance directly, so the two
    figures cannot drift apart.

    Returns None when gating is not configured, which callers must distinguish
    from False -- "we cannot tell" is not "has not attended".
    """
    if not gate:
        return None
    raw = str(record.get(gate["anchor_status_col"], "") or "").strip()
    return raw in gate["complete_codes"]


def visit_gate_allows(gate, form, record):
    """
    Return True when ``form`` may count ``record`` toward its denominator.

    Always True for an absent gate or an ungated form. For a gated form, the
    participant must carry a qualifying status on the anchor instrument.
    """
    if not gate:
        return True
    if normalize_form_name(form) not in gate["forms"]:
        return True
    return bool(visit_attended(gate, record))


def condition_is_constant_false(condition):
    """True only for a condition that can be proven false without record data."""
    try:
        return evaluate(condition, {}) is False
    except (UndeterminedError, ValueError):
        return False


def form_is_inactive(form, queue_logic, fdl_logic):
    """Return True when any governing AND-condition makes the form impossible."""
    form = normalize_form_name(form)
    conds = []
    if form in queue_logic:
        conds.append(queue_logic[form])
    if form in fdl_logic:
        conds.append(fdl_logic[form])
    return bool(conds) and any(condition_is_constant_false(c) for c in conds)


# ---------------------------------------------------------------------------
# Core: resolve one participant x form
# ---------------------------------------------------------------------------
def _evaluate_rule(condition, record):
    try:
        return evaluate(condition, record)
    except (UndeterminedError, ValueError):
        return None


def _should_administer(form, record, queue_logic, fdl_logic):
    """
    Return ``(should_administer, determinable)``.

    ``should_administer`` is True, False, or None. Queue and FDL rules combine
    with AND semantics. A definitive False therefore wins even when the other
    rule is unknown; otherwise an unresolved rule produces None rather than a
    false Missing classification.
    """
    form = normalize_form_name(form)
    rules = []
    if form in queue_logic:
        rules.append(queue_logic[form])
    if form in fdl_logic:
        rules.append(fdl_logic[form])

    if not rules:
        return True, True

    results = [_evaluate_rule(cond, record) for cond in rules]
    if any(result is False for result in results):
        return False, True
    if all(result is True for result in results):
        return True, True
    return None, False


def classify_detail(form, status_col, record, queue_logic, fdl_logic,
                    visit_gate=None):
    """
    Resolve one participant x form.

    Returns ``(outcome, exclusion_reason)`` where outcome is one of the three
    REDCap completion labels or ``None`` when the participant-form combination
    should not be counted.

    Exclusion reasons are diagnostic only and never appear as survey outcomes:
      - ``rule_false``: current Queue/FDL logic says the form does not apply.
      - ``rule_unknown``: the eligibility rule could not be evaluated.
      - ``awaiting_visit``: the form applies in principle, but the participant
        has not yet completed the in-person visit anchor, so the form is not
        expected of them yet.
      - ``status_unavailable``: the form applies, but the exported status was
        blank or outside REDCap's 0/1/2 completion codes.

    Queue/FDL logic is resolved first so that a form which does not apply to a
    participant at all keeps that more specific reason rather than being
    reported as merely awaiting a visit.
    """
    should, _determinable = _should_administer(
        form, record, queue_logic, fdl_logic
    )
    if should is False:
        return None, "rule_false"
    if should is not True:
        return None, "rule_unknown"

    if not visit_gate_allows(visit_gate, form, record):
        return None, "awaiting_visit"

    raw = str(record.get(status_col, "") or "").strip()
    if raw in COMPLETION_LABELS:
        return COMPLETION_LABELS[raw], None
    return None, "status_unavailable"


def classify(form, status_col, record, queue_logic, fdl_logic,
             visit_gate=None):
    """Backward-compatible outcome-only wrapper; may return ``None``."""
    return classify_detail(
        form, status_col, record, queue_logic, fdl_logic, visit_gate
    )[0]


# ---------------------------------------------------------------------------
# Aggregate across all records
# ---------------------------------------------------------------------------
def compute_survey_completeness(raw_records, columns, queue_logic, fdl_logic,
                                site_of, restrict_records=None,
                                visit_gate=None, excluded_forms=None):
    """
    Return per-form overall and site-level completion summaries.

    Administration eligibility is resolved first. Only eligible records with a
    valid REDCap 0/1/2 completion code enter the displayed counts. Ineligible
    and indeterminate participant-form combinations are excluded from both the
    numerator and denominator.

    ``visit_gate`` (see :func:`build_visit_gate`) additionally removes
    participants from the denominator of in-person forms until they have
    attended their visit, so pending visits do not masquerade as incomplete
    data.
    """
    forms = discover_survey_forms(columns, excluded_forms)
    records = restrict_records if restrict_records is not None else raw_records

    per_form = []
    for form, status_col in sorted(forms.items()):
        overall = Counter()
        by_site = defaultdict(Counter)
        excluded_by_logic = 0
        eligibility_unknown = 0
        status_unavailable = 0
        awaiting_visit = 0

        for rec in records:
            outcome, reason = classify_detail(
                form, status_col, rec, queue_logic, fdl_logic, visit_gate
            )
            if outcome is None:
                if reason == "rule_false":
                    excluded_by_logic += 1
                elif reason == "rule_unknown":
                    eligibility_unknown += 1
                elif reason == "awaiting_visit":
                    awaiting_visit += 1
                elif reason == "status_unavailable":
                    status_unavailable += 1
                continue
            overall[outcome] += 1
            by_site[site_of(rec)][outcome] += 1

        eligible = sum(overall.get(k, 0) for k in OUTCOME_ORDER)
        complete = overall.get("Complete", 0)
        done_any = complete + overall.get("Unconfirmed", 0)
        per_form.append({
            "form": form,
            "status_col": status_col,
            "iscol": status_col,  # compatibility with old renderer
            "overall": overall,
            "by_site": by_site,
            "eligible": eligible,
            "complete": complete,
            "complete_pct": (complete / eligible * 100) if eligible else 0.0,
            "done_any_pct": (done_any / eligible * 100) if eligible else 0.0,
            "excluded_by_logic": excluded_by_logic,
            "eligibility_unknown": eligibility_unknown,
            "status_unavailable": status_unavailable,
            "awaiting_visit": awaiting_visit,
            "in_queue": form in queue_logic,
            "in_fdl": form in fdl_logic,
            "visit_gated": bool(visit_gate) and form in visit_gate["forms"],
        })

    # Lowest completion first; forms with no eligible records are hidden by the
    # renderer and sorted last for predictable diagnostics.
    per_form.sort(
        key=lambda d: (
            d["eligible"] == 0,
            d["complete_pct"] if d["eligible"] else 101.0,
            d["form"],
        )
    )
    return per_form


def humanize_form(form):
    """Turn a REDCap instrument name into a readable title."""
    return normalize_form_name(form).replace("_", " ").strip().title()


if __name__ == "__main__":
    # Naming regression test.
    cols = ["record_number", "alpha_complete", "beta_iscomplete"]
    found = discover_survey_forms(cols)
    assert found == {
        "alpha": "alpha_complete",
        "beta": "beta_iscomplete",
    }, found

    # Key FDL regression: REDCap may export 0 for hidden forms. Those records
    # must be excluded before completion status is counted.
    fdl = {"combined_pds_another_assigned_sex": "[sex]=3"}
    records = [
        {"site": "A", "sex": "1", "combined_pds_another_assigned_sex_complete": "0"},
        {"site": "A", "sex": "2", "combined_pds_another_assigned_sex_complete": "0"},
        {"site": "A", "sex": "3", "combined_pds_another_assigned_sex_complete": "2"},
    ]
    result = compute_survey_completeness(
        records,
        ["combined_pds_another_assigned_sex_complete"],
        {},
        fdl,
        lambda r: r["site"],
    )[0]
    assert result["overall"] == Counter({"Complete": 1}), result
    assert result["eligible"] == 1, result
    assert result["excluded_by_logic"] == 2, result

    # An unevaluable rule is excluded, not converted into a dashboard status.
    outcome, reason = classify_detail(
        "adult_form", "adult_form_complete",
        {"adult_form_complete": "0", "int_age": ""},
        {}, {"adult_form": "[int_age]>=228"}
    )
    assert outcome is None and reason == "rule_unknown", (outcome, reason)

    # --- In-person visit gate ------------------------------------------
    anchor = "inperson_beck_depression_inventory"
    gated = {"after_visit_tas8", anchor}  # the anchor gates itself too
    cols = [f"{anchor}_complete", "after_visit_tas8_complete"]
    gate = build_visit_gate(cols, anchor, gated)
    assert gate is not None and gate["forms"] == frozenset(gated), gate

    visit_records = [
        # Attended: BDI complete -> TAS-8 is expected and counts.
        {"site": "A", f"{anchor}_complete": "2", "after_visit_tas8_complete": "2"},
        # Attended but TAS-8 not done -> a real incomplete.
        {"site": "A", f"{anchor}_complete": "2", "after_visit_tas8_complete": "0"},
        # Not yet visited -> REDCap's default 0 must NOT read as incomplete.
        {"site": "B", f"{anchor}_complete": "0", "after_visit_tas8_complete": "0"},
        # Blank anchor -> also not yet expected.
        {"site": "B", f"{anchor}_complete": "", "after_visit_tas8_complete": "0"},
    ]
    gated_result = {
        d["form"]: d for d in compute_survey_completeness(
            visit_records, cols, {}, {}, lambda r: r["site"], visit_gate=gate
        )
    }
    tas8 = gated_result["after_visit_tas8"]
    assert tas8["eligible"] == 2, tas8
    assert tas8["overall"] == Counter({"Complete": 1, "Incomplete": 1}), tas8
    assert tas8["awaiting_visit"] == 2, tas8
    assert tas8["complete_pct"] == 50.0, tas8
    assert tas8["visit_gated"] is True, tas8

    # The anchor gates itself, so its row is 100% by construction and its
    # eligible count IS the visit-attendance count. Both are intended: for
    # this row the denominator carries the signal, not the percentage.
    bdi = gated_result[anchor]
    assert bdi["visit_gated"] is True, bdi
    assert bdi["eligible"] == 2, bdi
    assert bdi["complete_pct"] == 100.0, bdi
    assert bdi["overall"] == Counter({"Complete": 2}), bdi
    assert bdi["awaiting_visit"] == 2, bdi
    # The blank-anchor record is held back by the gate before it can be
    # reported as an unusable status, so status_unavailable stays clean.
    assert bdi["status_unavailable"] == 0, bdi

    # Without the gate, the same data reports 25% and four false incompletes.
    ungated = {
        d["form"]: d for d in compute_survey_completeness(
            visit_records, cols, {}, {}, lambda r: r["site"]
        )
    }["after_visit_tas8"]
    assert ungated["eligible"] == 4 and ungated["complete_pct"] == 25.0, ungated

    # Queue/FDL exclusion outranks the gate: a form that does not apply at all
    # keeps the more specific reason.
    outcome, reason = classify_detail(
        "after_visit_tas8", "after_visit_tas8_complete",
        {f"{anchor}_complete": "0", "after_visit_tas8_complete": "0", "sex": "1"},
        {}, {"after_visit_tas8": "[sex]=3"}, gate
    )
    assert outcome is None and reason == "rule_false", (outcome, reason)

    # Gate fails open when the anchor column is missing from the export,
    # rather than silently emptying every gated denominator.
    assert build_visit_gate(["after_visit_tas8_complete"], anchor, gated) is None

    # --- Retired instruments are never discovered ----------------------
    retired = discover_survey_forms(
        ["srs2_complete", "srs2_adult_informantreport_complete",
         "staff_adir_complete"],
        excluded_forms={"srs2_adult_informantreport", "staff_adir"},
    )
    assert retired == {"srs2": "srs2_complete"}, retired

    print("survey_completeness self-tests passed")
