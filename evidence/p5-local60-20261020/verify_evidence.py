"""Verify immutable P5 inputs and the derived publication without running business code."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

BATCH = Path(__file__).resolve().parent


def load(relative):
    return json.loads((BATCH / relative).read_text(encoding='utf-8'))


def sha(relative):
    return hashlib.sha256((BATCH / relative).read_bytes()).hexdigest()


def main():
    r1 = load('matrix-r1/results.json')
    r2 = load('matrix-r2/results.json')
    combined = load('matrix-combined/results.json')
    continuation = load('matrix-combined/continuation.json')
    revision = load('continuation-revision-1.json')
    sources = load('matrix-r1/experiment.json')['source_sha256']
    source_mismatches = [name for name, expected in sources.items()
                         if sha(Path('binding/source') / name) != expected]
    assert len(r1) == 29 and len(r2) == 31 and len(combined) == 60
    assert combined == r1 + r2
    assert len({(r['scenario'], r['method'], r['repeat']) for r in combined}) == 60
    assert sha('matrix-r1/results.json') == continuation['r1_result_sha256'] == revision['original_results_sha256']
    assert sha('matrix-r2/results.json') == continuation['r2_result_sha256']
    assert sha('continuation-revision-1.json') == continuation['revision_sha256']
    assert sha('bound-plan.json') == revision['original_plan_sha256']
    assert len(sources) == 174 and not source_mismatches
    assert sources == load('matrix-r2/experiment.json')['source_sha256']
    assert sources == load('matrix-combined/experiment.json')['source_sha256']
    assert sources == load('bound-plan.json')['source_sha256'] == revision['original_source_sha256']
    assert sha('resume-guarded-run.py') == revision['guarded_runner_sha256']
    assert sha('resume_local60.py') == revision['controller_sha256']
    assert continuation['same_frozen_source'] and revision['guard_semantic_diff_verified']
    assert [(r['scenario'], r['method'], r['repeat']) for r in combined] == [tuple(x) for x in revision['planned_order']]
    incident_hashes = {}
    for row in combined:
        relative = Path('matrix-combined/incidents') / (row['incident_id'] + '.json')
        original = Path('matrix-r1' if row in r1 else 'matrix-r2') / 'incidents' / relative.name
        assert (BATCH / relative).read_bytes() == (BATCH / original).read_bytes()
        incident_hashes[row['incident_id']] = sha(relative)
    execution = load('continuation-execution-result.json')
    cleanup = load('cleanup-result.json')
    assert execution['status'] == 'EVALUATOR_FINISHED' and execution['terminal_cells'] == 60
    assert execution['evaluator_exit_code'] == 1 and execution['cleanup_exit_code'] == 0
    assert cleanup['status'] == 'STOPPED' and cleanup['remaining_batch_listeners'] == []
    healthy = cleanup['stages']['final_h00']
    assert healthy['passed'] and healthy['success'] == healthy['requests'] == 30
    assert healthy['completed_workflows'] == 10
    summary = load('publication/summary.json')
    assert load('publication/results.json') == combined
    expected = {'MR': (3, 0, 0), 'M0': (15, 0, 0), 'M1': (6, 125, 410772), 'M2v2': (6, 15, 12345)}
    for method, (passed, calls, tokens) in expected.items():
        observed = summary['methods'][method]
        assert (observed['cells'], observed['strict_continuous_acceptance_passed'],
                observed['model_calls'], observed['tokens']) == (15, passed, calls, tokens)
    paired = summary['paired_M2v2_vs_M0']
    assert paired['confirmed_pairs'] == 6 and paired['median_paired_elapsed_ratio'] == 1.216934
    assert paired['median_paired_recovery_observed_ratio'] == 1.552141 and not paired['criterion_met']
    assert len(load('publication/failed-cases.json')) == 30
    receipt = {
        'status': 'VERIFIED', 'recorded_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Read-only validation of recorded artifacts and derived reports; no business execution',
        'terminal_cells': 60, 'actual_attempts': 61, 'interrupted_attempts': 1,
        'original_29_rows_unchanged': True, 'combined_equals_r1_plus_r2': True,
        'r1_result_sha256': sha('matrix-r1/results.json'), 'r2_result_sha256': sha('matrix-r2/results.json'),
        'combined_result_sha256': sha('matrix-combined/results.json'),
        'source_fingerprints': 174, 'frozen_source_files_verified': 174,
        'r1_r2_bound_source_fingerprints_identical': True,
        'copied_raw_incidents_verified': 60, 'raw_incident_sha256': incident_hashes,
        'evaluator_exit_code': execution['evaluator_exit_code'], 'cleanup_status': cleanup['status'],
        'strict_continuous_acceptance': {m: summary['methods'][m]['strict_continuous_acceptance_passed'] for m in expected},
        'overall_time_criterion_met': False,
        'original_part_files_packaged_byte_for_byte': ['matrix-r1-results.json', 'matrix-r2-results.json'],
    }
    (BATCH / 'publication/integrity-verification.json').write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: receipt[key] for key in ['status', 'terminal_cells', 'source_fingerprints',
                                                  'original_29_rows_unchanged', 'copied_raw_incidents_verified']}))


if __name__ == '__main__':
    main()
