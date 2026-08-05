from typing import Type, TypeVar

from pydantic import BaseModel

from src import config, llm_client
from src.tracer import Tracer

T = TypeVar("T", bound=BaseModel)


class Agent:
    name: str = "agent"

    def __init__(self, tracer: Tracer):
        self.tracer = tracer

    def call_llm(
        self,
        case_id: str,
        system_prompt: str,
        user_prompt: str,
        output_model: Type[T],
    ) -> T:
        try:
            result = llm_client.call_structured(system_prompt, user_prompt, output_model)
            self.tracer.log(
                case_id=case_id,
                agent=self.name,
                model=config.MODEL_NAME,
                status="ok",
                attempts=result.attempts,
                latency_ms=round(result.latency_ms, 1),
                user_prompt=user_prompt,
                llm_output=result.parsed.model_dump(),
            )
            return result.parsed
        except Exception as exc:  # noqa: BLE001 - must never crash a case run
            self.tracer.log(
                case_id=case_id,
                agent=self.name,
                model=config.MODEL_NAME,
                status="error",
                error=str(exc),
                user_prompt=user_prompt,
            )
            raise
