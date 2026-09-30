"""
config.py
=========
All project-specific knowledge lives here, derived directly from the
PRO-DRS / OM-ACE Wave 3 REDCap data dictionary.

If the REDCap project changes (new coded values, new branching logic, etc.),
this is the ONE file you should need to edit. The rest of the pipeline reads
from these structures and does not hard-code any field names or codes.
"""

import os

# ---------------------------------------------------------------------------
# 1. API / EXPORT SETTINGS
# ---------------------------------------------------------------------------
# The token is intentionally NOT stored here. It is read at runtime from the
# environment variable REDCAP_API_TOKEN (preferred) or passed via --token.
REDCAP_API_URL = "https://redcap.healthsystem.virginia.edu/api/"
REPORT_ID = "16779"

# The exact ordered list of fields we expect from the report. Used to validate
# the export and to drive the dashboard. Order here = order in the data section.
EXPORT_FIELDS = [
    "record_number", "site", "src_subject_id", "sex", "gender_diverse",
    "group", "asd_group", "ados_module", "int_date", "int_age", "longitudinal",
    "longitudinal_2", "parent", "diagnosis_12yo",
    "participant_white", "phenotype", "what_asd_group", "met_dx_inclusion",
    "met_verb_cutoff", "met_per_cutoff", "met_age", "met_cogability",
    "met_motorskills", "met_english", "met_diagnosis", "illness_complaint",
    "ward_state", "inclusion", "status", "clinician_judgment",
    "lifetime_q1", "lifetime_q1_yes_q1", "lifetime_q1_no", "lifetime_q1_yes_q2",
    "lifetime_q1_no_yes", "lifetime_q1_unsure", "lifetime_q1_unsure_yes",
    "lifetime_q1_2", "lifetime_q1_yes_q1_2", "lifetime_q1_no_2",
    "lifetime_q1_no_yes_2", "lifetime_q1_unsure_2", "lifetime_q1_unsure_yes_2",
    "age_at_dx", "ace_demo_12", "ace_demo_13", "ace_demo_informant_10",
    "ace_demo_informant_11",
    # Table 1 additions.  These are separate constructs: adult self-report
    # education is not combined with informant-reported current grade, and
    # personal earnings are not combined with household income.
    "ace_demo_17", "ace_demo_informant_13a", "ace_demo_26a",
    "ace_demo_informant_15", "wasi_fs2_comp",
    # CATI: subscale + total scores, and the item-level missingness counter
    # that determines whether those scores are usable at all.
    "cati_missed", "soc_total", "com_total", "cam_total", "rig_total",
    "rep_total", "sen_total", "cati_total",
]

# ---------------------------------------------------------------------------
# 2. HUMAN-READABLE LABELS FOR EACH FIELD
# ---------------------------------------------------------------------------
FIELD_LABELS = {
    "record_number": "REDCap Subject ID",
    "site": "Site",
    "src_subject_id": "Subject ID",
    "sex": "Sex (at birth)",
    "gender_diverse": "Gender diverse",
    "group": "Phenotype group",
    "asd_group": "ASD sample source",
    "ados_module": "ADOS/BOSA module assignment",
    "int_date": "Date pre-visit forms sent",
    "int_age": "Age when pre-visit forms sent (months)",
    "longitudinal": "Part of Wave 1",
    "longitudinal_2": "Part of Wave 2",
    "parent": "Parent/informant participating",
    "diagnosis_12yo": "Diagnosed under/over age 12",
    "participant_white": "White or not",
    "phenotype": "Phenotype (calc)",
    "what_asd_group": "ASD group (calc)",
    "met_dx_inclusion": "Met screening dx inclusion",
    "met_verb_cutoff": "Met verbal cutoff",
    "met_per_cutoff": "Met performance cutoff",
    "met_age": "Met age criterion (16-39y)",
    "met_cogability": "Met cognitive ability",
    "met_motorskills": "Met motor skills",
    "met_english": "Met English language",
    "met_diagnosis": "Met diagnosis criterion",
    "illness_complaint": "Active uncontrolled illness (exclusion)",
    "ward_state": "Ward of the state (exclusion)",
    "inclusion": "Include / Exclude",
    "status": "Participant status",
    "clinician_judgment": "Clinician-confirmed autism dx",
    "lifetime_q1": "Self-report: ever dx'd with autism",
    "lifetime_q1_yes_q1": "Self-report: age at dx (yes)",
    "lifetime_q1_no": "Self-report: identifies autistic (no)",
    "lifetime_q1_yes_q2": "Self-report: age first told (yes)",
    "lifetime_q1_no_yes": "Self-report: age first identified (no->yes)",
    "lifetime_q1_unsure": "Self-report: identifies autistic (unsure)",
    "lifetime_q1_unsure_yes": "Self-report: age first identified (unsure->yes)",
    "lifetime_q1_2": "Informant: ever dx'd with autism",
    "lifetime_q1_yes_q1_2": "Informant: age at dx (yes)",
    "lifetime_q1_no_2": "Informant: identifies autistic (no)",
    "lifetime_q1_no_yes_2": "Informant: age first identified (no->yes)",
    "lifetime_q1_unsure_2": "Informant: identifies autistic (unsure)",
    "lifetime_q1_unsure_yes_2": "Informant: age first identified (unsure->yes)",
    "age_at_dx": "Age at diagnosis (derived)",
    "cati_missed": "CATI items missed",
    "soc_total": "CATI: Social",
    "com_total": "CATI: Communication",
    "cam_total": "CATI: Social camouflage",
    "rig_total": "CATI: Cognitive rigidity",
    "rep_total": "CATI: Repetitive behaviours",
    "sen_total": "CATI: Sensory sensitivity",
    "cati_total": "CATI: Total score",
    "ace_demo_12": "Self-report: Hispanic/Latino",
    "ace_demo_13": "Self-report: race",
    "ace_demo_informant_10": "Informant: Hispanic/Latino",
    "ace_demo_informant_11": "Informant: race",
    "ace_demo_17": "Highest education attained (self-report)",
    "ace_demo_informant_13a": "Current grade in school (informant-report)",
    "ace_demo_26a": "Personal income from work (self-report)",
    "ace_demo_informant_15": "Household income (informant-report)",
    "wasi_fs2_comp": "WASI FSIQ-2 Composite Score",
}

