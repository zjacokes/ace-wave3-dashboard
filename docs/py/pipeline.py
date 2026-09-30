"""Deterministic in-memory report pipeline. No disk, network, printing or clock reads."""
from __future__ import annotations
from dataclasses import dataclass, field
import datetime as dt
import hashlib
import html
import io
import re
import csv
import pandas as pd
import config as C
import survey_completeness as SC
import table1 as T1
from report_core import *

# Taken from the supplied 2026-09-21 dictionary, restricted to report 16779.
IDENTIFIER_FIELDS = {
    "int_date": "pre-visit dates",
    "ace_demo_13": "race",
    "ace_demo_informant_11": "race",
    "wasi_fs2_comp": "WASI",
    "lifetime_q1_yes_q1": "lifetime diagnosis ages",
    "lifetime_q1_yes_q2": "lifetime diagnosis ages",
    "lifetime_q1_no_yes": "lifetime diagnosis ages",
    "lifetime_q1_unsure_yes": "lifetime diagnosis ages",
    "lifetime_q1_yes_q1_2": "lifetime diagnosis ages",
    "lifetime_q1_unsure_yes_2": "lifetime diagnosis ages",
}

@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    text: str
    fields: tuple = ()

class ExportValidationError(ValueError):
    def __init__(self, findings):
        self.findings = findings
        super().__init__(" ".join(f.text for f in findings if f.level == "error"))

@dataclass
class Report:
    dashboard_html: str
    print_html: str
    table1_html: str
    table1_numeric_csv: str
    table1_audit_json: str
    table1_id_audit_csv: str | None
    cleaned_labeled_csv: str
    messages: list
    summary: dict
    findings: list
    table1_bundle: dict = field(repr=False)


def validate_export(df):
    findings = []
    def add(level, code, text, fields=()):
        findings.append(Finding(level, code, text, tuple(fields)))
    if 'record_number' not in df or not any(str(c).endswith(('_complete', '_iscomplete')) for c in df.columns):
        add('error', 'wrong_report', 'This does not look like report 16779. Export the report itself, not a form or an instrument.')
    if df.empty:
        add('error', 'empty', 'This report has no participant rows. Download a report containing records.')
    if 'record_number' in df:
        ids = df.record_number.fillna('').astype(str).str.strip()
        blanks = int(ids.eq('').sum())
        dup = ids.ne('') & ids.duplicated(keep=False)
        if blanks:
            add('error', 'blank_ids', f'{blanks} rows have a blank record number. Correct the source records and export again.')
        if dup.any():
            add('error', 'duplicate_ids', f'{ids[dup].nunique()} record numbers appear more than once ({int(dup.sum())} rows). Export one row per participant.')
        if ids.str.match(r'^\d+(?:\.\d+)?[eE][+-]?\d+$').any():
            add('error', 'excel_ids', 'Record numbers use scientific notation. This file looks like it was opened and re-saved in Excel. Upload the original download.')
        # Lost leading zeros cannot be recovered or inferred without an ID-width rule.
    labeled = []
    for name, mapping in C.VALUE_MAPS.items():
        if name in df:
            values = df[name].fillna('').astype(str).str.strip()
            labels = {str(v).casefold() for v in mapping.values()} - {str(k).casefold() for k in mapping}
            if values.str.casefold().isin(labels).any():
                labeled.append(name)
    if labeled:
        add('error', 'labeled', 'This export contains labels instead of raw codes. Re-export with Raw data and Raw headers. Affected columns: '+', '.join(labeled)+'.', labeled)
    if 'int_date' in df:
        dates = df.int_date.fillna('').astype(str).str.strip()
        invalid = []
        for value in dates[dates.ne('')]:
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    raise ValueError()
                dt.date.fromisoformat(value)
            except ValueError:
                invalid.append(value)
        if invalid:
            add('error', 'excel_dates', 'Pre-visit dates are not in the original REDCap YYYY-MM-DD format. This file may have been re-saved in Excel. Upload the original download.', ['int_date'])
    demographics_present = any(c in df and df[c].fillna('').astype(str).str.strip().ne('').any() for c in ('int_age', 'sex', 'group', 'site'))
    unavailable = [f for f in IDENTIFIER_FIELDS if f not in df or
                   (demographics_present and df[f].fillna('').astype(str).str.strip().eq('').all())]
    if unavailable:
        sections = list(dict.fromkeys(IDENTIFIER_FIELDS[f] for f in unavailable))
        add('warning', 'deidentified', 'Identifier-tagged fields are absent or blank throughout this export. REDCap may have removed them during de-identification. Affected sections: '+', '.join(sections)+'. These sources are unavailable in this export; missing values do not establish participant nonresponse. For complete sections, ask the study team which export settings to use. Fields: '+', '.join(unavailable)+'.', unavailable)
    missing = [c for c in C.EXPORT_FIELDS if c not in df]
    if missing:
        add('warning', 'stale', 'Expected report columns are missing: '+', '.join(missing)+'. Demographic, status, screening, or score sections using these fields may be unavailable or incomplete. Download the current report 16779 export.', missing)
    return findings


