import json
import platform
import sys
import time
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from src import config
from src.coordinator import Coordinator
from src.data_store import DataStore
from src.tracer import Tracer


def main() -> int:
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    data_store = DataStore(config.DATA_DIR)
    tracer = Tracer(config.TRACE_PATH)
    coordinator = Coordinator(data_store, tracer)

    input_files = sorted(config.INPUT_DIR.glob("EC_*.json"))
    if not input_files:
        print(f"No input files found in {config.INPUT_DIR}", file=sys.stderr)
        return 1

    ok, failed = 0, []
    start = time.monotonic()
    for path in input_files:
        case_id = path.stem
        try:
            coordinator.run_case(path)
            ok += 1
            print(f"[OK]   {case_id}")
        except Exception as exc:  # noqa: BLE001 - keep processing remaining cases
            failed.append(case_id)
            tracer.log(case_id=case_id, agent="coordinator", status="fatal_error", error=str(exc))
            print(f"[FAIL] {case_id}: {exc}", file=sys.stderr)

    elapsed = time.monotonic() - start
    print(f"\n{ok}/{len(input_files)} case thành công, {len(failed)} lỗi. "
          f"Thời gian: {elapsed:.1f}s")
    if failed:
        print(f"Case lỗi: {failed}", file=sys.stderr)

    write_metadata(len(input_files), ok, len(failed), elapsed)
    return 1 if failed else 0


def write_metadata(total: int, ok: int, failed: int, elapsed_seconds: float) -> None:
    metadata = {
        "model_name": config.MODEL_NAME,
        "model_parameter_size": config.MODEL_PARAMETER_SIZE,
        "model_quantization": config.MODEL_QUANTIZATION,
        "framework": "Custom hand-rolled Python orchestrator (no agent framework) calling Ollama",
        "runtime": {
            "engine": "Ollama",
            "ollama_base_url": config.OLLAMA_BASE_URL,
            "python_version": platform.python_version(),
            "os": platform.platform(),
        },
        "agents": [
            "coordinator",
            "order_seller_agent",
            "payment_agent",
            "delivery_agent",
            "policy_agent",
            "verifier_agent",
        ],
        "policy_version": config.POLICY_VERSION,
        "run_summary": {"total_cases": total, "succeeded": ok, "failed": failed,
                         "elapsed_seconds": round(elapsed_seconds, 1)},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    config.METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