# ---------------------------------------------------------------------------
# 3. CODED VALUE MAPS  (raw code -> human label)
# ---------------------------------------------------------------------------
# Standard REDCap yes/no fields all share this map.
YESNO = {"1": "Yes", "0": "No"}

# Race map is shared by self-report and informant-report.
RACE_MAP = {
    "1": "American Indian / Alaska Native",
    "2": "Asian",
    "3": "Native Hawaiian / Pacific Islander",
    "4": "Black / African American",
    "5": "White / Caucasian",
    "6": "More than one race",
}

EDUCATION_MAP = {
    "1": "Did not attend high school",
    "2": "Some high school; no diploma",
    "3": "High school degree or GED",
    "4": "Vocational/technical school",
    "8": "Some college; no degree",
    "9": "Associate's degree",
    "10": "Bachelor's degree",
    "11": "Advanced degree",
    "13": "Don't know",
}

GRADE_MAP = {
    "1": "5th grade", "2": "6th grade", "3": "7th grade",
    "4": "8th grade", "5": "9th grade", "6": "10th grade",
    "7": "11th grade", "8": "12th grade", "9": "College",
    "10": "Vocational/technical school",
}

INCOME_MAP = {
    "1": "Under $1,000", "2": "$1,000 to $2,999",
    "3": "$3,000 to $3,999", "4": "$4,000 to $4,999",
    "5": "$5,000 to $5,999", "6": "$6,000 to $6,999",
    "7": "$7,000 to $7,999", "8": "$8,000 to $8,999",
    "9": "$9,000 to $9,999", "10": "$10,000 to $12,499",
    "11": "$12,500 to $14,999", "12": "$15,000 to $17,499",
    "13": "$17,500 to $19,999", "14": "$20,000 to $24,999",
    "15": "$25,000 to $49,999", "16": "$50,000 to $74,999",
    "17": "$74,999 to $99,999", "18": "$100,000 to $149,999",
    "19": "$150,000 to $249,999", "20": "$250,000 to $499,999",
    "21": "$500,000 to $999,999", "22": "$1,000,000 or more",
}
PERSONAL_INCOME_MAP = {**INCOME_MAP, "23": "Don't know"}

VALUE_MAPS = {
    "site": {"1": "GMU", "2": "Children's National", "3": "UCLA",
             "4": "Yale", "5": "UVA"},
    "sex": {"2": "Female", "1": "Male", "3": "Another sex"},
    "gender_diverse": YESNO,
    "group": {"1": "ASD group", "2": "Unaffected sibling", "3": "Control"},
    "asd_group": {"1": "ACE Clinic", "2": "Community Dx",
                  "3": "New Diagnostic", "4": "Returning"},
    "longitudinal": YESNO,
    "longitudinal_2": YESNO,
    "parent": YESNO,
    "diagnosis_12yo": {"1": "Under age 12", "2": "12 or older", "3": "N/A"},
    "participant_white": {"1": "White/Caucasian", "2": "Not White/Caucasian"},
    "phenotype": {"1": "ASD group", "2": "Unaffected sibling", "3": "Control"},
    "what_asd_group": {"1": "ACE Clinic", "2": "Community Dx",
                       "3": "New Diagnostic", "4": "Returning"},
    "met_dx_inclusion": YESNO, "met_verb_cutoff": YESNO,
    "met_per_cutoff": YESNO, "met_age": YESNO, "met_cogability": YESNO,
    "met_motorskills": YESNO, "met_english": YESNO, "met_diagnosis": YESNO,
    "illness_complaint": YESNO, "ward_state": YESNO,
    "inclusion": {"1": "Include", "2": "Exclude"},
    "status": {"1": "Withdrawn", "2": "Lost to follow-up"},
    "clinician_judgment": YESNO,
    "lifetime_q1": {"1": "Yes", "0": "No", "2": "Unsure"},
    "lifetime_q1_no": {"1": "Yes", "0": "No", "2": "Unsure"},
    "lifetime_q1_unsure": {"1": "Yes", "0": "No", "2": "Unsure"},
    "lifetime_q1_2": {"1": "Yes", "0": "No", "2": "Unsure"},
    "lifetime_q1_no_2": {"1": "Yes", "0": "No", "2": "Unsure"},
    "lifetime_q1_unsure_2": {"1": "Yes", "0": "No", "2": "Unsure"},
    "ace_demo_12": YESNO,
    "ace_demo_13": RACE_MAP,
    "ace_demo_informant_10": YESNO,
    "ace_demo_informant_11": RACE_MAP,
    "ace_demo_17": EDUCATION_MAP,
    "ace_demo_informant_13a": GRADE_MAP,
    "ace_demo_26a": PERSONAL_INCOME_MAP,
    "ace_demo_informant_15": INCOME_MAP,
}

# ---------------------------------------------------------------------------
# 4. FIELD CATEGORIZATION  -> drives how each variable is summarized
# ---------------------------------------------------------------------------
# categorical -> count table + bar chart by site
# continuous  -> summary stats (n, mean, median, min, max) by site
# identifier  -> completeness only (no value breakdown; may contain PHI)
# date        -> completeness only
FIELD_KIND = {
    # identifiers / PHI -- completeness only, never value-broken-out
    "record_number": "identifier",
    "src_subject_id": "identifier",
    "int_date": "date",
    # continuous
    "int_age": "continuous",
    "age_at_dx": "continuous",
    "wasi_fs2_comp": "continuous",
    "lifetime_q1_yes_q1": "continuous",
    "lifetime_q1_yes_q2": "continuous",
    "lifetime_q1_no_yes": "continuous",
    "lifetime_q1_unsure_yes": "continuous",
    "lifetime_q1_yes_q1_2": "continuous",
    "lifetime_q1_no_yes_2": "continuous",
    "lifetime_q1_unsure_yes_2": "continuous",
}
# Everything with a VALUE_MAP entry not already listed is categorical.
for _f in EXPORT_FIELDS:
    if _f not in FIELD_KIND:
        FIELD_KIND[_f] = "categorical" if _f in VALUE_MAPS else "identifier"

