"""Writes one JSON line per agent invocation to trace.jsonl.

The file is truncated at the start of each full run (README: "không append,
chỉ cần lượt chạy mới nhất").
"""
import json
from datetime import datetime, timezone
from pathlib import Path


class Tracer:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.write_text("", encoding="utf-8")  # fresh file each run

    def log(self, **fields):
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), **fields}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
