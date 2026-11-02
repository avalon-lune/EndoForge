"""Bind direct/resumable geometry evidence to the exact shipped auditor sources.

Report paths are provenance strings, never files to execute or read. A staged
absolute prefix may differ, but the complete Scripts-relative suffix and exact
dependency membership must match. Passing this identity check does not rerun or
replace the geometric/numeric acceptance gates.
"""
import hashlib
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError('Geometry auditor identity: '+message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


DIRECT = {
    'geometry': ('endoforge.phase5.independent-geometry.v1', 'Scripts/Phase5/audit_geometry.py'),
    'contact': ('endoforge.phase5.independent-contact.v1', 'Scripts/Phase5/audit_contact.py'),
    'liver': ('endoforge.phase5.liver-contact-audit.v1', 'Scripts/Phase5/audit_liver_contact.py'),
}
KERNEL = 'Scripts/audit_phase4_collision_geometry.py'
PARALLEL = 'Scripts/Phase5/audit_trace_parallel.py'


def verify_geometry_report(report, source_root, kind, runner_phase=None):
    """Verify an evidence report against a workspace root or packaged Source/.

    kind is geometry/contact/liver. runner_phase=None requires a direct audit;
    runner_phase=6 or7 requires that exact resumable runner/schema. Native Phase7
    requalification deliberately uses the unchanged Phase6 runner; current UE
    presented paths use Phase7. Call once per source tree when both root and
    shipped identity must be checked. Returns canonical verified hashes.
    """
    require(kind in DIRECT, 'unknown report kind')
    require(runner_phase is None or type(runner_phase) is int and runner_phase in (6,7), 'unsupported runner phase')
    require(isinstance(report,dict) and report.get('passed') is True, 'report is missing or failed')
    root=Path(source_root).resolve()
    direct_schema,auditor=DIRECT[kind]
    expected={auditor:sha(root/auditor)}
    if kind=='contact':
        expected[KERNEL]=sha(root/KERNEL)
        require(report.get('geometry_kernel_sha256')==expected[KERNEL], 'contact kernel differs')
    if runner_phase is None:
        require(report.get('schema')==direct_schema, 'expected direct '+kind+' schema')
        require(report.get('audit_script_sha256')==expected[auditor], 'direct auditor differs')
        require('auditor_identities' not in report and 'script_sha256' not in report,
                'direct report contains ambiguous resumable identities')
    else:
        require(kind in ('contact','liver'), 'geometry has no resumable runner')
        require(report.get('schema')==f'endoforge.phase{runner_phase}.parallel-{kind}.v1' and
                report.get('kind')==kind, 'wrong resumable phase or kind')
        runner=f'Scripts/Phase{runner_phase}/audit_trace_resumable.py'
        expected[runner]=sha(root/runner)
        expected[PARALLEL]=sha(root/PARALLEL)
        require(report.get('script_sha256')==expected[runner], 'resumable runner differs')
        require(report.get('auditor_sha256')==expected[auditor], 'resumable leaf auditor differs')
        identities=report.get('auditor_identities')
        require(isinstance(identities,dict) and len(identities)==len(expected), 'dependency membership count differs')
        seen=set()
        for recorded,digest in identities.items():
            require(isinstance(recorded,str) and recorded, 'invalid dependency provenance path')
            normalized=recorded.replace('\\','/').rstrip('/')
            require(not any(p in ('.','..') for p in normalized.split('/')), 'noncanonical dependency provenance path')
            matches=[name for name in expected if normalized.casefold()==name.casefold() or
                     normalized.casefold().endswith('/'+name.casefold())]
            require(len(matches)==1, 'unexpected dependency Scripts-relative path: '+recorded)
            relative=matches[0]
            require(relative not in seen, 'duplicate dependency with another staged prefix: '+relative)
            require(digest==expected[relative], 'dependency bytes differ: '+relative)
            seen.add(relative)
        require(seen==set(expected), 'missing required dependency')
    return {'verified':True,'kind':kind,'runner_phase':runner_phase,
            'report_schema':report['schema'],'source_sha256':expected,
            'scope':'Exact auditor/dependency identity; independent numeric acceptance remains required.'}