# The 'site' field itself is the grouping key; treat specially in the UI.
SITE_FIELD = "site"

# ---------------------------------------------------------------------------
# 5. BRANCHING LOGIC  -> drives "expected missingness"
# ---------------------------------------------------------------------------
# Each entry: field -> predicate(row_raw) returning True if the field was
# *supposed* to be answered for this record (i.e. its branch was shown).
# Fields not listed are considered always-expected.
#
# row_raw maps field -> raw string code (already stripped). Helper below
# makes the predicates readable.
def _eq(field, *codes):
    codes = set(str(c) for c in codes)
    return lambda r: r.get(field, "") in codes

BRANCHING = {
    # asd_group only shown when group == ASD (1)
    "asd_group": _eq("group", "1"),
    "what_asd_group": _eq("group", "1"),

    # ---- Self-report lifetime branch tree (driven by lifetime_q1) ----
    # Asked age-at-dx only if answered "Yes"
    "lifetime_q1_yes_q1": _eq("lifetime_q1", "1"),
    "lifetime_q1_yes_q2": _eq("lifetime_q1", "1"),
    # "Do you identify as autistic?" follow-up if answered "No"
    "lifetime_q1_no": _eq("lifetime_q1", "0"),
    # age first identified, only if No -> then Yes
    "lifetime_q1_no_yes": _eq("lifetime_q1_no", "1"),
    # "Do you identify?" follow-up if answered "Unsure"
    "lifetime_q1_unsure": _eq("lifetime_q1", "2"),
    "lifetime_q1_unsure_yes": _eq("lifetime_q1_unsure", "1"),

    # ---- Informant-report lifetime branch tree (driven by lifetime_q1_2) ----
    "lifetime_q1_yes_q1_2": _eq("lifetime_q1_2", "1"),
    "lifetime_q1_no_2": _eq("lifetime_q1_2", "0"),
    "lifetime_q1_no_yes_2": _eq("lifetime_q1_no_2", "1"),
    "lifetime_q1_unsure_2": _eq("lifetime_q1_2", "2"),
    "lifetime_q1_unsure_yes_2": _eq("lifetime_q1_unsure_2", "1"),

    # Informant-report demographics only expected if a parent/informant exists
    "ace_demo_informant_10": _eq("parent", "1"),
    "ace_demo_informant_11": _eq("parent", "1"),

    # status (withdrawn / lost-to-follow-up) only meaningful when excluded or
    # otherwise off the main path -- but it can be blank legitimately for
    # active participants, so we treat it as conditionally-expected: only
    # count as "missing" when inclusion == Exclude.
    "status": _eq("inclusion", "2"),
}

# ---------------------------------------------------------------------------
# 6. ENROLLMENT FUNNEL  -> ordered eligibility gates for the funnel panel
# ---------------------------------------------------------------------------
# Each gate: (field, label, pass_predicate). A record "passes" the gate when
# the predicate is True. Inclusion/exclusion exclusion-criteria fields invert
# (a "No" is a pass).
FUNNEL_GATES = [
    ("met_dx_inclusion", "Met screening dx inclusion", _eq("met_dx_inclusion", "1")),
    ("met_age", "Met age (16-39y)", _eq("met_age", "1")),
    ("met_verb_cutoff", "Met verbal cutoff", _eq("met_verb_cutoff", "1")),
    ("met_per_cutoff", "Met performance cutoff", _eq("met_per_cutoff", "1")),
    ("met_cogability", "Met cognitive ability", _eq("met_cogability", "1")),
    ("met_motorskills", "Met motor skills", _eq("met_motorskills", "1")),
    ("met_english", "Met English language", _eq("met_english", "1")),
    ("met_diagnosis", "Met diagnosis criterion", _eq("met_diagnosis", "1")),
    # exclusion criteria: a "No" (0) is the pass
    ("illness_complaint", "No active uncontrolled illness", _eq("illness_complaint", "0")),
    ("ward_state", "Not a ward of the state", _eq("ward_state", "0")),
    ("inclusion", "Final: Included", _eq("inclusion", "1")),
]

# ---------------------------------------------------------------------------
# 6b. ELIGIBILITY SCREENING  -> per-gate, applicability-aware
# ---------------------------------------------------------------------------
# Replaces the old cumulative funnel. Two things were wrong with a cascade:
#
#   1. The gates do not all apply to the same people. Most are branched on
#      asd_group, so a Returning participant was never asked about motor
#      skills. Under the cascade their blank answer read as a failure and
#      dropped them from every later gate too.
#   2. A blank is not a failure. It usually means the item has not been
#      reached or filled in yet -- the WASI cutoffs, for example, are decided
#      at the in-person visit, so they stay blank until the participant comes
#      in. Counting those as failures made screening look far lossier than it
#      is.
#
# Each participant is therefore resolved against each gate into exactly one of
# four states: not applicable, pass, fail, or not answered. "Not answered" is
# reported as a first-class number rather than folded into failures, because
# a gate that is systematically blank at one site is a coordinator workflow
# signal, not an eligibility result.
#
# Only the ASD arm is screened this way. Unaffected siblings and controls have
# a different eligibility path and are excluded from the section entirely --
# which also matches the data, since asd_group is only collected when
# group == 1 and would otherwise be blank for every one of them.
SCREENING_COHORT_FIELD = "group"
SCREENING_COHORT_VALUES = {"1"}          # ASD group only
SCREENING_COHORT_LABEL = "ASD participants"

# asd_group: 1 = ACE Clinic, 2 = Community Dx, 3 = New Diagnostic, 4 = Returning
SCREENING_APPLICABILITY = {
    "all": (None, "All ASD participants"),
    "lt4": ({"1", "2", "3"}, "ACE Clinic, Community, New"),
    "new_comm": ({"2", "3"}, "Community, New"),
}
SCREENING_GROUP_FIELD = "asd_group"

