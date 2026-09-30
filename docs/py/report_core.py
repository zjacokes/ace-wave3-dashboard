"""Unchanged dashboard computation and rendering shared by CLI and browser."""
from __future__ import annotations
from collections import Counter, defaultdict
import re
import pandas as pd
import config as C
import survey_completeness as SC
import table1 as T1

def validate_columns(df: pd.DataFrame) -> list:
    """Return a list of expected fields missing from the export (warnings)."""
    return [f for f in C.EXPORT_FIELDS if f not in df.columns]


def decode_value(field: str, raw: str):
    """Map a single raw code to its label. Returns (label, is_unexpected)."""
    raw = (raw or "").strip()
    if raw == "":
        return "", False
    vmap = C.VALUE_MAPS.get(field)
    if vmap is None:
        return raw, False  # free text / continuous / id — pass through
    if raw in vmap:
        return vmap[raw], False
    # coded value not in dictionary -> show raw + flag
    return f"{raw} (unexpected)", True


def collapse_race(row: dict):
    """
    Unify self-report (ace_demo_13) and informant (ace_demo_informant_11).
    Priority: self-report; informant fills gaps. Returns:
        (unified_label, source, conflict_bool)
    """
    self_raw = (row.get(C.RACE_SELF, "") or "").strip()
    inf_raw = (row.get(C.RACE_INFORMANT, "") or "").strip()
    self_lab = C.RACE_MAP.get(self_raw)
    inf_lab = C.RACE_MAP.get(inf_raw)

    if self_lab and inf_lab:
        if self_raw == inf_raw:
            return self_lab, "both agree", False
        return self_lab, "self (conflict)", True  # prefer self, flag
    if self_lab:
        return self_lab, "self", False
    if inf_lab:
        return inf_lab, "informant", False
    return "", "none", False


def collapse_hispanic(row: dict):
    """Unify Hispanic/Latino self + informant (yes/no). Self takes priority."""
    self_raw = (row.get(C.HISPANIC_SELF, "") or "").strip()
    inf_raw = (row.get(C.HISPANIC_INFORMANT, "") or "").strip()
    self_lab = C.YESNO.get(self_raw)
    inf_lab = C.YESNO.get(inf_raw)
    if self_lab and inf_lab:
        if self_raw == inf_raw:
            return self_lab, False
        return self_lab, True
    if self_lab:
        return self_lab, False
    if inf_lab:
        return inf_lab, False
    return "", False


def collapse_lifetime_status(row: dict, side: str):
    """
    Derive a single 'autism diagnosis status' category from the branch tree.
    Returns the status label (or "" if the entry question is blank).
    """
    cfg = C.LIFETIME[side]
    q1 = (row.get(cfg["q1"], "") or "").strip()
    if q1 == "":
        return ""
    if q1 == "1":
        return "Formally diagnosed"
    if q1 == "0":
        follow = (row.get(cfg["no"], "") or "").strip()
    elif q1 == "2":
        follow = (row.get(cfg["unsure"], "") or "").strip()
    else:
        return "Unsure / unknown"
    if follow == "1":
        return "Identifies, not formally dx'd"
    if follow == "0":
        return "Does not identify"
    return "Unsure / unknown"


def collapse_lifetime_age(row: dict, side: str, fields_key: str):
    """
    Derive one age view from its branch fields.

    ``fields_key`` selects which set of branch fields to read -- see
    ``config.LIFETIME_AGE_VIEWS``. Takes the first non-blank numeric among
    them; the branches feeding any one view are mutually exclusive, so at most
    one is ever populated for a given record.

    Diagnosis age and identification age are derived separately rather than
    merged: they answer different questions, and combining them produces a
    mean that describes neither group.
    """
    for f in C.LIFETIME[side][fields_key]:
        v = (row.get(f, "") or "").strip()
        if v != "":
            try:
                return float(v)
            except ValueError:
                continue
    return None


def build_labeled_frame(df_raw: pd.DataFrame):
    """
    Produce a fully labeled DataFrame plus a record of unexpected codes and
    race/ethnicity conflicts for the data-quality panel.
    """
    present = [f for f in C.EXPORT_FIELDS if f in df_raw.columns]
    labeled_rows = []
    unexpected = []          # (record_index, field, raw)
    race_conflicts = []      # record_index
    hisp_conflicts = []      # record_index

    raw_records = df_raw.to_dict(orient="records")
    for i, rrow in enumerate(raw_records):
        rrow = {k: ("" if v is None else str(v).strip()) for k, v in rrow.items()}
        out = {}
        for f in present:
            lab, flagged = decode_value(f, rrow.get(f, ""))
            out[C.FIELD_LABELS.get(f, f)] = lab
            if flagged:
                unexpected.append((i, f, rrow.get(f, "")))

        race_lab, race_src, race_conf = collapse_race(rrow)
        out["Race (unified)"] = race_lab
        out["Race source"] = race_src
        if race_conf:
            race_conflicts.append(i)

        hisp_lab, hisp_conf = collapse_hispanic(rrow)
        out["Hispanic/Latino (unified)"] = hisp_lab
        if hisp_conf:
            hisp_conflicts.append(i)

        # Collapsed lifetime diagnosis status + the two derived ages
        for side in ("self", "informant"):
            out[C.LIFETIME[side]["status_label"]] = collapse_lifetime_status(rrow, side)
            for label_key, fields_key in C.LIFETIME_AGE_VIEWS:
                age = collapse_lifetime_age(rrow, side, fields_key)
                out[C.LIFETIME[side][label_key]] = "" if age is None else age

        labeled_rows.append(out)

    df_labeled = pd.DataFrame(labeled_rows)
    quality = {
        "unexpected": unexpected,
        "race_conflicts": race_conflicts,
        "hisp_conflicts": hisp_conflicts,
    }
    return df_labeled, quality, raw_records


# ===========================================================================
# ANALYTICS
# ===========================================================================
def site_of(rrow: dict) -> str:
    return C.VALUE_MAPS["site"].get((rrow.get("site", "") or "").strip(),
                                    "Unknown site")


def compute_categorical(raw_records, field):
    """Counts per label, broken down by site. Returns dict + ordered labels."""
    vmap = C.VALUE_MAPS.get(field, {})
    # ordered labels follow the dictionary's code order, plus extras
    ordered = list(vmap.values())
    by_site = defaultdict(Counter)   # site -> Counter(label)
    overall = Counter()
    for rrow in raw_records:
        s = site_of(rrow)
        lab, _ = decode_value(field, rrow.get(field, ""))
        if lab == "":
            continue
        by_site[s][lab] += 1
        overall[lab] += 1
    # include any unexpected labels that appeared
    for lab in overall:
        if lab not in ordered:
            ordered.append(lab)
    return {"ordered": ordered, "by_site": by_site, "overall": overall}


def compute_continuous(raw_records, field):
    """Summary stats by site for a numeric field."""
    by_site = defaultdict(list)
    allvals = []
    for rrow in raw_records:
        v = (rrow.get(field, "") or "").strip()
        if v == "":
            continue
        try:
            num = float(v)
        except ValueError:
            continue
        by_site[site_of(rrow)].append(num)
        allvals.append(num)

    def stats(vals):
        if not vals:
            return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
        s = sorted(vals)
        n = len(s)
        mean = sum(s) / n
        median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
        return {"n": n, "mean": mean, "median": median, "min": s[0], "max": s[-1]}

    rows = {site: stats(v) for site, v in by_site.items()}
    rows["All sites"] = stats(allvals)
    return rows


def compute_missingness(raw_records):
    """
    For each field: raw blanks, expected count (per branching), and
    'missing among expected'. Broken down overall + by site.
    """
    sites = sorted({site_of(r) for r in raw_records})
    results = {}
    # Trimmed per user request: only a short high-value list; the bulk of
    # "what's missing" now comes from the survey-completeness section.
    fields = [f for f in C.MISSINGNESS_FIELDS
              if any(f in r for r in raw_records[:1])] or C.MISSINGNESS_FIELDS
    for field in fields:
        pred = C.BRANCHING.get(field)  # None -> always expected
        raw_blank = 0
        expected = 0
        missing_expected = 0
        per_site = defaultdict(lambda: {"raw_blank": 0, "expected": 0,
                                        "missing_expected": 0, "total": 0})
        for rrow in raw_records:
            s = site_of(rrow)
            per_site[s]["total"] += 1
            val = (rrow.get(field, "") or "").strip()
            is_blank = val == ""
            if is_blank:
                raw_blank += 1
                per_site[s]["raw_blank"] += 1
            is_expected = True if pred is None else bool(pred(rrow))
            if is_expected:
                expected += 1
                per_site[s]["expected"] += 1
                if is_blank:
                    missing_expected += 1
                    per_site[s]["missing_expected"] += 1
        total = len(raw_records)
        results[field] = {
            "label": C.FIELD_LABELS.get(field, field),
            "kind": C.FIELD_KIND.get(field, "categorical"),
            "total": total,
            "raw_blank": raw_blank,
            "expected": expected,
            "missing_expected": missing_expected,
            "pct_missing_expected": (missing_expected / expected * 100) if expected else 0.0,
            "pct_raw_blank": (raw_blank / total * 100) if total else 0.0,
            "branching": pred is not None,
            "per_site": dict(per_site),
        }
    return results, sites