def build_report(csv_text, *, dictionary_text=None, queue_text=None,
                 fdl_text=None, source_name="", source_timestamp=None,
                 built_at=None, status="Draft", export_links=None):
    """Build with explicit time inputs; built_at is required (no implicit clock).

    Text is kept exactly for source hashes, including an optional UTF-8 BOM.
    No browser-only counting or alternative numeric serializers exist.
    """
    if built_at is None:
        raise ValueError('built_at must be supplied by the caller.')
    built_time = dt.datetime.fromisoformat(built_at.replace('Z', '+00:00')) if isinstance(built_at, str) else built_at
    stamp = built_time.strftime('%Y-%m-%d_%H%M')
    snapshot_date = source_timestamp
    if not snapshot_date:
        match = re.search(r'\d{4}-\d{2}-\d{2}', source_name)
        snapshot_date = match.group() if match else built_time.date().isoformat()
    snapshot_date = str(snapshot_date)[:10]
    dt.date.fromisoformat(snapshot_date)
    try:
        header = next(csv.reader(io.StringIO(csv_text.lstrip('\ufeff'))))
        if len(header) != len(set(header)):
            raise ExportValidationError([Finding('error', 'duplicate_columns', 'This CSV contains duplicate column headers. Upload the original raw report export.')])
        df_raw = pd.read_csv(io.StringIO(csv_text.lstrip('\ufeff')), dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, StopIteration, UnicodeError) as error:
        raise ExportValidationError([Finding('error', 'invalid_csv', 'This CSV could not be read. Upload the original UTF-8 CSV downloaded from report 16779.')]) from error
    findings = validate_export(df_raw)
    if any(f.level == 'error' for f in findings):
        raise ExportValidationError(findings)
    messages = [{'level': f.level, 'text': f.text} for f in findings]
    def log(text):
        messages.append({'level': 'warning' if 'WARNING:' in text else 'info', 'text': text.strip()})
    log(f'{len(df_raw)} records, {len(df_raw.columns)} columns')
    log('Decoding values and collapsing race/ethnicity …')
    df_labeled, quality, raw_records = build_labeled_frame(df_raw)
    log('Building manuscript-style Table 1 …')
    table1_bundle = T1.build_bundle_from_frame(
        df_raw, snapshot_date, status=status, dictionary_text=dictionary_text,
        generated_at=built_time.replace(microsecond=0, tzinfo=None).isoformat(),
        source_hash=hashlib.sha256(csv_text.encode('utf-8')).hexdigest(),
        dictionary_hash=hashlib.sha256(dictionary_text.encode('utf-8')).hexdigest() if dictionary_text is not None else None)
    for warning in table1_bundle['metadata']['dictionary_warnings']:
        findings.append(Finding('warning', 'dictionary', warning))
        log('WARNING: '+warning)
    if export_links is None:
        export_links = T1.export_names(stamp)
    # --- analytics
    log("Computing analytics ...")
    site_overview = compute_site_overview(raw_records)
    # Included-only cohort (drops record-id-only / excluded shells)
    included_records = [r for r in raw_records if C.is_included(r)]
    site_overview_incl = compute_site_overview(included_records)
    missingness, sites = compute_missingness(raw_records)
    # Variables missing more than the configured share of their *expected*
    # responses become data-quality flags and feed the headline counter.
    missingness_flags = sorted(
        (
            {
                "field": f,
                "label": m["label"],
                "pct": m["pct_missing_expected"],
                "missing": m["missing_expected"],
                "expected": m["expected"],
                "branching": m["branching"],
            }
            for f, m in missingness.items()
            if m["expected"] and m["pct_missing_expected"] > C.MISSINGNESS_FLAG_PCT
        ),
        key=lambda d: -d["pct"],
    )
    funnel = compute_funnel(raw_records)
    screening = compute_screening(raw_records)

    # REDCap instrument/form completeness. Discover status fields regardless
    # of whether optional Queue/FDL files were supplied. When logic is present,
    # eligibility is resolved before the 0/1/2 completion status is counted.
    survey = None
    columns = list(df_raw.columns)
    excluded_forms = getattr(C, "SURVEY_EXCLUDED_FORMS", set())
    forms = SC.discover_survey_forms(columns, excluded_forms)
    expected_completion = getattr(C, "SURVEY_COMPLETION_FIELDS", [])
    missing_expected = SC.missing_expected_fields(columns, expected_completion)

    # In-person forms are only "expected" once the participant has attended
    # their visit. Gate them on the anchor instrument so pending visits are
    # removed from the denominator instead of counted as incomplete.
    visit_gate = SC.build_visit_gate(
        columns,
        getattr(C, "INPERSON_VISIT_ANCHOR", ""),
        getattr(C, "INPERSON_VISIT_GATED_FORMS", set()),
        getattr(C, "INPERSON_VISIT_COMPLETE_CODES", ("2",)),
    )

    # How many of the enrolled cohort have yet to attend their in-person
    # visit. Uses the same anchor test as the survey-completeness gate, so
    # this figure and the anchor row's eligible count always agree.
    visit_attendance = compute_visit_attendance(
        included_records, raw_records, visit_gate
    )
    if visit_attendance:
        log(f"  {visit_attendance['awaiting']} of "
              f"{visit_attendance['n_cohort']} enrolled participant(s) have "
              f"yet to attend a visit "
              f"({visit_attendance['attended']} attended, "
              f"{visit_attendance['pct_attended']:.0f}%)")

    if missing_expected:
        preview = ", ".join(missing_expected[:8])
        extra = len(missing_expected) - 8
        if extra > 0:
            preview += f", ... (+{extra} more)"
        log(
            f"  WARNING: {len(missing_expected)} configured survey/form status "
            f"field(s) are absent from REDCap report {C.REPORT_ID}: {preview}"
        )

    # Loaded once: the survey section and the CATI validity denominator both
    # need the administration rules.
    queue_logic = SC.load_queue_logic_from_text(queue_text)
    fdl_logic = SC.load_fdl_logic_from_text(fdl_text)

    log("Summarizing CATI scores ...")
    cati = compute_cati(raw_records, columns, queue_logic, fdl_logic)
    if cati["absent_fields"]:
        log(f"  WARNING: {len(cati['absent_fields'])} CATI field(s) absent "
              f"from REDCap report {C.REPORT_ID}: "
              + ", ".join(cati["absent_fields"]))
    if not cati["eligibility_filtered"] and cati["rule_missing_fields"]:
        log("  WARNING: CATI eligibility not applied — the Survey Queue rule "
              "needs field(s) absent from the report: "
              + ", ".join(cati["rule_missing_fields"])
              + f"; denominator falls back to all {cati['n_total']} records")
    log(f"  {cati['n_valid']} valid CATI of {cati['n_eligible']} eligible "
          f"({cati['states']['incomplete_items']} with missing items, "
          f"{cati['states']['unverifiable']} unverifiable)")

    if forms:
        log("Resolving survey/form completeness ...")
        survey_all = SC.compute_survey_completeness(
            raw_records, columns, queue_logic, fdl_logic, site_of,
            visit_gate=visit_gate, excluded_forms=excluded_forms)
        form_names = set(forms)
        unmatched_logic = sorted(
            form for form in ((set(queue_logic) | set(fdl_logic)) - form_names)
            if not SC.form_is_inactive(form, queue_logic, fdl_logic)
        )
        missing_logic_fields = SC.missing_logic_fields(
            columns, queue_logic, fdl_logic
        )
        survey = {
            "all": survey_all,
            "n_forms": len(forms),
            "n_queue": len(queue_logic),
            "n_fdl": len(fdl_logic),
            "logic_available": bool(queue_logic or fdl_logic),
            "missing_expected_fields": missing_expected,
            "missing_logic_fields": missing_logic_fields,
            "unmatched_logic_rules": unmatched_logic,
            "visit_gate": visit_gate,
            "n_visit_gated": len(visit_gate["forms"]) if visit_gate else 0,
            "visit_anchor_name": (
                C.SURVEY_DISPLAY_NAMES.get(
                    visit_gate["anchor_form"],
                    SC.humanize_form(visit_gate["anchor_form"]),
                ) if visit_gate else None
            ),
            "n_visit_attended": (
                sum(
                    1 for r in raw_records
                    if str(r.get(visit_gate["anchor_status_col"], "") or "")
                    .strip() in visit_gate["complete_codes"]
                ) if visit_gate else 0
            ),
        }
        suffixes = ", ".join(SC.COMPLETION_SUFFIXES)
        log(f"  {len(forms)} form-status fields discovered ({suffixes})")
        log(f"  {len(queue_logic)} queue rule(s) and {len(fdl_logic)} "
              "display rule(s) loaded")
        if excluded_forms:
            log(f"  {len(excluded_forms)} retired instrument(s) suppressed "
                  "(no longer collected)")
        if visit_gate:
            log(f"  in-person visit gate active on {len(visit_gate['forms'])}"
                  f" form(s); anchor = {visit_gate['anchor_status_col']}, "
                  f"{survey['n_visit_attended']}/{len(raw_records)} attended")
        elif getattr(C, "INPERSON_VISIT_GATED_FORMS", set()):
            log("  WARNING: in-person visit gate disabled — anchor "
                  f"'{getattr(C, 'INPERSON_VISIT_ANCHOR', '')}' status column "
                  "was not returned by the report. In-person forms will count "
                  "un-visited participants as incomplete.")
        if not (queue_logic or fdl_logic):
            log("  NOTE: no Queue/FDL logic loaded; all returned forms are "
                  "treated as generally applicable.")
        if missing_logic_fields:
            log("  WARNING: administration logic references field(s) absent "
                  "from the report: " + ", ".join(missing_logic_fields))
        if unmatched_logic:
            log(f"  WARNING: {len(unmatched_logic)} active logic rule(s) did "
                  "not match a returned form-status column.")
    else:
        suffixes = " or ".join(f"*{s}" for s in SC.COMPLETION_SUFFIXES)
        log(
            f"  WARNING: no REDCap form-status columns ({suffixes}) were "
            f"returned by report {C.REPORT_ID}; Survey Completeness skipped. "
            "Add the instrument status fields to that REDCap report."
        )

    # Helper: build a categorical summary directly from a labeled column.
    def cat_from_labeled(col, ordered_hint=None):
        by_site = defaultdict(Counter)
        overall = Counter()
        for rrow, lab in zip(raw_records, df_labeled[col]):
            if lab is None or lab == "":
                continue
            by_site[site_of(rrow)][lab] += 1
            overall[lab] += 1
        ordered = list(ordered_hint) if ordered_hint else []
        for lab in overall:
            if lab not in ordered:
                ordered.append(lab)
        return {"ordered": ordered, "by_site": by_site, "overall": overall}

    # Helper: continuous summary from a labeled (numeric-or-blank) column.
    def cont_from_labeled(col):
        by_site = defaultdict(list)
        allvals = []
        for rrow, val in zip(raw_records, df_labeled[col]):
            if val is None or val == "":
                continue
            try:
                num = float(val)
            except (ValueError, TypeError):
                continue
            by_site[site_of(rrow)].append(num)
            allvals.append(num)

        def stats(vals):
            if not vals:
                return {"n": 0, "mean": None, "median": None,
                        "min": None, "max": None}
            s = sorted(vals); n = len(s); mean = sum(s) / n
            median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
            return {"n": n, "mean": mean, "median": median,
                    "min": s[0], "max": s[-1]}
        rows = {site: stats(v) for site, v in by_site.items()}
        rows["All sites"] = stats(allvals)
        return rows

    # Fields that should NOT appear as standalone categorical tables.
    suppress = (C.DROP_FIELDS | C.FUNNEL_ONLY_FIELDS | C.LIFETIME_RAW_FIELDS
                | {C.RACE_SELF, C.RACE_INFORMANT,
                   C.HISPANIC_SELF, C.HISPANIC_INFORMANT}
                | set(C.STATUS_PANEL_FIELDS) | {C.SITE_FIELD}
                | getattr(C, "TABLE1_ONLY_FIELDS", set()))

    # Prominent status panel (inclusion / status / clinician_judgment).
    status_panel = []
    for f in C.STATUS_PANEL_FIELDS:
        cat = compute_categorical(raw_records, f)
        if cat["overall"]:
            status_panel.append((f, cat))

    categoricals = []
    # Each continuous entry is (label, source, rows). Carrying the label and
    # the source field separately keeps derived views working: they have no
    # entry in FIELD_LABELS, and passing their label in as the field name made
    # the card header print it twice.
    continuous = []
    for f in C.EXPORT_FIELDS:
        if f in suppress:
            continue
        kind = C.FIELD_KIND.get(f, "categorical")
        if kind == "categorical":
            cat = compute_categorical(raw_records, f)
            if cat["overall"]:
                categoricals.append((f, cat))
        elif kind == "continuous":
            rows = compute_continuous(raw_records, f)
            if rows.get("All sites", {}).get("n", 0) > 0:
                continuous.append((C.FIELD_LABELS.get(f, f), f, rows))

    # Collapsed lifetime: status (categorical) + the two age views, per side.
    lifetime_status = []
    for side in ("self", "informant"):
        col = C.LIFETIME[side]["status_label"]
        cat = cat_from_labeled(col, ordered_hint=C.LIFETIME_STATUS_ORDER)
        if cat["overall"]:
            lifetime_status.append((C.LIFETIME[side]["status_label"], cat))
        for label_key, fields_key in C.LIFETIME_AGE_VIEWS:
            label = C.LIFETIME[side][label_key]
            rows = cont_from_labeled(label)
            if rows.get("All sites", {}).get("n", 0) > 0:
                source = " + ".join(C.LIFETIME[side][fields_key])
                continuous.append((label, source, rows))

    race_cat = cat_from_labeled("Race (unified)", ordered_hint=list(C.RACE_MAP.values()))
    hisp_cat = cat_from_labeled("Hispanic/Latino (unified)", ordered_hint=["Yes", "No"])

    ctx = {
        "title": "ACE Wave 3 Data Quality Report",
        "generated": built_time.strftime("%B %d, %Y at %H:%M"),
        "total_records": len(raw_records),
        "site_overview": site_overview,
        "site_overview_incl": site_overview_incl,
        "n_included": len(included_records),
        "visit_attendance": visit_attendance,
        "survey": survey,
        "sites": sites,
        "funnel": funnel,
        "screening": screening,
        "missingness": missingness,
        "missingness_flags": missingness_flags,
        "cati": cati,
        "status_panel": status_panel,
        "lifetime_status": lifetime_status,
        "categoricals": categoricals,
        "continuous": continuous,
        "race_cat": race_cat,
        "hisp_cat": hisp_cat,
        "quality": quality,
        "table1": table1_bundle,
        "table1_export_links": export_links,
    }

    summary = {
        'records': len(raw_records), 'columns': len(columns),
        'all_n': table1_bundle['tables']['all_nonwithdrawn__group']['n'],
        'included_n': table1_bundle['tables']['included__group']['n'],
        'included_records': len(included_records),
        'awaiting_visit': visit_attendance['awaiting'] if visit_attendance else None,
        'checks': (len(quality['unexpected']) + len(quality['race_conflicts'])
                   + len(quality['hisp_conflicts']) + len(missingness_flags)),
    }
    log(f"Table 1: All records N = {summary['all_n']} / Included only N = {summary['included_n']}")
    log(f"{summary['checks']} checks to review")
    log('Rendering dashboard …')
    dashboard = render_html(ctx)
    printable = render_html(ctx, print_mode=True)
    standalone = T1._standalone_html(table1_bundle, export_links)
    unavailable_findings = [f for f in findings if f.code == 'deidentified']
    if unavailable_findings:
        # Preserve counts; make unavailable export sources explicit in every HTML and audit.
        note = '<aside role="note" style="padding:16px;background:#fff3cf;color:#493500">'+html.escape(unavailable_findings[0].text)+'</aside>'
        dashboard = dashboard.replace('<body>', '<body>'+note, 1)
        printable = printable.replace('<body>', '<body>'+note, 1)
        standalone = standalone.replace('<body>', '<body>'+note, 1)
        table1_bundle['metadata']['export_availability'] = {'unavailable_source_fields': list(unavailable_findings[0].fields), 'note': unavailable_findings[0].text}
    return Report(dashboard, printable, standalone,
                  T1.numeric_csv_text(table1_bundle), T1.audit_json_text(table1_bundle),
                  None, df_labeled.to_csv(index=False), messages, summary, findings, table1_bundle)