# (field, label, applicability key, pass codes, fail codes)
# Exclusion criteria invert: "No" (0) is the pass.
SCREENING_GATES = [
    ("met_dx_inclusion", "Met screening dx inclusion", "all", {"1"}, {"0"}),
    ("met_verb_cutoff", "Met verbal cutoff", "all", {"1"}, {"0"}),
    ("met_per_cutoff", "Met performance cutoff", "all", {"1"}, {"0"}),
    ("met_age", "Met age (16-39y)", "lt4", {"1"}, {"0"}),
    ("met_cogability", "Met cognitive ability", "lt4", {"1"}, {"0"}),
    ("met_motorskills", "Met motor skills", "new_comm", {"1"}, {"0"}),
    ("met_english", "Met English language", "new_comm", {"1"}, {"0"}),
    ("met_diagnosis", "Met diagnosis criterion", "new_comm", {"1"}, {"0"}),
    ("illness_complaint", "No active uncontrolled illness", "new_comm",
     {"0"}, {"1"}),
    ("ward_state", "Not a ward of the state", "new_comm", {"0"}, {"1"}),
]

# The recorded Include/Exclude decision. Compared against the computed
# roll-up rather than treated as a gate, so disagreements surface.
SCREENING_OUTCOME_FIELD = "inclusion"
SCREENING_OUTCOME_INCLUDE = {"1"}

# ---------------------------------------------------------------------------
# 7. RACE COLLAPSE  -> unify self + informant into one field
# ---------------------------------------------------------------------------
# Priority is self-report; informant fills gaps. Conflicts are logged.
RACE_SELF = "ace_demo_13"
RACE_INFORMANT = "ace_demo_informant_11"
HISPANIC_SELF = "ace_demo_12"
HISPANIC_INFORMANT = "ace_demo_informant_10"

# ---------------------------------------------------------------------------
# 8. SITE COLORS  -> one stable, coherent color per site everywhere
# ---------------------------------------------------------------------------
# Keyed by the decoded site label. Used for every by-site chart so a site
# reads as the same color across the whole dashboard.
SITE_COLORS = {
    "GMU": "#4cc4b0",                 # teal
    "Children's National": "#5b8def", # blue
    "UCLA": "#e9a23b",                # amber
    "Yale": "#9b6cf0",                # violet
    "UVA": "#e0603e",                 # coral
    "Unknown site": "#8aa0ab",        # muted gray
}
# Categorical answer palette (for pie/stacked charts of a single variable).
CAT_PALETTE = ["#4cc4b0", "#5b8def", "#e9a23b", "#9b6cf0", "#e0603e",
               "#46c0d8", "#d65a9a", "#8aa0ab"]

# ---------------------------------------------------------------------------
# 9. FIELDS TO DROP  -> erroneously included / redundant with the funnel
# ---------------------------------------------------------------------------
# Calc duplicates of group / asd_group.
DROP_FIELDS = {"phenotype", "what_asd_group"}
# The met_* and exclusion-criteria fields: kept ONLY in the funnel, not as
# standalone count tables.
FUNNEL_ONLY_FIELDS = {
    "met_dx_inclusion", "met_verb_cutoff", "met_per_cutoff", "met_age",
    "met_cogability", "met_motorskills", "met_english", "met_diagnosis",
    "illness_complaint", "ward_state",
}

# ---------------------------------------------------------------------------
# 10. STATUS PANEL  -> promoted, prominent fields right under "records by site"
# ---------------------------------------------------------------------------
STATUS_PANEL_FIELDS = ["inclusion", "status", "clinician_judgment"]

# ---------------------------------------------------------------------------
# 11. LIFETIME COLLAPSE  -> unify the branch trees into clean derived fields
# ---------------------------------------------------------------------------
# Self-report and informant each collapse to:
#   (a) a single "autism diagnosis status" category, and
#   (b) TWO continuous age fields, kept separate on purpose:
#         age at diagnosis     -- from the "formally diagnosed" branch
#         age first identified -- from the "identifies, not formally dx'd"
#                                 branches (the no->yes and unsure->yes paths)
#       These were previously merged into one "age at dx / identification"
#       field. They measure different things and differ by roughly six years
#       in the self-report data, so the merged mean described neither group
#       and drifted with the mix of the two.
#
# Status logic (self-report), framed around 'Formally diagnosed' as headline:
#   lifetime_q1 == Yes (1)                         -> "Formally diagnosed"
#   lifetime_q1 == No (0):
#       lifetime_q1_no == Yes (1)                  -> "Identifies, not formally dx'd"
#       lifetime_q1_no == No (0)                   -> "Does not identify"
#       lifetime_q1_no == Unsure (2) or blank      -> "Unsure / unknown"
#   lifetime_q1 == Unsure (2):
#       lifetime_q1_unsure == Yes (1)              -> "Identifies, not formally dx'd"
#       lifetime_q1_unsure == No (0)               -> "Does not identify"
#       else                                       -> "Unsure / unknown"
#   blank                                          -> "" (true missing)
LIFETIME_STATUS_ORDER = [
    "Formally diagnosed",
    "Identifies, not formally dx'd",
    "Does not identify",
    "Unsure / unknown",
]
LIFETIME = {
    "self": {
        "q1": "lifetime_q1",
        "no": "lifetime_q1_no",
        "unsure": "lifetime_q1_unsure",
        # Every raw branch age field, listed so none of them get a standalone
        # table. This is the suppression list, not the derivation.
        "age_fields": ["lifetime_q1_yes_q1", "lifetime_q1_yes_q2",
                       "lifetime_q1_no_yes", "lifetime_q1_unsure_yes"],
        "status_label": "Self-report: autism diagnosis status",
        # The two derived ages are kept apart on purpose: they answer
        # different questions and their distributions differ materially, so
        # averaging them together describes neither group.
        "dx_age_label": "Self-report: age at diagnosis",
        "dx_age_fields": ["lifetime_q1_yes_q1"],
        "ident_age_label": "Self-report: age first identified",
        "ident_age_fields": ["lifetime_q1_no_yes", "lifetime_q1_unsure_yes"],
    },
    "informant": {
        "q1": "lifetime_q1_2",
        "no": "lifetime_q1_no_2",
        "unsure": "lifetime_q1_unsure_2",
        "age_fields": ["lifetime_q1_yes_q1_2", "lifetime_q1_no_yes_2",
                       "lifetime_q1_unsure_yes_2"],
        "status_label": "Informant: autism diagnosis status",
        "dx_age_label": "Informant: age at diagnosis",
        "dx_age_fields": ["lifetime_q1_yes_q1_2"],
        "ident_age_label": "Informant: age first identified",
        "ident_age_fields": ["lifetime_q1_no_yes_2", "lifetime_q1_unsure_yes_2"],
    },
}