def compute_cati(raw_records, columns=None, queue_logic=None, fdl_logic=None):
    """
    CATI subscale/total statistics, restricted to *valid* administrations.

    A CATI score is only interpretable when every item was answered. REDCap
    still computes and exports a score when items are missing, so scores are
    filtered on the item-missingness counter before anything is summarized.
    Each record resolves to exactly one validity state:

      valid           counter == 0 -> scores are usable
      incomplete_items counter > 0 -> scores exist but are not interpretable
      unverifiable    scores present but the counter is blank/unparseable
      no_data         no scores and no counter (not taken yet)

    Only ``valid`` records contribute to the statistics. The other states are
    returned as counts so the section's denominator is always visible.

    Eligibility comes from the Survey Queue rule for the CATI instrument, so
    the denominator matches who was actually assigned it rather than the whole
    report. Records whose eligibility cannot be resolved are counted apart.

    If the rule references a field the export does not contain, it cannot be
    resolved for anyone. Rather than filter every record out and render an
    empty section, the denominator falls back to the full cohort and
    ``eligibility_filtered`` is returned False so the caller can say so.
    """
    missed_field = C.CATI_MISSED_FIELD
    score_fields = [f for f, _ in C.CATI_SCORES]

    # A field absent from the report is not the same as a field that is blank
    # for everyone. Without this check the section would report every eligible
    # participant as "not taken" when the columns were simply never exported.
    present = {str(c).strip().lower() for c in (columns or [])}
    absent_fields = ([f for f in [missed_field] + score_fields
                      if f.lower() not in present] if columns is not None
                     else [])

    # The eligibility rule can only filter if the fields it references were
    # actually exported. When they were not, the rule is unresolvable for
    # *every* record, and applying it would silently empty the denominator and
    # take the whole section down with it. Fall back to the full cohort and
    # report the degradation instead, so missing scores are never mistaken for
    # absent data.
    rule_missing_fields = SC.form_rule_missing_fields(
        C.CATI_FORM, columns, queue_logic or {}, fdl_logic or {}
    ) if columns is not None else []
    eligibility_filtered = not rule_missing_fields

    eligible, not_eligible, elig_unknown = [], 0, 0
    for rec in raw_records:
        if (queue_logic is None and fdl_logic is None) or rule_missing_fields:
            eligible.append(rec)
            continue
        should, _ = SC._should_administer(
            C.CATI_FORM, rec, queue_logic or {}, fdl_logic or {}
        )
        if should is True:
            eligible.append(rec)
        elif should is False:
            not_eligible += 1
        else:
            elig_unknown += 1

    states = Counter()
    by_site_state = defaultdict(Counter)
    valid_records = []
    over_max = 0
    missed_values = []

    for rec in eligible:
        raw = str(rec.get(missed_field, "") or "").strip()
        has_scores = any(
            str(rec.get(f, "") or "").strip() != "" for f in score_fields
        )
        try:
            missed = float(raw)
        except ValueError:
            missed = None

        if missed is None:
            state = "unverifiable" if has_scores else "no_data"
        elif missed == 0:
            state = "valid"
            valid_records.append(rec)
            missed_values.append(missed)
        else:
            state = "incomplete_items"
            missed_values.append(missed)
            if missed > C.CATI_MISSED_MAX:
                over_max += 1
        states[state] += 1
        by_site_state[site_of(rec)][state] += 1

    # Statistics are computed over valid records only.
    scores = []
    for field, label in C.CATI_SCORES:
        rows = compute_continuous(valid_records, field)
        scores.append({
            "field": field,
            "label": label,
            "rows": rows,
            "n": rows.get("All sites", {}).get("n", 0),
        })

    # A valid CATI whose score is nonetheless blank is a separate problem
    # from missing items, and would otherwise be invisible.
    n_valid = states["valid"]
    blank_scores = [
        s for s in scores if n_valid and s["n"] < n_valid
    ]

    return {
        "scores": scores,
        "states": states,
        "by_site_state": by_site_state,
        "state_order": ["valid", "incomplete_items", "unverifiable", "no_data"],
        "state_labels": {
            "valid": "Valid (all items answered)",
            "incomplete_items": "Incomplete items",
            "unverifiable": "Cannot verify",
            "no_data": "Not taken",
        },
        "n_valid": n_valid,
        "n_eligible": len(eligible),
        "n_not_eligible": not_eligible,
        "n_elig_unknown": elig_unknown,
        "n_total": len(raw_records),
        "over_max": over_max,
        "blank_scores": blank_scores,
        "sites": sorted({site_of(r) for r in eligible}),
        "mean_missed": (sum(missed_values) / len(missed_values)
                        if missed_values else 0.0),
        "absent_fields": absent_fields,
        "missed_field_absent": missed_field.lower() not in present
                               if columns is not None else False,
        # Eligibility provenance: whether the Survey Queue rule actually
        # filtered the denominator, and if not, which fields it needed.
        "eligibility_filtered": eligibility_filtered,
        "rule_missing_fields": rule_missing_fields,
    }


def compute_visit_attendance(cohort_records, all_records, visit_gate):
    """
    Split the enrolled cohort into participants who have attended their
    in-person visit and those still to come in.

    Attendance uses exactly the test the survey-completeness section already
    applies -- a qualifying status on the visit anchor instrument (the BDI,
    which opens every visit) -- via :func:`survey_completeness.visit_attended`.
    Reusing that predicate is the point: this figure and the anchor row's
    eligible count in the survey table are then guaranteed to agree.

    ``cohort_records`` is the enrolled (Include) cohort and drives the headline
    numbers. ``all_records`` is reported alongside it because the survey
    section gates on the full export, and the two denominators would otherwise
    look contradictory.

    Returns ``None`` when the gate is unavailable, so the caller omits the
    figure rather than reporting every participant as not yet seen.
    """
    if not visit_gate:
        return None

    by_site = defaultdict(lambda: {"attended": 0, "awaiting": 0})
    attended = 0
    for rec in cohort_records:
        came_in = bool(SC.visit_attended(visit_gate, rec))
        attended += came_in
        key = "attended" if came_in else "awaiting"
        by_site[site_of(rec)][key] += 1

    n_cohort = len(cohort_records)
    all_attended = sum(
        1 for rec in all_records if SC.visit_attended(visit_gate, rec)
    )
    return {
        "n_cohort": n_cohort,
        "attended": attended,
        "awaiting": n_cohort - attended,
        "pct_attended": (100.0 * attended / n_cohort) if n_cohort else 0.0,
        "by_site": dict(by_site),
        "sites": sorted(by_site),
        "all_records": len(all_records),
        "all_attended": all_attended,
        "all_awaiting": len(all_records) - all_attended,
        "anchor_form": visit_gate["anchor_form"],
        "anchor_col": visit_gate["anchor_status_col"],
    }


def compute_screening(raw_records):
    """
    Per-gate eligibility screening, applicability-aware.

    Restricted to the ASD arm. For every gate, each participant resolves to
    one of four states:

      not_applicable  the gate is branched away for their asd_group
      pass            answered with a qualifying code
      fail            answered with a disqualifying code
      unanswered      blank, or a value outside the gate's codes

    ``unanswered`` is kept separate from ``fail`` throughout. A blank normally
    means the item has not been reached yet (the WASI cutoffs wait on the
    in-person visit) or was skipped at data entry -- neither is an eligibility
    result, and conflating them overstates attrition.

    Gates are evaluated independently rather than cumulatively, so no
    participant is removed from a later gate by an earlier one.
    """
    cohort = [
        r for r in raw_records
        if str(r.get(C.SCREENING_COHORT_FIELD, "") or "").strip()
        in C.SCREENING_COHORT_VALUES
    ]
    sites = sorted({site_of(r) for r in cohort})

    def applicable(rec, key):
        codes, _label = C.SCREENING_APPLICABILITY[key]
        if codes is None:
            return True
        val = str(rec.get(C.SCREENING_GROUP_FIELD, "") or "").strip()
        return val in codes

    gates = []
    # participant -> True once any applicable gate fails / is unanswered
    any_fail = {id(r): False for r in cohort}
    any_unanswered = {id(r): False for r in cohort}

    for field, label, applies, pass_codes, fail_codes in C.SCREENING_GATES:
        counts = Counter()
        by_site = defaultdict(Counter)
        for rec in cohort:
            if not applicable(rec, applies):
                state = "not_applicable"
            else:
                val = str(rec.get(field, "") or "").strip()
                if val in pass_codes:
                    state = "pass"
                elif val in fail_codes:
                    state = "fail"
                    any_fail[id(rec)] = True
                else:
                    state = "unanswered"
                    any_unanswered[id(rec)] = True
            counts[state] += 1
            by_site[site_of(rec)][state] += 1

        n_app = counts["pass"] + counts["fail"] + counts["unanswered"]
        answered = counts["pass"] + counts["fail"]
        gates.append({
            "field": field,
            "label": label,
            "applies_label": C.SCREENING_APPLICABILITY[applies][1],
            "counts": counts,
            "by_site": by_site,
            "applicable": n_app,
            "answered": answered,
            "answered_pct": (answered / n_app * 100) if n_app else 0.0,
            "pass_pct": (counts["pass"] / answered * 100) if answered else 0.0,
        })

    # Roll-up: a participant is only "eligible so far" when every gate that
    # applies to them is answered and passing.
    rollup = Counter()
    rollup_by_site = defaultdict(Counter)
    for rec in cohort:
        if any_fail[id(rec)]:
            state = "Fails a criterion"
        elif any_unanswered[id(rec)]:
            state = "Screening incomplete"
        else:
            state = "Meets all applicable criteria"
        rollup[state] += 1
        rollup_by_site[site_of(rec)][state] += 1

    # Recorded Include/Exclude vs the computed roll-up.
    recorded_included = sum(
        1 for r in cohort
        if str(r.get(C.SCREENING_OUTCOME_FIELD, "") or "").strip()
        in C.SCREENING_OUTCOME_INCLUDE
    )
    included_but_not_clear = sum(
        1 for r in cohort
        if str(r.get(C.SCREENING_OUTCOME_FIELD, "") or "").strip()
        in C.SCREENING_OUTCOME_INCLUDE
        and (any_fail[id(r)] or any_unanswered[id(r)])
    )

    # asd_group drives applicability, so a blank one silently shrinks the
    # denominator of every branched gate. Surface it.
    missing_group = sum(
        1 for r in cohort
        if not str(r.get(C.SCREENING_GROUP_FIELD, "") or "").strip()
    )

    return {
        "gates": gates,
        "sites": sites,
        "n_cohort": len(cohort),
        "n_total": len(raw_records),
        "rollup": rollup,
        "rollup_by_site": rollup_by_site,
        "rollup_order": ["Meets all applicable criteria", "Fails a criterion",
                         "Screening incomplete"],
        "recorded_included": recorded_included,
        "included_but_not_clear": included_but_not_clear,
        "missing_group": missing_group,
    }


