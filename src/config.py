import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
LOGGING_DIR = ROOT_DIR / "logging"
TRACE_PATH = LOGGING_DIR / "trace.jsonl"
METADATA_PATH = LOGGING_DIR / "metadata.json"

# Model name is declared here in source code per lab rule #4 (not in .env).
# NOTE: gpt-4o-mini was chosen by explicit user request. OpenAI does not
# publish parameter counts for this model, and public estimates put it well
# above the lab's <=10B-parameter constraint (README lưu ý #1) — this is a
# known, deliberate deviation from that rule, not an oversight. Kept honest
# here (and in metadata.json) instead of fabricating a parameter size.
LLM_PROVIDER = "openai"  # "openai" or "ollama"
MODEL_NAME = "gpt-4o-mini"
MODEL_PARAMETER_SIZE = (
    "undisclosed by OpenAI (official figure not published; unverified public "
    "estimates vary widely, some below and some above 10B — compliance with "
    "the lab's <=10B limit cannot be confirmed for this closed-weight model)"
)
MODEL_QUANTIZATION = "n/a (hosted API)"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT_SECONDS = 120
LLM_MAX_RETRIES = 3
LLM_TEMPERATURE = 0.1

POLICY_VERSION = "EC_POLICY_V1"
CURRENCY = "BRL"