# The derived age views, in display order. Each entry names the config keys
# that carry its label and its source branch fields.
LIFETIME_AGE_VIEWS = [
    ("dx_age_label", "dx_age_fields"),
    ("ident_age_label", "ident_age_fields"),
]
# All the raw lifetime branch fields that should no longer get their own
# standalone tables (they're represented by the collapsed views).
LIFETIME_RAW_FIELDS = set()
for _side in LIFETIME.values():
    LIFETIME_RAW_FIELDS.update([_side["q1"], _side["no"], _side["unsure"]])
    LIFETIME_RAW_FIELDS.update(_side["age_fields"])

# ---------------------------------------------------------------------------
# 12. SURVEY COMPLETENESS  -> queue + display logic files
# ---------------------------------------------------------------------------
# This package bundles the current Survey Queue and Form Display Logic exports.
# Resolve both relative to config.py so they load regardless of the shell's
# working directory. Either path can still be overridden with the CLI flags.
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_BUNDLED_QUEUE = os.path.join(_PROJECT_DIR, "survey_queue_logic.csv")
_BUNDLED_FDL = os.path.join(_PROJECT_DIR, "form_display_logic.csv")
SURVEY_QUEUE_FILE = _BUNDLED_QUEUE if os.path.isfile(_BUNDLED_QUEUE) else None
SURVEY_FDL_FILE = _BUNDLED_FDL if os.path.isfile(_BUNDLED_FDL) else None

# Canonical REDCap instrument-status fields expected in report 16779.  These
# are used for diagnostics only; discovery remains automatic, so newly added
# ``*_complete`` fields will still appear without editing this list.
# Instruments that are no longer collected for Wave 3. They have been pulled
# from REDCap report 16779, so normally they simply will not appear. This set
# is belt-and-braces: it also suppresses them when the pipeline is re-run
# against an older saved export that still carries the columns, so historical
# runs stay comparable to current ones.
SURVEY_EXCLUDED_FORMS = {
    "staff_adir",                    # ADI-R
    "diagnostic_funneling_form",     # funneling form
    "staff_medical_history",         # medical history
    "abas3_parent_informantreport",
    "abas3_adult_informantreport",
    "srs2_child_informantreport",
    "srs2_adult_informantreport",
}

SURVEY_COMPLETION_FIELDS = [
    "start_page_complete",
    "participant_status_form_complete",
    "ace_wave_3_demographics_selfreport_19_complete",
    "ace_wave_3_demographics_self_report_1218_yo_complete",
    "lifetime_count_of_psychiatric_diagnoses_selfreport_complete",
    "the_gender_selfreport_complete",
    "pds_selfreport_male_version_2023_complete",
    "pds_selfreport_female_version_2023_complete",
    "combined_pds_another_assigned_sex_complete",
    "selfassessment_of_autistic_traits_complete",
    "cati_complete",
    "raads14_screen_complete",
    "friendship_questionnaire_complete",
    "promis_general_life_satisfaction_short_form_5a_complete",
    "promis_meaning_and_purpose_short_form_4a_complete",
    "promis_pediatric_life_satisfaction_short_form_4a_complete",
    "promis_pediatric_meaning_and_purpose_short_form_4a_complete",
    "asqol_1618_complete",
    "asqol_19_complete",
    "whoqolbref_physical_domain_complete",
    "isq8_complete",
    "ace_wave_3_demographics_informantreport_complete",
    "lifetime_count_of_psychiatric_diagnoses_informantr_complete",
    "scq_lifetime_informantreport_complete",
    "inperson_ef_compensation_complete",
    "inperson_wasiii_complete",
    "inperson_dkefs_verbal_fluency_task_complete",
    "inperson_stop_and_go_switch_test_game_complete",
    "inperson_cantab_complete",
    "inperson_behavioral_assessment_interruptions_complete",
    "inperson_beck_depression_inventory_complete",
    "inperson_ascasd_complete",
    "inperson_asaa_complete",
    "inperson_dsm5_child_informantreport_complete",
    "inperson_dsm5_child_selfreport_complete",
    "inperson_dsm5_adult_selfreport_complete",
    "inperson_ptsd_checklist_for_dsm5_complete",
    "inperson_cbcl_complete",
    "inperson_abcl_complete",
    "inperson_ados_module_3_complete",
    "inperson_ados_module_4_complete",
    "inperson_ados_participant_feedback_questionnaire_complete",
    "inperson_bosa_participant_feedback_questionnaire_complete",
    "after_visit_ados_participant_followup_complete",
    "after_visit_glasgow_sensory_questionnaire_complete",
    "after_visit_tas8_complete",
    "informant_interview_complete",
    "participant_interview_complete",
    "dsm5_checklist_complete",
    "abas3_upload_complete",
    "staff_brief2_parent_form_shiny_app_upload_complete",
    "staff_briefa_informant_report_shiny_app_upload_complete",
    "srs2_complete",
    "staff_srs2_adult_informant_report_shiny_app_upload_complete",
    "staff_wave_3_neuroimaging_session_notes_d7c4_complete",
]