def compute_funnel(raw_records):
    """
    Eligibility funnel: how many records pass each gate cumulatively,
    overall and by site. A record must pass all prior gates to be counted
    at the current one (true funnel).
    """
    sites = sorted({site_of(r) for r in raw_records})
    overall = []
    by_site = {s: [] for s in sites}

    # Starting cohort = everyone
    surviving = {id(r): r for r in raw_records}
    overall.append(("Total records", len(raw_records)))
    for s in sites:
        by_site[s].append(("Total records",
                            sum(1 for r in raw_records if site_of(r) == s)))

    for field, label, pred in C.FUNNEL_GATES:
        still = {}
        for k, r in surviving.items():
            try:
                ok = bool(pred(r))
            except Exception:
                ok = False
            if ok:
                still[k] = r
        surviving = still
        overall.append((label, len(surviving)))
        for s in sites:
            by_site[s].append(
                (label, sum(1 for r in surviving.values() if site_of(r) == s))
            )
    return {"overall": overall, "by_site": by_site, "sites": sites}


def compute_site_overview(raw_records):
    """Top-line counts per site."""
    c = Counter(site_of(r) for r in raw_records)
    return c


# ===========================================================================
# RENDERING  (self-contained HTML; no external assets)
# ===========================================================================
def esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def fmt(x, nd=1):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def bar_svg(pairs, max_val=None, width=460, bar_h=22, gap=8,
            colors=None, default_color="var(--accent)"):
    """
    Horizontal bar chart as inline SVG. pairs = [(label, value), ...].
    `colors` may be a dict {label: color} or a list parallel to pairs.
    """
    if not pairs:
        return "<div class='empty'>No data</div>"
    max_val = max_val or max((v for _, v in pairs), default=1) or 1
    label_w = 180
    plot_w = width - label_w - 50
    height = len(pairs) * (bar_h + gap) + gap
    parts = [f"<svg viewBox='0 0 {width} {height}' class='bars' "
             f"role='img' xmlns='http://www.w3.org/2000/svg'>"]
    y = gap
    for idx, (label, val) in enumerate(pairs):
        if isinstance(colors, dict):
            col = colors.get(label, default_color)
        elif isinstance(colors, list):
            col = colors[idx % len(colors)]
        else:
            col = default_color
        w = (val / max_val) * plot_w if max_val else 0
        parts.append(
            f"<text x='{label_w-8}' y='{y+bar_h*0.68}' "
            f"class='bl' text-anchor='end'>{esc(label)}</text>"
        )
        parts.append(
            f"<rect x='{label_w}' y='{y}' width='{max(w,0):.1f}' "
            f"height='{bar_h}' rx='3' fill='{col}'></rect>"
        )
        parts.append(
            f"<text x='{label_w+max(w,0)+6:.1f}' y='{y+bar_h*0.68}' "
            f"class='bv'>{val}</text>"
        )
        y += bar_h + gap
    parts.append("</svg>")
    return "".join(parts)


def donut_svg(pairs, colors=None, size=150, thickness=34):
    """
    Donut chart for a single categorical breakdown. pairs=[(label,val),...].
    Returns SVG + a legend (caller places it). Colors: list or dict.
    """
    total = sum(v for _, v in pairs)
    if total == 0:
        return "<div class='empty'>No data</div>"
    cx = cy = size / 2
    r = (size - thickness) / 2
    import math
    circ = 2 * math.pi * r
    parts = [f"<svg viewBox='0 0 {size} {size}' class='donut' "
             f"role='img' xmlns='http://www.w3.org/2000/svg'>"]
    offset = 0.0
    for idx, (label, val) in enumerate(pairs):
        if val == 0:
            continue
        if isinstance(colors, dict):
            col = colors.get(label, C.CAT_PALETTE[idx % len(C.CAT_PALETTE)])
        elif isinstance(colors, list):
            col = colors[idx % len(colors)]
        else:
            col = C.CAT_PALETTE[idx % len(C.CAT_PALETTE)]
        frac = val / total
        dash = frac * circ
        parts.append(
            f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='none' "
            f"stroke='{col}' stroke-width='{thickness}' "
            f"stroke-dasharray='{dash:.2f} {circ-dash:.2f}' "
            f"stroke-dashoffset='{-offset:.2f}' "
            f"transform='rotate(-90 {cx} {cy})'></circle>"
        )
        offset += dash
    parts.append(
        f"<text x='{cx}' y='{cy-2}' class='donut-n' text-anchor='middle'>"
        f"{total}</text>"
        f"<text x='{cx}' y='{cy+14}' class='donut-l' text-anchor='middle'>"
        f"total</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def legend_html(pairs, colors, total=None, vertical=False):
    """Color legend chips with label, count, and percent."""
    total = total if total is not None else sum(v for _, v in pairs)
    cls = "legend vert" if vertical else "legend"
    out = [f"<div class='{cls}'>"]
    for idx, (label, val) in enumerate(pairs):
        if isinstance(colors, dict):
            col = colors.get(label, C.CAT_PALETTE[idx % len(C.CAT_PALETTE)])
        else:
            col = colors[idx % len(colors)]
        pct = (val / total * 100) if total else 0
        out.append(
            f"<div class='leg-item'><span class='swatch' "
            f"style='background:{col}'></span>"
            f"<span class='leg-l'>{esc(label)}</span>"
            f"<span class='leg-v'>{val} · {pct:.0f}%</span></div>"
        )
    out.append("</div>")
    return "".join(out)


def site_stacked_bar(cat, sites, width=460, height=208):
    """
    Vertical stacked bar per site, each segment a colored answer category.
    Gives a colorful at-a-glance comparison across sites.
    """
    by_site = cat["by_site"]
    ordered = [l for l in cat["ordered"] if cat["overall"].get(l, 0) > 0]
    sites = [s for s in sites if s in by_site] or list(by_site.keys())
    if not sites or not ordered:
        return "<div class='empty'>No data</div>", {}
    # Extra top padding keeps the largest value label fully inside the SVG.
    pad_l, pad_b, pad_t = 30, 26, 26
    plot_w = width - pad_l - 8
    plot_h = height - pad_b - pad_t
    bw = min(54, plot_w / max(len(sites), 1) * 0.6)
    gap = (plot_w - bw * len(sites)) / (len(sites) + 1)
    max_total = max(sum(by_site[s].values()) for s in sites) or 1
    palette = {lab: C.CAT_PALETTE[i % len(C.CAT_PALETTE)]
               for i, lab in enumerate(ordered)}
    parts = [f"<svg viewBox='0 0 {width} {height}' class='stack' "
             f"role='img' xmlns='http://www.w3.org/2000/svg'>"]
    x = pad_l + gap
    for s in sites:
        col_total = sum(by_site[s].values())
        y = pad_t + plot_h
        for lab in ordered:
            v = by_site[s].get(lab, 0)
            if v == 0:
                continue
            h = (v / max_total) * plot_h
            y -= h
            parts.append(
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw:.1f}' "
                f"height='{h:.1f}' fill='{palette[lab]}'></rect>"
            )
        parts.append(
            f"<text x='{x+bw/2:.1f}' y='{pad_t+plot_h+16:.1f}' "
            f"class='xl' text-anchor='middle'>{esc(s[:10])}</text>"
        )
        bar_top = pad_t + plot_h - ((col_total / max_total) * plot_h)
        value_y = max(16.0, bar_top - 6.0)
        parts.append(
            f"<text x='{x+bw/2:.1f}' y='{value_y:.1f}' "
            f"class='xv' text-anchor='middle'>{col_total}</text>"
        )
        x += bw + gap
    parts.append("</svg>")
    return "".join(parts), palette


def total_of(cat):
    return sum(cat["overall"].values())


# Fixed colors for survey outcomes (coherent across the section).
SURVEY_OUTCOME_COLORS = {
    "Complete": "#4cc4b0",     # teal
    "Unconfirmed": "#e9a23b",  # amber
    "Incomplete": "#e0603e",   # coral
}


def completeness_bar(overall, order, colors, width=460, height=20):
    """Horizontal segmented bar across logic-eligible participant records."""
    segs = [(k, overall.get(k, 0)) for k in order
            if overall.get(k, 0) > 0]
    total = sum(v for _, v in segs)
    if total == 0:
        return "<div class='empty'>No eligible participants</div>"
    parts = [f"<svg viewBox='0 0 {width} {height}' class='compbar' "
             f"preserveAspectRatio='none' xmlns='http://www.w3.org/2000/svg'>"]
    x = 0.0
    for k, v in segs:
        w = v / total * width
        parts.append(
            f"<rect x='{x:.2f}' y='0' width='{w:.2f}' height='{height}' "
            f"fill='{colors[k]}'><title>{esc(k)}: {v}</title></rect>"
        )
        x += w
    parts.append("</svg>")
    return "".join(parts)


