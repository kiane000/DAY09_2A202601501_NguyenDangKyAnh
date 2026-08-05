"""Independent post-hoc validation of output/*.json before zipping for submission.

Re-derives ground truth straight from the CSVs via policy_engine and checks
every output file against it, plus schema/format/hard-gate rules — deliberately
not reusing any in-process state from the pipeline run.
"""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from src import config
from src.data_store import DataStore
from src.policy_engine import apply_policy
from src.schemas import CaseOutput


def main() -> int:
    data_store = DataStore(config.DATA_DIR)
    input_files = sorted(config.INPUT_DIR.glob("EC_*.json"))
    expected_ids = {p.stem for p in input_files}

    output_files = sorted(config.OUTPUT_DIR.glob("*.json"))
    actual_ids = {p.stem for p in output_files}

    problems_by_case: dict[str, list[str]] = {}

    stray = actual_ids - expected_ids
    if stray:
        problems_by_case["__stray_files__"] = [f"file lạ trong output/: {sorted(stray)}"]
    missing = expected_ids - actual_ids
    if missing:
        problems_by_case["__missing_files__"] = [f"thiếu output cho: {sorted(missing)}"]

    for input_path in input_files:
        case_id = input_path.stem
        output_path = config.OUTPUT_DIR / f"{case_id}.json"
        problems = []
        if not output_path.exists():
            continue  # already reported above

        case_input = json.loads(input_path.read_text(encoding="utf-8"))
        claimed_order_id = case_input["customer_request"]["claimed_order_id"]

        try:
            raw = json.loads(output_path.read_text(encoding="utf-8"))
            output = CaseOutput.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            problems_by_case[case_id] = [f"schema invalid: {exc}"]
            continue

        if output.case_id != case_id:
            problems.append(f"case_id trong file ({output.case_id}) != tên file ({case_id})")

        facts = data_store.get_order_facts(claimed_order_id)
        expected = apply_policy(facts)

        if output.assessment.primary_issue != expected.primary_issue:
            problems.append(
                f"primary_issue sai: got={output.assessment.primary_issue} "
                f"expected={expected.primary_issue}"
            )
        if output.assessment.case_status != expected.case_status:
            problems.append(
                f"case_status sai: got={output.assessment.case_status} "
                f"expected={expected.case_status}"
            )
        fr = output.financial_resolution
        for field, expected_value in (
            ("item_total_brl", expected.item_total_brl),
            ("freight_total_brl", expected.freight_total_brl),
            ("payment_total_brl", expected.payment_total_brl),
            ("recommended_refund_brl", expected.recommended_refund_brl),
        ):
            got_value = getattr(fr, field)
            if abs(got_value - expected_value) > 0.01:
                problems.append(f"{field} sai: got={got_value} expected={expected_value}")

        if not expected.matched_rule:
            problems.append("CẢNH BÁO: case này không khớp rõ ràng rule nào (fallback) — cần review tay")

        for eid in output.evidence_ids:
            kind, _, rest = eid.partition(":")
            if kind == "order" and (not facts.order or rest != facts.order.order_id):
                problems.append(f"evidence order không tồn tại: {eid}")
            elif kind == "item" and rest not in {f"{i.order_id}:{i.order_item_id}" for i in facts.items}:
                problems.append(f"evidence item không tồn tại: {eid}")
            elif kind == "payment" and rest not in {
                f"{p.order_id}:{p.payment_sequential}" for p in facts.payments
            }:
                problems.append(f"evidence payment không tồn tại: {eid}")
            elif kind == "seller" and rest not in facts.sellers:
                problems.append(f"evidence seller không tồn tại: {eid}")

        if problems:
            problems_by_case[case_id] = problems

    invalid_case_ids = {k for k in problems_by_case if k in expected_ids} | missing
    print(f"Tổng số case input: {len(input_files)}; output hợp lệ hoàn toàn: "
          f"{len(input_files) - len(invalid_case_ids)}")
    if problems_by_case:
        print("\n=== VẤN ĐỀ PHÁT HIỆN ===")
        for case_id, problems in problems_by_case.items():
            print(f"\n{case_id}:")
            for p in problems:
                print(f"  - {p}")
        return 1

    print("Tất cả case pass validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