# Order used in the Survey Completeness table.
# Instrument names must omit the trailing "_complete".
SURVEY_DISPLAY_ORDER = [
    "start_page",
    "participant_status_form",
    "ace_wave_3_demographics_selfreport_19",
    "ace_wave_3_demographics_self_report_1218_yo",
    "ace_wave_3_demographics_informantreport",
    "lifetime_count_of_psychiatric_diagnoses_selfreport",
    "lifetime_count_of_psychiatric_diagnoses_informantr",
    "pds_selfreport_male_version_2023",
    "pds_selfreport_female_version_2023",
    "combined_pds_another_assigned_sex",
    "selfassessment_of_autistic_traits",
    "cati",
    "raads14_screen",
    "friendship_questionnaire",
    "promis_general_life_satisfaction_short_form_5a",
    "promis_meaning_and_purpose_short_form_4a",
    "promis_pediatric_life_satisfaction_short_form_4a",
    "promis_pediatric_meaning_and_purpose_short_form_4a",
    "asqol_1618",
    "asqol_19",
    "whoqolbref_physical_domain",
    "isq8",
    "scq_lifetime_informantreport",
    "inperson_ef_compensation",
    "inperson_wasiii",
    "inperson_dkefs_verbal_fluency_task",
    "inperson_stop_and_go_switch_test_game",
    "inperson_cantab",
    "inperson_beck_depression_inventory",
    "inperson_ascasd",
    "inperson_asaa",
    "inperson_dsm5_child_informantreport",
    "inperson_dsm5_child_selfreport",
    "inperson_dsm5_adult_selfreport",
    "inperson_ptsd_checklist_for_dsm5",
    "inperson_cbcl",
    "inperson_abcl",
    "inperson_ados_module_3",
    "inperson_ados_module_4",
    "inperson_ados_participant_feedback_questionnaire",
    "inperson_bosa_participant_feedback_questionnaire",
    "after_visit_ados_participant_followup",
    "after_visit_glasgow_sensory_questionnaire",
    "after_visit_tas8",
    "informant_interview",
    "participant_interview",
    "dsm5_checklist",
    "staff_brief2_parent_form_shiny_app_upload",
    "staff_briefa_informant_report_shiny_app_upload",
    "srs2",
    "staff_srs2_adult_informant_report_shiny_app_upload",
    "abas3_upload",
    "staff_wave_3_neuroimaging_session_notes_d7c4",
    "inperson_behavioral_assessment_interruptions",
    "the_gender_selfreport"
]


# ---------------------------------------------------------------------------
# 12b. IN-PERSON VISIT GATE
# ---------------------------------------------------------------------------
# Surveys administered during (and immediately after) the in-person visit
# cannot meaningfully be called "incomplete" for a participant who simply has
# not come in yet. Without this gate the completeness table drops off a cliff
# at the first in-person measure, which reads to a clinician as a data-quality
# problem rather than as normal enrollment pacing.
#
# The BDI is the anchor. Every participant starts their in-person visit with
# it, so a complete BDI is proof that the visit happened and that the whole
# in-person battery is therefore *expected*. Participants without a complete
# BDI are removed from the denominator of every gated form -- they are not
# counted as incomplete, and they are not counted as eligible.
#
# The anchor gates itself as well. That is intentional, and it means the BDI's
# own completion percentage is 100% by construction: the only participants in
# its denominator are the ones whose BDI is complete. The number that carries
# real information for that row is the *Eligible* count, which equals the
# number of participants who have attended a visit. The section header states
# that count explicitly so the attendance signal stays visible.
INPERSON_VISIT_ANCHOR = "inperson_beck_depression_inventory"

# The gated block is the contiguous run of SURVEY_DISPLAY_ORDER from
# INPERSON_VISIT_FIRST through INPERSON_VISIT_LAST, so re-ordering that list
# re-derives the block automatically. The block starts at the first in-person
# measure, not at the anchor: the cognitive battery administered before the
# BDI is part of the same visit and must be gated too.
INPERSON_VISIT_FIRST = "inperson_ef_compensation"
INPERSON_VISIT_LAST = "after_visit_tas8"

# In-person instruments that sit outside that contiguous run in the display
# order. Listed explicitly rather than by moving them in SURVEY_DISPLAY_ORDER,
# so that gating and table position stay independent decisions.
INPERSON_VISIT_EXTRA_FORMS = {
    "inperson_behavioral_assessment_interruptions",
}

# REDCap status codes on the anchor that count as "the visit happened".
# 2 = Complete. Add "1" here to also accept Unconfirmed.
INPERSON_VISIT_COMPLETE_CODES = {"2"}


def _derive_visit_gated_forms():
    """Contiguous SURVEY_DISPLAY_ORDER span, plus any stranded extras."""
    forms = set(INPERSON_VISIT_EXTRA_FORMS)
    try:
        start = SURVEY_DISPLAY_ORDER.index(INPERSON_VISIT_FIRST)
        stop = SURVEY_DISPLAY_ORDER.index(INPERSON_VISIT_LAST)
    except ValueError:
        return forms
    if stop < start:
        start, stop = stop, start
    return forms | set(SURVEY_DISPLAY_ORDER[start:stop + 1])


INPERSON_VISIT_GATED_FORMS = _derive_visit_gated_forms()