def stacked_table(cat, sites, show_total_row=True):
    """HTML count table: labels x sites + total, with a TOTAL row."""
    ordered = cat["ordered"]
    by_site = cat["by_site"]
    overall = cat["overall"]
    sites = [s for s in sites if s in by_site] or list(by_site.keys())
    head = "".join(f"<th>{esc(s)}</th>" for s in sites)
    rows = []
    col_tot = {s: 0 for s in sites}
    grand = 0
    for lab in ordered:
        if overall.get(lab, 0) == 0:
            continue
        cells = []
        for s in sites:
            v = by_site[s].get(lab, 0)
            col_tot[s] += v
            cells.append(f"<td>{v}</td>")
        grand += overall.get(lab, 0)
        rows.append(f"<tr><th class='rl'>{esc(lab)}</th>{''.join(cells)}"
                    f"<td class='tot'>{overall.get(lab,0)}</td></tr>")
    total_row = ""
    if show_total_row:
        tcells = "".join(f"<td class='tot'>{col_tot[s]}</td>" for s in sites)
        total_row = (f"<tr class='trow'><th class='rl'>Total</th>{tcells}"
                     f"<td class='tot'>{grand}</td></tr>")
    return (f"<table class='cnt'><thead><tr><th></th>{head}"
            f"<th class='tot'>Total</th></tr></thead>"
            f"<tbody>{''.join(rows)}{total_row}</tbody></table>")




def render_survey_section(ctx):
    """Render logic-filtered REDCap survey completeness for all records."""
    sv = ctx["survey"]
    forms = [d for d in sv["all"] if d["eligible"] > 0]
    display_rank = {
        form: position
        for position, form in enumerate(C.SURVEY_DISPLAY_ORDER)
    }

    forms.sort(
        key=lambda d: (
            display_rank.get(d["form"], len(display_rank)),
            C.SURVEY_DISPLAY_NAMES.get(
                d["form"],
                SC.humanize_form(d["form"]),
            ).lower(),
        )
    )
    order = SC.OUTCOME_ORDER
    logic_available = sv.get("logic_available", False)

    H = ["<section><h2>Survey completeness</h2>"]
    if logic_available:
        H.append(
            "<p class='desc'>Form Display Logic and Survey Queue rules are "
            "applied <b>before</b> REDCap completion status is counted. A "
            "participant contributes to a survey only when the form was intended "
            "for that participant. The table therefore contains only REDCap's "
            "three completion states: <b>Complete</b>, <b>Unconfirmed</b>, and "
            "<b>Incomplete</b>.</p>"
        )
    else:
        H.append(
            "<p class='desc'>No Survey Queue or Form Display Logic was loaded, "
            "so every returned form-status field is treated as generally "
            "applicable. The table contains REDCap's three exported completion "
            "states.</p>"
        )

    leg_items = []
    for k in order:
        leg_items.append(
            f"<div class='leg-item'><span class='swatch' "
            f"style='background:{SURVEY_OUTCOME_COLORS[k]}'></span>"
            f"<span class='leg-l'>{esc(k)}</span></div>"
        )
    H.append(f"<div class='legend'>{''.join(leg_items)}</div>")

    logic_text = (
        f"logic from <b>{sv['n_queue']}</b> queue rules and "
        f"<b>{sv['n_fdl']}</b> display rules"
        if logic_available else
        "<span class='flag'><b>no queue/display logic loaded</b></span>"
    )
    excluded = sum(d.get("excluded_by_logic", 0) for d in sv["all"])
    unknown = sum(d.get("eligibility_unknown", 0) for d in sv["all"])
    unavailable = sum(d.get("status_unavailable", 0) for d in sv["all"])
    H.append(
        "<div class='note'>"
        f"<b>{len(forms)}</b> forms have at least one eligible participant · "
        f"{logic_text} · completion is calculated from <b>all {ctx['total_records']} "
        "records</b>, not only records currently marked Include. "
        f"<b>{excluded}</b> ineligible participant-form combinations were "
        "excluded before status counting."
        "</div>"
    )

    visit_gate = sv.get("visit_gate")
    awaiting = sum(d.get("awaiting_visit", 0) for d in sv["all"])
    if visit_gate:
        anchor_name = sv.get("visit_anchor_name") or "the anchor instrument"
        attended = sv.get("n_visit_attended", 0)
        H.append(
            "<div class='note' style='border-left-color:var(--good)'>"
            f"<b>In-person visit gate active.</b> <b>{attended}</b> of "
            f"{ctx['total_records']} participants have a complete "
            f"<b>{esc(anchor_name)}</b>. Because the gate also applies to "
            f"<b>{esc(anchor_name)}</b> itself, read that row's <b>Eligible</b> "
            "count (not its percentage) as the visit-attendance figure."
            # f"<b>Every in-person visit opens with that "
            # "instrument, so a complete one means the visit took place and the "
            # f"rest of the battery is due. The {sv.get('n_visit_gated', 0)} "
            # "in-person and post-visit surveys are therefore counted only for "
            # "those participants, and a pending visit is not reported as "
            # f"missing data. <b>{awaiting}</b> participant-form combinations "
            # "were held back on that basis. 
            "</div>"
        )
    elif getattr(C, "INPERSON_VISIT_GATED_FORMS", set()):
        H.append(
            "<div class='note' style='border-left-color:var(--warn)'>"
            "<span class='flag'><b>In-person visit gate disabled.</b></span> "
            "The anchor instrument's status column was not returned by report "
            f"{esc(str(C.REPORT_ID))}, so in-person surveys count participants "
            "who have not yet attended their visit. Completion percentages for "
            "those forms will read artificially low."
            "</div>"
        )

    missing_logic_fields = sv.get("missing_logic_fields", [])
    if missing_logic_fields:
        H.append(
            "<div class='note' style='border-left-color:var(--warn)'>"
            f"<span class='flag'><b>{len(missing_logic_fields)}</b> field(s) "
            "required by the loaded administration logic were absent from the "
            f"API report:</span> {', '.join(esc(x) for x in missing_logic_fields)}. "
            "Participant-form combinations requiring those fields were excluded "
            "because eligibility could not be established."
            "</div>"
        )
    elif unknown:
        H.append(
            "<div class='note' style='border-left-color:var(--accent2)'>"
            f"<b>{unknown}</b> participant-form combinations had insufficient "
            "record-level data to evaluate their display rule and were excluded "
            "from completion denominators."
            "</div>"
        )

    if unavailable:
        H.append(
            "<div class='note' style='border-left-color:var(--warn)'>"
            f"<span class='flag'><b>{unavailable}</b> logic-eligible "
            "participant-form combinations lacked a valid 0/1/2 REDCap status "
            "and were excluded.</span> This should normally be zero."
            "</div>"
        )

    missing_expected = sv.get("missing_expected_fields", [])
    if missing_expected:
        preview = ", ".join(esc(x) for x in missing_expected[:6])
        more = len(missing_expected) - 6
        if more > 0:
            preview += f", … (+{more} more)"
        H.append(
            "<div class='note' style='border-left-color:var(--warn)'>"
            f"<span class='flag'><b>{len(missing_expected)}</b> configured "
            f"completion field(s) were absent from REDCap report "
            f"{esc(str(C.REPORT_ID))}.</span> {preview}. A field existing in the "
            "project is not enough; it must also be included in the API report."
            "</div>"
        )

    unmatched_rules = sv.get("unmatched_logic_rules", [])
    if unmatched_rules:
        H.append(
            "<div class='note' style='border-left-color:var(--accent2)'>"
            f"<b>{len(unmatched_rules)}</b> active queue/display rule(s) did not "
            "match a returned <code>*_complete</code> field. Inactive <code>1=0"
            "</code> rules are intentionally ignored in this warning."
            "</div>"
        )

    H.append("<table class='cnt survey'><thead><tr>"
             "<th class='rl'>Survey / instrument</th>"
             "<th class='rl'>Completion among eligible</th>"
             "<th>Complete</th><th>Uncf.</th><th>Incompl.</th>"
             "<th>Eligible</th>"
             "</tr></thead><tbody>")
    for d in forms:
        ov = d["overall"]
        title = C.SURVEY_DISPLAY_NAMES.get(
            d["form"],
            SC.humanize_form(d["form"]),
        )
        bar = completeness_bar(ov, order, SURVEY_OUTCOME_COLORS)
        pct = d["complete_pct"]
        srcs = []
        if d["in_queue"]:
            srcs.append("Q")
        if d["in_fdl"]:
            srcs.append("F")
        if d.get("visit_gated"):
            srcs.append("V")
        srctag = "".join(srcs) or "—"
        H.append(
            f"<tr>"
            f"<td class='rl'>{esc(title)}"
            f"<span class='srctag'>{srctag}</span></td>"
            f"<td class='rl barcell'>{bar}"
            f"<span class='pctlab'>{pct:.0f}%</span></td>"
            f"<td>{ov.get('Complete',0)}</td>"
            f"<td>{ov.get('Unconfirmed',0)}</td>"
            f"<td>{ov.get('Incomplete',0)}</td>"
            f"<td class='tot'>{d['eligible']}</td>"
            f"</tr>"
        )
    H.append("</tbody></table>")
    H.append(
        "<div class='note' style='margin-top:12px'>The Eligible column is the "
        "number of participants whose Queue/FDL rule evaluated true and whose "
        "REDCap status was 0, 1, or 2. REDCap status values attached to forms "
        "whose rule evaluated false are intentionally ignored; they do not mean "
        "the participant should have received that survey. <b>Q</b>/<b>F</b> "
        "identify Survey Queue and Form Display Logic coverage; <b>V</b> marks "
        "a form whose denominator is limited to participants who have "
        "completed their in-person visit.</div>"
    )
    H.append("</section>")
    return "".join(H)


