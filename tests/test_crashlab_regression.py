import copy
import json
from pathlib import Path
import pytest
from stateproof.crashlab import load_contract, run_local, execute_synthetic_crash
from stateproof.crashlab_regression import make_test_source, export_receipt, repair_check

CONTRACT = Path(__file__).parent.parent / "contracts" / "support_credit.json"


def fixture():
    data = load_contract(CONTRACT)
    return data, run_local(data, "keyword")


def test_failure_is_reproducible():
    data, report = fixture()
    assert report["result"]["false_success"]
    assert not report["result"]["oracle"]["correct_state"]
    assert execute_synthetic_crash(data, report["plan"])["false_success"]


def test_generated_regression_compiles():
    data, report = fixture()
    compile(make_test_source(report, data), "generated", "exec")


def test_generated_regression_actually_fails():
    data, report = fixture()
    scope = {"__name__": "synthetic_regression"}
    exec(compile(make_test_source(report, data), "generated", "exec"), scope)
    with pytest.raises(AssertionError, match="Retry caused"):
        scope["test_retry_does_not_duplicate_effect"]()


def test_repaired_adapter_passes():
    data, report = fixture()
    fixed = repair_check(report, data)
    assert fixed["before_failed"] and fixed["after_passed"]
    assert fixed["before"]["effect_count"] == 2
    assert fixed["after"]["effect_count"] == 1


def test_no_regression_from_healthy_case():
    data = load_contract(CONTRACT)
    good = run_local(data, "writes_first")
    with pytest.raises(ValueError, match="verified synthetic failure"):
        make_test_source(good, data)


def test_contract_hash_mismatch_rejected():
    data, report = fixture()
    bad = copy.deepcopy(data)
    bad["public"]["scenario"] = "Changed"
    with pytest.raises(ValueError, match="different contract"):
        make_test_source(report, bad)


def test_plan_tampering_rejected():
    data, report = fixture()
    bad = copy.deepcopy(report)
    bad["plan"]["operation_id"] = "unlisted_operation"
    with pytest.raises(ValueError, match="not allowed"):
        make_test_source(bad, data)


def test_repeated_export_wont_overwrite(tmp_path):
    data, report = fixture()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(report))
    dest = tmp_path / "test_generated.py"
    first = export_receipt(receipt, CONTRACT, dest)
    assert dest.exists() and first["verification"]["after_passed"]
    with pytest.raises(FileExistsError):
        export_receipt(receipt, CONTRACT, dest)