# Friendly names shown in the Survey Completeness table.
# Any instrument omitted here falls back to an automatically generated name.
SURVEY_DISPLAY_NAMES = {
    "start_page": "Start Page",
    "participant_status_form": "Participant Status",
    "ace_wave_3_demographics_selfreport_19": 
        "Demographics Self-Report (Adult)",
    "ace_wave_3_demographics_self_report_1218_yo": 
        "Demographics Self-Report (Adolescent)",
    "ace_wave_3_demographics_informantreport": 
        "Demographics Informant-Report",
    "lifetime_count_of_psychiatric_diagnoses_selfreport": 
        "Lifetime Psychiatric Diagnoses Self-Report",
    "lifetime_count_of_psychiatric_diagnoses_informantr":
        "Lifetime Psychiatric Diagnoses Informant-Report",
    "pds_selfreport_male_version_2023":
        "PDS (Male Version)",
    "pds_selfreport_female_version_2023":
        "PDS (Female Version)",
    "combined_pds_another_assigned_sex":
        "PDS (Another Assigned Sex)",
    "selfassessment_of_autistic_traits":
        "SAAT",
    "cati":
        "CATI",
    "raads14_screen":
        "RAADS-14 Screen",
    "friendship_questionnaire":
        "Friendship Questionnaire",
    "promis_general_life_satisfaction_short_form_5a":
        "PROMIS General Life Satisfaction (Adult)",
    "promis_meaning_and_purpose_short_form_4a":
        "PROMIS Meaning and Purpose (Adult)",
    "promis_pediatric_life_satisfaction_short_form_4a":
        "PROMIS General Life Satisfaction (Adolescent)",
    "promis_pediatric_meaning_and_purpose_short_form_4a":
        "PROMIS Meaning and Purpose (Adolescent)",
    "asqol_19":
        "ASQoL (Adult)",
    "asqol_1618":
        "ASQoL (Adolescent)",
    "whoqolbref_physical_domain":
        "WHOQoL",
    "isq8":
        "ISQ-8",
    "scq_lifetime_informantreport":
        "SCQ Lifetime",
    "inperson_ef_compensation":
        "EF Compensation",
    "inperson_wasiii":
        "WASI-3",
    "inperson_dkefs_verbal_fluency_task":
        "DKEFS Verbal Fluency Task",
    "inperson_stop_and_go_switch_test_game":
        "Stop and Go",
    "inperson_cantab":
        "CANTAB",
    "inperson_beck_depression_inventory":
        "BDI",
    "inperson_ascasd":
        "ASC-ASD",
    "inperson_asaa":
        "ASA-A",
    "inperson_dsm5_adult_selfreport":
        "DSM-5 Self-Report (Adult)",
    "inperson_dsm5_child_selfreport":
        "DSM-5 Self-Report (Adolescent)",
    "inperson_dsm5_child_informantreport":
        "DSM-5 Informant-Report (Adolescent)",
    "inperson_ptsd_checklist_for_dsm5":
        "PTSD Checklist",
    "inperson_abcl":
        "ABCL",
    "inperson_cbcl":
        "CBCL",
    "inperson_ados_module_3":
        "ADOS Module 3",
    "inperson_ados_module_4":
        "ADOS Module 4 or BOSA",
    "inperson_ados_participant_feedback_questionnaire":
        "ADOS Feedback Questionnaire",
    "inperson_bosa_participant_feedback_questionnaire":
        "BOSA Feedback Questionnaire",
    "after_visit_ados_participant_followup":
        "ADOS Follow-Up",
    "after_visit_glasgow_sensory_questionnaire":
        "Glasgow Sensory Questionnaire",
    "after_visit_tas8":
        "TAS-8",
    "informant_interview":
        "Informant Interview",
    "participant_interview":
        "Participant Interview",
    "dsm5_checklist":
        "DSM-5 Checklist",
    "staff_brief2_parent_form_shiny_app_upload":
        "BRIEF-2 Parent (Shiny)",
    "staff_briefa_informant_report_shiny_app_upload":
        "BRIEF-A Informant (Shiny)",
    "srs2":
        "SRS-2 Informant-Report (Child) (Shiny)",
    "staff_srs2_adult_informant_report_shiny_app_upload":
        "SRS-2 Informant-Report (Adult) (Shiny)",
    "staff_wave_3_neuroimaging_session_notes_d7c4":
        "Neuroimaging Session Notes",
    "inperson_behavioral_assessment_interruptions":
        "Behavioral Assessment Interruptions",
    "abas3_upload":
        "ABAS (Upload)",
    "the_gender_selfreport":
        "Gender Questionnaire — Self-Report"
}

# ---------------------------------------------------------------------------
# 13. INCLUDED COHORT  -> for the "records by site - included" top line
# ---------------------------------------------------------------------------
# A record counts toward the "included" cohort when inclusion == Include (1).
def is_included(rrow):
    return (rrow.get("inclusion", "") or "").strip() == "1"

# ---------------------------------------------------------------------------
# 14. MISSINGNESS TRACKER  -> only these fields appear in the missingness panel
# ---------------------------------------------------------------------------
# The bulk of "what's missing" now comes from survey completeness, so the
# per-variable missingness tracker is trimmed to a short, high-value list.
MISSINGNESS_FIELDS = [
    "site", "group", "phenotype", "int_date", "int_age",
    "participant_white", "diagnosis_12yo", "age_at_dx", "inclusion",
]


# ---------------------------------------------------------------------------
# 14. CATI  (Comprehensive Autistic Trait Inventory)
# ---------------------------------------------------------------------------
# Subscale and total scores are only interpretable when the respondent
# answered every item. REDCap still exports a computed score when items are
# missing, so the scores must be validated against the item-missingness
# counter before any of them are summarized -- otherwise a score built from
# partial data is silently averaged in with complete ones.
#
# CATI_MISSED_FIELD counts unanswered items (0-42). Only records at exactly 0
# contribute to the statistics below. Records with >0 are counted and reported
# separately so the section's denominator is always visible.
CATI_MISSED_FIELD = "cati_missed"
CATI_MISSED_MAX = 42

# The REDCap instrument name, used to reuse the Survey Queue eligibility rule
# so the section's denominator matches who was actually assigned the CATI.
CATI_FORM = "cati"

# Display order for the section: subscales first, total last.
CATI_SCORES = [
    ("soc_total", "Social"),
    ("com_total", "Communication"),
    ("cam_total", "Social camouflage"),
    ("rig_total", "Cognitive rigidity"),
    ("rep_total", "Repetitive behaviours"),
    ("sen_total", "Sensory sensitivity"),
    ("cati_total", "CATI total"),
]
CATI_TOTAL_FIELD = "cati_total"

# Suppressed from the generic categorical/continuous sections: these are
# rendered by the dedicated CATI section, which applies the validity filter.
CATI_RAW_FIELDS = {CATI_MISSED_FIELD} | {f for f, _ in CATI_SCORES}


# ---------------------------------------------------------------------------
# 15. DATA-QUALITY FLAG THRESHOLDS
# ---------------------------------------------------------------------------
# A variable in the missingness table whose missing-among-expected rate
# exceeds this percentage raises a data-quality flag and increments the
# headline counter. "Among expected" matters: branched fields are judged only
# against the records that should have answered them.
MISSINGNESS_FLAG_PCT = 1.0


# ---------------------------------------------------------------------------
# 16. MANUSCRIPT-STYLE TABLE 1
# ---------------------------------------------------------------------------
# Table 1 is computed from participant-level raw records, but the dashboard
# receives only six precomputed aggregate views (two cohorts x three column
# presets).  Participant-level values are never embedded in the HTML.
TABLE1_CROSSWALK_VERSION = "ACE-W3-2026-09-21-v1"
TABLE1_DEFAULT_COHORT = "all_nonwithdrawn"
TABLE1_DEFAULT_STRATUM = "group"
TABLE1_ONLY_FIELDS = {
    "ace_demo_17", "ace_demo_informant_13a", "ace_demo_26a",
    "ace_demo_informant_15", "wasi_fs2_comp",
}

