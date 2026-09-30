"""Wire-format adapter only; all analysis is pipeline.build_report."""
import base64
from dataclasses import asdict
import json
from pipeline import build_report, ExportValidationError

def run_browser_report(csv_text, dictionary_text, queue_text, fdl_text, source_name, built_at):
    try:
        report = build_report(csv_text, dictionary_text=dictionary_text,
            queue_text=queue_text, fdl_text=fdl_text, source_name=source_name,
            built_at=built_at, export_links={})
    except ExportValidationError as error:
        return json.dumps({'ok': False, 'findings': [asdict(f) for f in error.findings]})
    # Restricted participant-level outputs never cross the worker boundary.
    files = {
        'dashboard': ('dashboard.html', 'text/html', report.dashboard_html),
        'table1': ('table1.html', 'text/html', report.table1_html),
        'numeric': ('table1_numeric.csv', 'text/csv', report.table1_numeric_csv),
        'audit': ('table1_metadata.json', 'application/json', report.table1_audit_json),
    }
    return json.dumps({'ok': True, 'summary': report.summary, 'messages': report.messages,
        'findings': [asdict(f) for f in report.findings], 'files': {
            key: {'name': name, 'type': mime, 'base64': base64.b64encode(value.encode('utf-8')).decode('ascii')}
            for key, (name, mime, value) in files.items()}})
