import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
TRACE_PATH = ROOT_DIR / "trace.jsonl"
METADATA_PATH = ROOT_DIR / "metadata.json"

# Model name is declared here in source code per lab rule #4 (not in .env).
MODEL_NAME = "qwen2.5:7b-instruct"
MODEL_PARAMETER_SIZE = "7B"
MODEL_QUANTIZATION = "Q4_K_M"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT_SECONDS = 120
LLM_MAX_RETRIES = 3
LLM_TEMPERATURE = 0.1

POLICY_VERSION = "EC_POLICY_V1"
CURRENCY = "BRL"