TABLE1_COHORTS = {
    "all_nonwithdrawn": "All non-withdrawn records",
    "included": "Included records",
}

TABLE1_STRATA = {
    "group": {
        "label": "Study group",
        "field": "group_category",
        "categories": ["ASD group", "Unaffected sibling", "Control"],
    },
    "site": {
        "label": "Site",
        "field": "site_category",
        "categories": ["GMU", "Children's National", "UCLA", "Yale", "UVA"],
    },
    "sex": {
        "label": "Sex",
        "field": "sex_category",
        "categories": ["Female", "Male", "Another sex"],
    },
}

# percent_base is either the full table-column N, the variable's applicable
# N, or valid responses only.  The latter is used only when the report does
# not contain the source branching field needed to distinguish true missing
# responses from structural blanks.
TABLE1_VARIABLES = [
    {
        "key": "age_years", "label": "Age at time forms were sent, years",
        "kind": "continuous", "app": "app_all", "decimals": 1,
        "footnotes": ["age"],
    },
    {
        "key": "sex_category", "label": "Sex", "kind": "categorical",
        "app": "app_all", "categories": ["Female", "Male", "Another sex"],
        "percent_base": "column", "footnotes": ["sex"],
    },
    {
        "key": "race_category", "label": "Race", "kind": "categorical",
        "app": "app_all", "categories": list(RACE_MAP.values()),
        "percent_base": "column", "footnotes": ["race"],
    },
    {
        "key": "ethnicity_category", "label": "Hispanic/Latino ethnicity",
        "kind": "categorical", "app": "app_all",
        "categories": ["Yes", "No"], "percent_base": "column",
        "footnotes": ["race"],
    },
    {
        "key": "site_category", "label": "Site", "kind": "categorical",
        "app": "app_all", "categories": list(VALUE_MAPS["site"].values()),
        "percent_base": "column", "footnotes": [],
    },
    {
        "key": "group_category", "label": "Study group",
        "kind": "categorical", "app": "app_all",
        "categories": list(VALUE_MAPS["group"].values()),
        "percent_base": "column", "footnotes": ["group"],
    },
    {
        "key": "asd_source_category", "label": "ASD recruitment source",
        "kind": "categorical", "app": "app_asd",
        "categories": list(VALUE_MAPS["asd_group"].values()),
        "percent_base": "applicable", "footnotes": ["conditional"],
    },
    {
        "key": "age_dx_years", "label": "Age at formal autism diagnosis, years",
        "kind": "continuous", "app": "app_asd", "decimals": 1,
        "footnotes": ["diagnosis_age", "conditional"],
    },
    {
        "key": "wasi_fsiq2", "label": "WASI FSIQ-2 Composite Score",
        "kind": "continuous", "app": "app_all", "decimals": 1,
        "footnotes": ["wasi"],
    },
    {
        "key": "education_category",
        "label": "Highest education attained (self-report)",
        "kind": "categorical", "app": "app_adult",
        "categories": list(EDUCATION_MAP.values()),
        "percent_base": "applicable", "footnotes": ["education"],
    },
    {
        "key": "grade_category",
        "label": "Current grade in school (informant-report)",
        "kind": "categorical", "app": "app_grade",
        "categories": list(GRADE_MAP.values()),
        "percent_base": "valid", "footnotes": ["education", "branch_unknown"],
    },
    {
        "key": "personal_income_category",
        "label": "Personal income from work, last 12 months (self-report)",
        "kind": "categorical", "app": "app_personal_income",
        "categories": list(PERSONAL_INCOME_MAP.values()),
        "percent_base": "valid", "footnotes": ["income", "branch_unknown"],
    },
    {
        "key": "household_income_category",
        "label": "Household income, last 12 months (informant-report)",
        "kind": "categorical", "app": "app_informant_minor",
        "categories": list(INCOME_MAP.values()),
        "percent_base": "applicable", "footnotes": ["income", "conditional"],
    },
]

TABLE1_FOOTNOTES = {
    "summary": ("Continuous values are mean (SD) with valid n; categorical "
                "values are n (%). Percentages use the table-column N unless "
                "a conditional block identifies an applicable- or valid-response denominator."),
    "withdrawn": ("Participants marked Withdrawn are excluded from both the "
                  "All and Included views. 'All' therefore means all non-withdrawn records."),
    "age": ("Age is int_age / 12: age at the time pre-visit forms were sent. "
            "It is not age at consent or age at the in-person visit."),
    "sex": ("Sex is taken only from the Start Page sex field (1=Male, "
            "2=Female, 3=Another sex). It is not combined with gender or with "
            "demographic-form sex fields whose numeric coding is reversed."),
    "race": ("Race and Hispanic/Latino ethnicity use valid adult self-report "
             "first and valid informant report as fallback. Concise race labels "
             "correspond to: American Indian, Native American, Indigenous, First "
             "Nation, or Alaska Native; Asian; Native Hawaiian or Other Pacific "
             "Islander; Black, African American, Afro-Caribbean, or African; "
             "White/Caucasian; and More Than One Race. Adolescent free text is "
             "not automatically coded."),
    "group": ("Study group is an enrollment group and is not itself a clinical "
              "diagnosis."),
    "conditional": ("Conditional blocks use the applicable participant count "
                    "shown in the block header; structurally inapplicable records "
                    "do not enter the percentage denominator."),
    "diagnosis_age": ("Age at formal diagnosis uses the exported age_at_dx "
                      "calculation and is summarized only for the ASD study group."),
    "wasi": ("WASI FSIQ-2 uses wasi_fs2_comp. Missing scores do not remove a "
             "participant from the Table 1 cohort."),
    "education": ("Highest education attained (adult self-report) and current "
                  "grade in school (informant-report) are displayed separately "
                  "because they are different constructs."),
    "income": ("Personal income from work (adult self-report) and household "
               "income (informant-report) are displayed separately and are not "
               "harmonized into a single income measure."),
    "branch_unknown": ("The export does not include the upstream branch field "
                       "for this item. Percentages therefore use valid responses; "
                       "blank values cannot be classified reliably as missing "
                       "versus not applicable."),
}