def render_html(ctx, print_mode=False) -> str:
    css = """
    :root{
      --bg:#0f1417; --panel:#171f24; --ink:#e8eef1; --muted:#8aa0ab;
      --line:#27343b; --accent:#4cc4b0; --accent2:#e9a23b; --warn:#e0603e;
      --good:#4cc4b0;
    }
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--ink);
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
      font-size:14px;line-height:1.5}
    .wrap{max-width:1100px;margin:0 auto;padding:40px 28px 80px}
    header.top{border-bottom:2px solid var(--accent);padding-bottom:18px;
      margin-bottom:6px}
    .eyebrow{font-family:'SF Mono',ui-monospace,'Cascadia Mono','Roboto Mono',Menlo,Consolas,monospace;letter-spacing:.18em;
      text-transform:uppercase;font-size:11px;color:var(--accent);margin:0}
    h1{font-family:Georgia,'Times New Roman',serif;font-weight:600;
      font-size:30px;margin:6px 0 4px}
    .sub{color:var(--muted);margin:0;font-size:13px}
    .kpis{display:flex;gap:14px;flex-wrap:wrap;margin:26px 0 8px}
    .kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;
      padding:16px 20px;min-width:140px}
    .kpi .n{font-family:'SF Mono',ui-monospace,'Cascadia Mono','Roboto Mono',Menlo,Consolas,monospace;font-size:28px;font-weight:600;
      color:var(--ink)}
    .kpi .l{color:var(--muted);font-size:12px;margin-top:2px}
    .kpi .kpi-sub{display:block;font-size:10.5px;opacity:.75;
      font-family:'SF Mono',ui-monospace,'Cascadia Mono','Roboto Mono',Menlo,Consolas,monospace}
    section{background:var(--panel);border:1px solid var(--line);
      border-radius:12px;padding:22px 24px;margin:22px 0}
    section > h2{font-family:Georgia,'Times New Roman',serif;font-size:19px;
      margin:0 0 4px;font-weight:600}
    section > .desc{color:var(--muted);font-size:12.5px;margin:0 0 16px}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
    @media(max-width:760px){.grid{grid-template-columns:1fr}}
    .card{border:1px solid var(--line);border-radius:9px;padding:14px 16px;
      background:#131a1e}
    .card h3{font-size:14px;margin:0 0 10px;font-weight:600}
    .card h3 .meta{color:var(--muted);font-weight:400;font-size:11.5px;
      font-family:'SF Mono',ui-monospace,'Cascadia Mono','Roboto Mono',Menlo,Consolas,monospace;margin-left:6px}
    table{border-collapse:collapse;width:100%;font-size:12.5px}
    th,td{text-align:right;padding:5px 8px;border-bottom:1px solid var(--line)}
    th.rl,td.rl,th:first-child{text-align:left}
    thead th{color:var(--muted);font-weight:600;font-size:11px;
      text-transform:uppercase;letter-spacing:.04em}
    .tot{color:var(--accent);font-weight:600}
    td.rl{color:var(--ink)}
    svg.bars{width:100%;height:auto}
    svg.bars .bl{fill:var(--muted);font-size:11px;
      font-family:sans-serif}
    svg.bars .bv{fill:var(--ink);font-size:11px;font-weight:600;
      font-family:'SF Mono',ui-monospace,'Cascadia Mono','Roboto Mono',Menlo,Consolas,monospace}
    .miss-bar{height:9px;border-radius:5px;background:#22303a;overflow:hidden;
      min-width:60px}
    .miss-fill{height:100%;background:var(--warn)}
    .pill{display:inline-block;font-family:'SF Mono',ui-monospace,'Cascadia Mono','Roboto Mono',Menlo,Consolas,monospace;
      font-size:10.5px;padding:1px 7px;border-radius:20px;border:1px solid var(--line)}
    .pill.branch{color:var(--accent2);border-color:var(--accent2)}
    .funnel-row{display:flex;align-items:center;gap:12px;margin:5px 0}
    .funnel-row .lab{width:230px;font-size:12.5px;color:var(--ink)}
    .funnel-track{flex:1;height:24px;background:#131a1e;border-radius:5px;
      border:1px solid var(--line);overflow:hidden;position:relative}
    .funnel-fill{height:100%;background:linear-gradient(90deg,var(--accent),#2f8f80)}
    .funnel-row .cnt{width:120px;text-align:right;
      font-family:'SF Mono',ui-monospace,'Cascadia Mono','Roboto Mono',Menlo,Consolas,monospace;font-size:12.5px}
    .funnel-row .cnt .drop{color:var(--warn);margin-left:4px;font-size:11px}
    .flag{color:var(--warn)}
    .ok{color:var(--good)}
    .note{background:#131a1e;border-left:3px solid var(--accent);
      padding:10px 14px;border-radius:0 6px 6px 0;color:var(--muted);
      font-size:12.5px;margin:14px 0 0;line-height:1.9}
    /* grids */
    .grid-3{grid-template-columns:1fr 1fr 1fr}
    @media(max-width:900px){.grid-3{grid-template-columns:1fr}}
    .status-stack{display:flex;flex-direction:column;gap:18px}
    .status-card-body{display:grid;grid-template-columns:240px minmax(0,1fr);
      gap:22px;align-items:start}
    .status-card-body .donut-wrap{margin:0;min-height:0;padding:0 20px 0 0;
      border-bottom:none;border-right:1px solid var(--line)}
    .status-table-wrap{min-width:0;overflow-x:auto}
    @media(max-width:760px){
      .status-card-body{grid-template-columns:1fr}
      .status-card-body .donut-wrap{padding:0 0 12px;border-right:none;
        border-bottom:1px solid var(--line)}
    }
    /* feature (prominent) panel */
    section.feature{border-color:var(--accent);
      box-shadow:0 0 0 1px var(--accent) inset,0 8px 30px rgba(0,0,0,.25)}
    section.feature > h2{color:var(--accent)}
    .feature-card{background:#0d181c}
    /* total row in tables */
    tr.trow th,tr.trow td{border-top:2px solid var(--line);
      border-bottom:none;font-weight:600;padding-top:7px}
    tr.trow .rl{color:var(--muted);text-transform:uppercase;
      font-size:10.5px;letter-spacing:.05em}
    /* donut */
    svg.donut{width:130px;height:130px;flex:0 0 auto}
    svg.donut .donut-n{fill:var(--ink);font-size:22px;font-weight:600;
      font-family:'SF Mono',ui-monospace,monospace}
    svg.donut .donut-l{fill:var(--muted);font-size:9px;
      text-transform:uppercase;letter-spacing:.1em}
    /* donut card: donut centered, legend stacked underneath, fixed min-height
       so the table below starts at the same y across sibling cards */
    .donut-wrap{display:flex;flex-direction:column;align-items:center;
      gap:10px;margin-bottom:14px;min-height:210px;
      padding-bottom:10px;border-bottom:1px solid var(--line)}
    .donut-wrap .legend{width:100%}
    /* stacked bar chart box */
    .chartbox{margin-bottom:10px}
    svg.stack{width:100%;height:auto}
    svg.stack .xl{fill:var(--muted);font-size:10px;
      font-family:-apple-system,sans-serif}
    svg.stack .xv{fill:var(--ink);font-size:10.5px;font-weight:600;
      font-family:'SF Mono',ui-monospace,monospace}
    /* legend: default inline-wrap (used under stacked bars) */
    .legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin:4px 0 12px}
    /* vertical legend (used inside donut cards) — one item per row */
    .legend.vert{flex-direction:column;flex-wrap:nowrap;gap:5px;
      align-items:stretch}
    .legend.vert .leg-item{justify-content:flex-start;width:100%}
    .legend.vert .leg-v{margin-left:auto}
    .leg-item{display:flex;align-items:center;gap:6px;font-size:11.5px;
      min-width:0}
    .leg-l{color:var(--ink);white-space:nowrap;overflow:hidden;
      text-overflow:ellipsis}
    .leg-v{color:var(--muted);font-family:'SF Mono',ui-monospace,monospace;
      font-size:11px;white-space:nowrap}
    .swatch{width:11px;height:11px;border-radius:3px;flex:0 0 auto}
    /* survey completeness table */
    table.survey td.barcell{width:200px;position:relative;padding-right:44px}
    svg.compbar{width:170px;height:16px;border-radius:3px;display:inline-block;
      vertical-align:middle}
    table.survey .pctlab{position:absolute;right:8px;top:50%;
      transform:translateY(-50%);font-family:'SF Mono',ui-monospace,monospace;
      font-size:11px;color:var(--ink)}
    table.survey td.muted{color:var(--muted)}
    .srctag{display:inline-block;margin-left:8px;font-size:9px;
      font-family:'SF Mono',ui-monospace,monospace;color:var(--muted);
      border:1px solid var(--line);border-radius:3px;padding:0 4px;
      vertical-align:middle}
    table.survey th.rl:nth-child(2){min-width:190px}
    .sitechip{display:inline-flex;align-items:center;gap:6px;margin-right:14px}
    footer{color:var(--muted);font-size:11.5px;margin-top:30px;
      border-top:1px solid var(--line);padding-top:14px;
      font-family:'SF Mono',ui-monospace,'Cascadia Mono','Roboto Mono',Menlo,Consolas,monospace}
    .twocol{column-count:2;column-gap:26px}
    @media(max-width:760px){.twocol{column-count:1}}
    .dq-item{break-inside:avoid;margin-bottom:8px;font-size:12.5px}
    @media print{
      body{background:#fff;color:#111;font-size:11px}
      .wrap{max-width:none;padding:0}
      section,.kpi,.card{border-color:#ccc;background:#fff;
        break-inside:avoid;page-break-inside:avoid}
      section{box-shadow:none}
      .eyebrow,.tot{color:#0a7d6c}
      h1,section>h2,.card h3{color:#111}
      .sub,.desc,.l,.meta,.bl{color:#555}
      .bv{fill:#111}.bl{fill:#555}
      .funnel-fill{background:#0a7d6c}
      .miss-fill{background:#c0492e}
    }
    """ + T1.table1_css()
    # No web fonts: keeps the dashboard fully offline (works on locked-down
    # clinician machines and in the PDF renderer). System stacks below.
    fonts = ""

    # In print mode, override the dark tokens with a light, ink-friendly
    # palette and force it on-screen (wkhtmltopdf won't honor @media print here).
    if print_mode:
        css += """
        :root{--bg:#ffffff;--panel:#ffffff;--ink:#16242b;--muted:#5d6f78;
          --line:#d4dde1;--accent:#0a7d6c;--accent2:#b9781f;--warn:#c0492e;
          --good:#0a7d6c;}
        body{background:#fff;color:#16242b}
        section,.kpi,.card{box-shadow:none;break-inside:avoid;
          page-break-inside:avoid}
        .card{background:#f7f9fa}
        .note{background:#f0f6f5;color:#5d6f78}
        .miss-bar{background:#e7edf0}
        .funnel-track{background:#f0f4f5}
        .note,.card,.funnel-track{}
        svg.bars .bv{fill:#16242b}svg.bars .bl{fill:#5d6f78}
        section{border-color:#d4dde1}
        section.feature{box-shadow:0 0 0 1px #0a7d6c inset}
        .feature-card{background:#f2f7f6}
        svg.donut .donut-n{fill:#16242b}
        svg.stack .xv{fill:#16242b}svg.stack .xl{fill:#5d6f78}
        .leg-l{color:#16242b}
        tr.trow th,tr.trow td{border-top-color:#c2ccd1}
        """
    H = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
         f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{esc(ctx['title'])}</title>{fonts}<style>{css}</style></head><body><div class='wrap'>"]

    # ---- header + KPIs
    H.append(
        f"<header class='top'><p class='eyebrow'>ACE Wave 3 · Produced by the DCC</p>"
        f"<h1>{esc(ctx['title'])}</h1>"
        f"<p class='sub'>Generated {esc(ctx['generated'])} · "
        f"aggregate-only view, no participant-level data shown</p></header>"
    )

    # Manuscript-style Table 1 is the first substantive dashboard panel.  The
    # interactive HTML switches only among precomputed aggregate views; the
    # PDF intentionally renders the default non-withdrawn / study-group view.
    H.append(T1.render_panel(
        ctx["table1"], export_links=ctx.get("table1_export_links"),
        print_mode=print_mode,
    ))

    total = ctx["total_records"]
    n_sites = len(ctx["site_overview"])
    n_incl = ctx["n_included"]
    H.append("<div class='kpis'>")
    H.append(f"<div class='kpi'><div class='n'>{total}</div>"
             f"<div class='l'>Total records</div></div>")
    H.append(f"<div class='kpi'><div class='n'>{n_incl}</div>"
             f"<div class='l'>Included records</div></div>")
    # Awaiting visit: enrolled participants who have not yet come in, by the
    # same anchor test the survey section uses. Omitted entirely when the gate
    # is unavailable -- reporting 0 would misread "cannot tell" as "all seen".
    va = ctx.get("visit_attendance")
    if va:
        anchor_label = esc(va["anchor_form"])
        H.append(
            f"<div class='kpi' title='Enrolled participants with no complete "
            f"{anchor_label} status — the instrument that opens every "
            f"in-person visit.'>"
            f"<div class='n'>{va['awaiting']}</div>"
            f"<div class='l'>Awaiting visit "
            f"<span class='kpi-sub'>of {va['n_cohort']} enrolled</span></div>"
            f"</div>"
        )
    H.append(f"<div class='kpi'><div class='n'>{n_sites}</div>"
             f"<div class='l'>Sites reporting</div></div>")
    dq = ctx["quality"]
    miss_flags = ctx["missingness_flags"]
    n_flags = (len(dq["unexpected"]) + len(dq["race_conflicts"])
               + len(dq["hisp_conflicts"]) + len(miss_flags))
    H.append(f"<div class='kpi'><div class='n'>{n_flags}</div>"
             f"<div class='l'>Data-quality flags</div></div>")
    H.append("</div>")

    # ---- site overview: total vs included, side by side
    H.append("<section><h2>Records by site</h2>"
             "<p class='desc'>Left: all records (includes partially-completed records "
             "that have only a record ID). Right: records marked <b>Include</b> (the "
             "meaningful enrolled cohort).</p>")
    so = sorted(ctx["site_overview"].items(), key=lambda kv: -kv[1])
    so_incl = sorted(ctx["site_overview_incl"].items(), key=lambda kv: -kv[1])
    # shared max so the two charts are visually comparable
    shared_max = max([v for _, v in so] + [1])
    H.append("<div class='grid'>")
    H.append("<div class='card'><h3>All records "
             f"<span class='meta'>n = {total}</span></h3>"
             f"{bar_svg(so, max_val=shared_max, colors=C.SITE_COLORS)}</div>")
    H.append("<div class='card'><h3>Included only "
             f"<span class='meta'>n = {n_incl}</span></h3>"
             f"{bar_svg(so_incl, max_val=shared_max, colors=C.SITE_COLORS)}</div>")
    H.append("</div></section>")

    # ---- PROMINENT status panel (inclusion / status / clinician dx)
    H.append("<section class='feature'><h2>Participant status</h2>"
             "<p class='desc'>Headline state of the cohort: inclusion decisions, "
             "participant status, and clinician-confirmed diagnosis.</p>")
    H.append("<div class='status-stack'>")
    for field, cat in ctx["status_panel"]:
        label = C.FIELD_LABELS.get(field, field)
        pairs = [(l, cat["overall"][l]) for l in cat["ordered"]
                 if cat["overall"].get(l, 0) > 0]
        donut = donut_svg(pairs, colors=C.CAT_PALETTE)
        leg = legend_html(pairs, C.CAT_PALETTE, vertical=True)
        H.append(
            f"<div class='card feature-card'><h3>{esc(label)}"
            f"<span class='meta'>({esc(field)})</span></h3>"
            f"<div class='status-card-body'>"
            f"<div class='donut-wrap'>{donut}{leg}</div>"
            f"<div class='status-table-wrap'>{stacked_table(cat, ctx['sites'])}</div>"
            f"</div></div>"
        )
    H.append("</div></section>")

    # ---- demographics: race + hispanic side by side (race as stacked bars)
    H.append("<section><h2>Race &amp; ethnicity</h2>"
             "<p class='desc'>Race unifies self-report and informant-report into a "
             "single mutually-exclusive category. "
             "Hispanic/Latino ethnicity is reported "
             "separately, as the federal standard treats it as a distinct axis.</p>")
    H.append("<div class='grid'>")
    # race: stacked bar by site + table
    race_bar, race_pal = site_stacked_bar(ctx["race_cat"], ctx["sites"])
    race_pairs = [(l, ctx["race_cat"]["overall"][l])
                  for l in ctx["race_cat"]["ordered"]
                  if ctx["race_cat"]["overall"].get(l, 0) > 0]
    H.append("<div class='card'><h3>Race (unified)</h3>"
             f"<div class='chartbox'>{race_bar}</div>"
             f"{legend_html(race_pairs, race_pal)}"
             f"{stacked_table(ctx['race_cat'], ctx['sites'])}</div>")
    # hispanic: donut + table
    hisp_pairs = [(l, ctx["hisp_cat"]["overall"][l])
                  for l in ctx["hisp_cat"]["ordered"]
                  if ctx["hisp_cat"]["overall"].get(l, 0) > 0]
    hisp_donut = donut_svg(hisp_pairs, colors=C.CAT_PALETTE)
    H.append("<div class='card'><h3>Hispanic / Latino (unified)</h3>"
             f"<div class='donut-wrap'>{hisp_donut}"
             f"{legend_html(hisp_pairs, C.CAT_PALETTE, vertical=True)}</div>"
             f"{stacked_table(ctx['hisp_cat'], ctx['sites'])}</div>")
    H.append("</div></section>")

    # ---- lifetime diagnosis status (collapsed) as donuts
    if ctx["lifetime_status"]:
        H.append("<section><h2>Autism diagnosis status (lifetime)</h2>"
                 "<p class='desc'>The lifetime questionnaire's branching tree "
                 "collapsed into one status per reporter: whether the participant "
                 "is formally diagnosed, identifies as autistic without a formal "
                 "diagnosis, does not identify, or is unsure. Age at diagnosis / "
                 "identification is merged into a single field, shown with the "
                 "other continuous variables below.</p>")
        H.append("<div class='grid'>")
        for label, cat in ctx["lifetime_status"]:
            pairs = [(l, cat["overall"][l]) for l in cat["ordered"]
                     if cat["overall"].get(l, 0) > 0]
            donut = donut_svg(pairs, colors=C.CAT_PALETTE)
            H.append(
                f"<div class='card'><h3>{esc(label)}</h3>"
                f"<div class='donut-wrap'>{donut}"
                f"{legend_html(pairs, C.CAT_PALETTE, vertical=True)}</div>"
                f"{stacked_table(cat, ctx['sites'])}</div>"
            )
        H.append("</div></section>")

    # ---- categorical variables (each with a colored stacked bar)
    H.append("<section><h2>Categorical variables by site</h2>"
             "<p class='desc'>Coded fields decoded to labels, counted per site, "
             "with a stacked bar for at-a-glance comparison.</p>")
    H.append("<div class='grid'>")
    for field, cat in ctx["categoricals"]:
        label = C.FIELD_LABELS.get(field, field)
        bar, pal = site_stacked_bar(cat, ctx["sites"])
        pairs = [(l, cat["overall"][l]) for l in cat["ordered"]
                 if cat["overall"].get(l, 0) > 0]
        H.append(f"<div class='card'><h3>{esc(label)}"
                 f"<span class='meta'>{esc(field)}</span></h3>"
                 f"<div class='chartbox'>{bar}</div>"
                 f"{legend_html(pairs, pal)}"
                 f"{stacked_table(cat, ctx['sites'])}</div>")
    H.append("</div></section>")

    # ---- continuous variables
    if ctx["continuous"]:
        H.append("<section><h2>Continuous variables</h2>"
                 "<p class='desc'>Summary statistics by site for numeric fields "
                 "(ages, derived ages). n = non-missing values.</p>")
        H.append("<div class='grid'>")
        for label, source, rows in ctx["continuous"]:
            H.append(f"<div class='card'><h3>{esc(label)}"
                     f"<span class='meta'>{esc(source)}</span></h3>")
            H.append("<table class='cnt'><thead><tr><th></th><th>n</th>"
                     "<th>Mean</th><th>Median</th><th>Min</th><th>Max</th>"
                     "</tr></thead><tbody>")
            site_order = [s for s in ctx["sites"] if s in rows] + ["All sites"]
            for s in site_order:
                st = rows.get(s)
                if not st:
                    continue
                cls = "tot" if s == "All sites" else "rl"
                H.append(
                    f"<tr><th class='{cls}'>{esc(s)}</th>"
                    f"<td>{st['n']}</td><td>{fmt(st['mean'])}</td>"
                    f"<td>{fmt(st['median'])}</td><td>{fmt(st['min'],0)}</td>"
                    f"<td>{fmt(st['max'],0)}</td></tr>"
                )
            H.append("</tbody></table></div>")
        H.append("</div></section>")

    # ---- CATI (valid administrations only)
    # Rendered whenever the instrument is part of this project -- an empty
    # denominator is a finding to report, not a reason to hide the section.
    ct = ctx["cati"]
    if ct["n_eligible"] or ct["n_elig_unknown"] or ct["absent_fields"]:
        H.append("<section><h2>CATI</h2>")
        H.append(
            "<p class='desc'>Subscale and total scores for the Comprehensive "
            "Autistic Trait Inventory. A CATI score is only interpretable when "
            "every item was answered, so <b>only administrations with "
            f"<code>{esc(C.CATI_MISSED_FIELD)} = 0</code> are summarized "
            "here</b>. REDCap still exports a computed score when items are "
            "skipped; those scores are excluded rather than averaged in.</p>"
        )
        if ct["absent_fields"]:
            H.append(
                "<div class='note' style='border-left-color:var(--warn)'>"
                f"<span class='flag'><b>{len(ct['absent_fields'])} CATI field(s) "
                f"are not returned by report {esc(str(C.REPORT_ID))}:</span> "
                + esc(", ".join(ct["absent_fields"])) + ". "
                + ("Without the item-missingness counter no administration can "
                   "be validated, so every score below is suppressed. "
                   if ct["missed_field_absent"] else
                   "Those scales cannot be summarized. ")
                + "Add the field(s) to the report to populate this section."
                + "</div>"
            )
        if not ct["eligibility_filtered"] and ct["rule_missing_fields"]:
            H.append(
                "<div class='note' style='border-left-color:var(--warn)'>"
                "<span class='flag'><b>Eligibility could not be applied.</b></span> "
                "The Survey Queue rule for this instrument depends on "
                + ", ".join(f"<code>{esc(f)}</code>"
                            for f in ct["rule_missing_fields"])
                + f", which report {esc(str(C.REPORT_ID))} does not return. "
                "The denominator below is therefore <b>every record in the "
                f"export ({ct['n_total']})</b>, not just participants actually "
                "assigned the CATI, so <b>Not taken</b> overstates the true "
                "figure. Scores themselves are unaffected. Add the field(s) to "
                "the report to restore the correct denominator.</div>"
            )
        st = ct["states"]
        denom_phrase = (
            f"Of {ct['n_eligible']} participants eligible for the CATI"
            if ct["eligibility_filtered"] else
            f"Of {ct['n_eligible']} records in the export "
            "(eligibility unavailable, see above)"
        )
        H.append(
            f"<div class='note'><b>n = {ct['n_valid']}</b> valid CATI "
            f"administrations. {denom_phrase}: "
            f"<b>{st['valid']}</b> complete and usable, "
            f"<b>{st['incomplete_items']}</b> with one or more missing items "
            f"(scores suppressed), <b>{st['unverifiable']}</b> with scores but "
            f"no <code>{esc(C.CATI_MISSED_FIELD)}</code> value to verify "
            f"against, and <b>{st['no_data']}</b> not yet taken."
            + (f" {ct['n_not_eligible']} participant(s) are not eligible for "
               "the CATI under the Survey Queue rule and are excluded from "
               "this denominator." if ct["n_not_eligible"] else "")
            + "</div>"
        )
        if ct["states"]["unverifiable"]:
            H.append(
                "<div class='note' style='border-left-color:var(--warn)'>"
                f"<span class='flag'><b>{ct['states']['unverifiable']}</b> "
                "record(s) have CATI scores but no item-missingness value.</span> "
                "Validity cannot be established, so they are excluded from the "
                "statistics rather than assumed complete.</div>"
            )
        if ct["over_max"]:
            H.append(
                "<div class='note' style='border-left-color:var(--warn)'>"
                f"<span class='flag'><b>{ct['over_max']}</b> record(s) report "
                f"more than {C.CATI_MISSED_MAX} missed items</span>, which is "
                "outside the valid range for this instrument.</div>"
            )
        if ct["blank_scores"]:
            names = ", ".join(f"{s['label']} ({s['n']})"
                              for s in ct["blank_scores"])
            H.append(
                "<div class='note' style='border-left-color:var(--warn)'>"
                "<span class='flag'>Some scales are blank on otherwise valid "
                f"CATIs</span> — n below {ct['n_valid']} for: {esc(names)}. "
                "A complete item set should yield every subscale.</div>"
            )

        if ct["n_valid"]:
            H.append("<div class='grid'>")
            for sc_ in ct["scores"]:
                is_total = sc_["field"] == C.CATI_TOTAL_FIELD
                H.append(
                    f"<div class='card'><h3>{esc(sc_['label'])}"
                    + (" <span class='meta'>total</span>" if is_total else "")
                    + f"<span class='meta'>{esc(sc_['field'])}</span></h3>"
                )
                H.append("<table class='cnt'><thead><tr><th></th><th>n</th>"
                         "<th>Mean</th><th>Median</th><th>Min</th><th>Max</th>"
                         "</tr></thead><tbody>")
                rows = sc_["rows"]
                site_order = [s for s in ctx["sites"] if s in rows] + ["All sites"]
                for s in site_order:
                    stt = rows.get(s)
                    if not stt:
                        continue
                    cls = "tot" if s == "All sites" else "rl"
                    H.append(
                        f"<tr><th class='{cls}'>{esc(s)}</th>"
                        f"<td>{stt['n']}</td><td>{fmt(stt['mean'])}</td>"
                        f"<td>{fmt(stt['median'])}</td><td>{fmt(stt['min'],0)}</td>"
                        f"<td>{fmt(stt['max'],0)}</td></tr>"
                    )
                H.append("</tbody></table></div>")
            H.append("</div>")
        else:
            H.append("<p class='ok'>No CATI administrations are currently "
                     "valid, so no scores are shown.</p>")

        # Validity by site: a site with many incomplete CATIs is a workflow signal.
        if ct["sites"]:
            H.append("<h3>CATI validity by site</h3>"
                     "<div class='status-table-wrap'>"
                     "<table class='cnt'><thead><tr><th class='rl'>Site</th>"
                     + "".join(f"<th>{esc(ct['state_labels'][k])}</th>"
                               for k in ct["state_order"])
                     + "<th>Eligible</th></tr></thead><tbody>")
            for s in ct["sites"]:
                row = ct["by_site_state"][s]
                tot = sum(row.get(k, 0) for k in ct["state_order"])
                H.append(f"<tr><th class='rl'>{esc(s)}</th>"
                         + "".join(f"<td>{row.get(k, 0)}</td>"
                                   for k in ct["state_order"])
                         + f"<td class='tot'>{tot}</td></tr>")
            H.append("<tr class='trow'><th class='rl'>Total</th>"
                     + "".join(f"<td class='tot'>{st.get(k, 0)}</td>"
                               for k in ct["state_order"])
                     + f"<td class='tot'>{ct['n_eligible']}</td></tr>")
            H.append("</tbody></table></div>")
        H.append("</section>")

    # ---- eligibility screening (per-gate, applicability-aware)
    sc = ctx["screening"]
    H.append("<section><h2>Eligibility screening</h2>")
    H.append(
        "<p class='desc'>Each criterion is evaluated <b>independently</b> "
        "against only the participants it applies to. Most are branched on "
        f"<b>{esc(C.FIELD_LABELS.get(C.SCREENING_GROUP_FIELD, C.SCREENING_GROUP_FIELD))}</b> "
        f"({esc(C.SCREENING_GROUP_FIELD)}), so a criterion that was never "
        "asked of a participant does not count against them. "
        "<b>Not answered</b> is reported separately from <b>Fail</b>: a blank "
        "is a data-entry or workflow gap, not an eligibility decision. "
        "Exclusion criteria pass when answered “No.”</p>"
    )
    H.append(
        f"<div class='note'>Scope: <b>{sc['n_cohort']}</b> "
        f"{esc(C.SCREENING_COHORT_LABEL)} of {sc['n_total']} total records. "
        "Unaffected siblings and non-autistic participants are not included here.</div>"
    )
    if sc["missing_group"]:
        H.append(
            "<div class='note' style='border-left-color:var(--warn)'>"
            f"<span class='flag'><b>{sc['missing_group']}</b> ASD participant(s) "
            f"have no {esc(C.SCREENING_GROUP_FIELD)} recorded.</span> "
            "Applicability cannot be determined for them, so they are counted "
            "only under criteria that apply to everyone.</div>"
        )

    H.append("<div class='status-table-wrap'>"
             "<table class='cnt'><thead><tr>"
             "<th class='rl'>Criterion</th><th class='rl'>Applies to</th>"
             "<th>Applicable</th>"
             "<th>Pass</th><th>Fail</th><th>Not answered</th>"
             "<th>% answered</th><th>% pass</th>"
             "</tr></thead><tbody>")
    for g in sc["gates"]:
        c = g["counts"]
        unans = c["unanswered"]
        warn = " style='color:var(--warn);font-weight:600'" if unans else ""
        H.append(
            f"<tr><th class='rl'>{esc(g['label'])}<br>"
            f"<span class='meta'>({esc(g['field'])})</span></th>"
            f"<th class='rl'><span class='meta'>{esc(g['applies_label'])}</span></th>"
            f"<td>{g['applicable']}</td>"
            f"<td>{c['pass']}</td><td>{c['fail']}</td>"
            f"<td{warn}>{unans}</td>"
            f"<td>{g['answered_pct']:.0f}%</td>"
            f"<td>{g['pass_pct']:.0f}%</td></tr>"
        )
    H.append("</tbody></table></div>")

    # Per-site unanswered matrix: the point of this view is to spot a
    # criterion that one site is systematically leaving blank.
    if any(g["counts"]["unanswered"] for g in sc["gates"]):
        H.append("<h3>Unanswered criteria by site</h3>"
                 "<p class='desc'>Counts of applicable-but-blank responses. "
                 "A column that is consistently high may indicate at a workflow or "
                 "training gap.</p>")
        H.append("<div class='status-table-wrap'>"
                 "<table class='cnt'><thead><tr><th class='rl'>Criterion</th>"
                 + "".join(f"<th>{esc(s)}</th>" for s in sc["sites"])
                 + "<th>TOTAL</th></tr></thead><tbody>")
        for g in sc["gates"]:
            if not g["counts"]["unanswered"]:
                continue
            cells = []
            for s in sc["sites"]:
                n = g["by_site"][s].get("unanswered", 0)
                app = sum(g["by_site"][s].get(k, 0)
                          for k in ("pass", "fail", "unanswered"))
                cells.append(
                    f"<td>{n}<span class='meta'>/{app}</span></td>"
                    if app else "<td><span class='meta'>—</span></td>"
                )
            H.append(f"<tr><th class='rl'>{esc(g['label'])}</th>" + "".join(cells)
                     + f"<td><b>{g['counts']['unanswered']}</b>"
                       f"<span class='meta'>/{g['applicable']}</span></td></tr>")
        H.append("</tbody></table></div>")

    # Roll-up across every criterion that applies to a participant.
    H.append("<h3>Overall screening status</h3>")
    ru = sc["rollup"]
    H.append("<div class='status-table-wrap'>"
             "<table class='cnt'><thead><tr><th class='rl'>Site</th>"
             + "".join(f"<th>{esc(k)}</th>" for k in sc["rollup_order"])
             + "<th>TOTAL</th></tr></thead><tbody>")
    for s in sc["sites"]:
        row = sc["rollup_by_site"][s]
        tot = sum(row.get(k, 0) for k in sc["rollup_order"])
        H.append(f"<tr><th class='rl'>{esc(s)}</th>"
                 + "".join(f"<td>{row.get(k, 0)}</td>" for k in sc["rollup_order"])
                 + f"<td class='tot'>{tot}</td></tr>")
    H.append("<tr class='trow'><th class='rl'>Total</th>"
             + "".join(f"<td class='tot'>{ru.get(k, 0)}</td>"
                       for k in sc["rollup_order"])
             + f"<td class='tot'>{sc['n_cohort']}</td></tr>")
    H.append("</tbody></table></div>")
    H.append(
        "<div class='note'>“Screening incomplete” means nothing has failed but "
        "at least one applicable criterion is still unanswered; these are "
        "pending and not necessarily excluded. Recorded as Include in REDCap: "
        f"<b>{sc['recorded_included']}</b>."
        + (f" <span class='flag'><b>{sc['included_but_not_clear']}</b> "
           "of those do not yet clear every applicable criterion here</span> "
           "(consider reconciling)."
           if sc["included_but_not_clear"] else "")
        + "</div>"
    )
    H.append("</section>")

    # ---- survey completeness (queue + display logic aware)
    if ctx.get("survey"):
        H.append(render_survey_section(ctx))

    # ---- missingness
    H.append("<section><h2>Missingness per variable</h2>"
             "<p class='desc'>“Missing among expected” respects REDCap branching "
             "logic — fields hidden by a participant’s prior answers are not "
             "counted as missing. The "
             "<span class='pill branch'>branching</span> tag marks "
             "conditionally-shown fields. Raw blank % is shown for reference.</p>")
    H.append("<table class='cnt'><thead><tr>"
             "<th class='rl'>Variable</th><th></th>"
             "<th>Expected</th><th>Missing</th><th>Missing % (expected)</th>"
             "<th>Raw blank %</th><th></th></tr></thead><tbody>")
    miss = ctx["missingness"]
    # sort: worst expected-missingness first
    order = sorted(miss.items(), key=lambda kv: -kv[1]["pct_missing_expected"])
    for field, m in order:
        if m["kind"] in ("identifier",) and field in ("record_number", "src_subject_id"):
            # show but these should be ~complete
            pass
        branch = ("<span class='pill branch'>branching</span>"
                  if m["branching"] else "")
        pct = m["pct_missing_expected"]
        bar = (f"<div class='miss-bar'><div class='miss-fill' "
               f"style='width:{min(pct,100):.0f}%'></div></div>")
        # Rows past the threshold are the ones counted in the headline
        # data-quality flag, so mark them here as well.
        flagged = (m["expected"] and pct > C.MISSINGNESS_FLAG_PCT)
        pct_cell = (f"<td class='flag'><b>{pct:.1f}%</b></td>" if flagged
                    else f"<td>{pct:.1f}%</td>")
        H.append(
            f"<tr><td class='rl'>{esc(m['label'])}"
            f"<div class='meta' style='color:var(--muted);font-size:10.5px;"
            f"font-family:IBM Plex Mono,monospace'>{esc(field)}</div></td>"
            f"<td>{branch}</td>"
            f"<td>{m['expected']}</td><td>{m['missing_expected']}</td>"
            f"{pct_cell}<td>{m['pct_raw_blank']:.1f}%</td>"
            f"<td>{bar}</td></tr>"
        )
    H.append("</tbody></table>")
    H.append(
        f"<div class='note'>Variables above "
        f"{fmt(C.MISSINGNESS_FLAG_PCT, 1)}% missing among expected responses "
        f"are highlighted and counted in the <b>Data-quality flags</b> KPI at "
        f"the top of this report — <b>{len(ctx['missingness_flags'])}</b> "
        f"currently. Branched variables are judged only against the records "
        f"that should have answered them.</div>"
    )
    H.append("</section>")

    # ---- data quality
    H.append("<section><h2>Data-quality flags</h2>"
             "<p class='desc'>Issues worth a human’s eyes: variables missing "
             f"more than {fmt(C.MISSINGNESS_FLAG_PCT, 1)}% of their expected "
             "responses, values outside the "
             "dictionary, and cross-source race/ethnicity conflicts (resolved in "
             "favor of self-report, but surfaced here).</p>")
    if n_flags == 0:
        H.append("<p class='ok'>No flags — all variables are within the "
                 f"{fmt(C.MISSINGNESS_FLAG_PCT, 1)}% missingness threshold, all "
                 "coded values are within the dictionary, and no cross-source "
                 "conflicts were detected.</p>")
    else:
        H.append("<div class='twocol'>")
        for mf in miss_flags:
            scope = ("of expected responses" if mf["branching"]
                     else "of all records")
            H.append(
                f"<div class='dq-item flag'>● <b>{esc(mf['label'])}</b> "
                f"({esc(mf['field'])}): {mf['missing']} of {mf['expected']} "
                f"missing — <b>{mf['pct']:.1f}%</b> {scope}.</div>"
            )
        if dq["race_conflicts"]:
            H.append(f"<div class='dq-item flag'>● {len(dq['race_conflicts'])} "
                     f"record(s) with conflicting self vs informant <b>race</b> "
                     f"(used self-report).</div>")
        if dq["hisp_conflicts"]:
            H.append(f"<div class='dq-item flag'>● {len(dq['hisp_conflicts'])} "
                     f"record(s) with conflicting self vs informant "
                     f"<b>Hispanic/Latino</b> (used self-report).</div>")
        # group unexpected codes by field
        byf = Counter(f for _, f, _ in dq["unexpected"])
        for f, n in byf.most_common():
            vals = sorted({raw for _, ff, raw in dq["unexpected"] if ff == f})
            H.append(f"<div class='dq-item flag'>● <b>{esc(C.FIELD_LABELS.get(f,f))}"
                     f"</b> ({esc(f)}): {n} record(s) with out-of-dictionary "
                     f"value(s): {esc(', '.join(vals))}.</div>")
        H.append("</div>")
    H.append("</section>")

    # ---- footer
    H.append(
        f"<footer>Source: REDCap report {esc(C.REPORT_ID)} · "
        f"{esc(ctx['generated'])} · {total} records · {n_sites} sites · "
        f"Aggregate counts only; no PHI. Re-run build_dashboard.py to refresh."
        f"</footer>"
    )
    H.append("</div></body></html>")
    return "".join(H)


# ===========================================================================
# PDF
# ===========================================================================
