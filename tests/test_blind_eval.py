"""PREBUILD audit tests, not held-out evidence of model quality."""
import json
import pytest

from stateproof.blind_eval import BlindCohort, PUBLIC_TASK, baseline_report


def test_cohort_has_eight_opaque_cases_and_common_public_contract():
    cohort = BlindCohort(999)
    ids = cohort.public_case_ids()
    assert len(ids) == len(set(ids)) == 8
    public = [cohort.describe(cid) for cid in ids]
    assert all(p['contract'] == PUBLIC_TASK for p in public)
    assert all(p['case_id'].startswith('case-') for p in public)
    assert not any(word in json.dumps(public) for word in ('"repaired"', '"implementation"', 'gateway', 'orchestrator'))


@pytest.mark.parametrize('seed', [0, 1, 20261027])
def test_repaired_and_unrepaired_pairs_have_counterfactual_blindness(seed):
    cohort = BlindCohort(seed)
    grouped = {}
    for cid in cohort.public_case_ids():
        truth = cohort._private_truth(cid)
        grouped.setdefault(truth['implementation'], {})[truth['repaired']] = cid
    assert len(grouped) == 4
    for name, variants in grouped.items():
        assert set(variants) == {True, False}
        for fault in ('lost_ack', 'stale_read', 'partial_commit', 'clean'):
            weak1 = cohort.observe(variants[True], {'fault_id': fault, 'probe_id': 'ledger_count'})
            weak2 = cohort.observe(variants[False], {'fault_id': fault, 'probe_id': 'ledger_count'})
            # Case IDs differ; traces sometimes remain indistinguishable, demonstrating missing evidence.
            assert weak1['trace'] == weak2['trace']
            assert 'private_evidence' not in json.dumps(weak1)
            assert 'oracle' not in json.dumps(weak2)


def test_orchestrator_counterfactual_different_ground_truth_same_weak_probe():
    cohort = BlindCohort(20261027)
    matching = {x['repaired']: cid for cid in cohort.public_case_ids()
                if (x := cohort._private_truth(cid))['implementation'] == 'orchestrator'}
    c_fail, c_fix = matching[False], matching[True]
    args = {'fault_id': 'partial_commit', 'probe_id': 'ledger_count'}
    a, b = cohort.observe(c_fail, args), cohort.observe(c_fix, args)
    assert a['trace'] == b['trace']
    assert a['probe_result'] == b['probe_result']
    assert cohort._private_score(c_fail, [args])['missed_vulnerability']
    assert not cohort._private_score(c_fix, [args])['vulnerable']


@pytest.mark.parametrize('budget', [1, 2, 3, 4])
def test_deterministic_baselines_have_no_false_positives_and_four_clean_controls(budget):
    report = baseline_report(20261027, budget)
    assert report['cases'] == 8
    assert report['vulnerable_cases'] == 3  # 'healthy' has no fault even when unrepaired
    assert report['clean_cases'] == 5
    for r in report['strategies'].values():
        assert r['budget'] == budget
        assert r['false_positives'] == 0
        assert r['true_positives'] + r['false_negatives'] == 3
        assert r['true_negatives'] == 5


def test_invalid_case_and_experiment_rejected():
    cohort = BlindCohort()
    with pytest.raises(ValueError):
        cohort.describe('gateway')
    with pytest.raises(ValueError):
        cohort.observe(cohort.public_case_ids()[0], {'fault_id': 'run_shell', 'probe_id': 'effect_ids'})
    with pytest.raises(ValueError):
        baseline_report(budget=0)
