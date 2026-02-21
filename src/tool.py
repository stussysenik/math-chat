import asyncio
import inspect
from pydantic import BaseModel
from typing import Dict, Any, List

from src.schema import ExtractedProblem
from src.worker import execute_deterministic_pipeline

class SolveMathProblemSchema(BaseModel):
    """
    Standard tool-call parameters that an orchestrating LLM (e.g. GLM-4, Claude)
    must generate to interact with the LEAN-verified deterministic pipeline.
    """
    problem_definition: ExtractedProblem

class OrchestratorTool:
    """
    Wraps the entire deterministic math pipeline into a single standard tool definition
    that can be passed into OpenAI/Anthropic/GLM function calling arrays.
    """
    
    @staticmethod
    def get_tool_schema() -> Dict[str, Any]:
        """Returns the JSON Schema definition for LLM tool binding."""
        return {
            "type": "function",
            "function": {
                "name": "solve_deterministic_math_problem",
                "description": (
                    "Executes a rigorous, LEAN-lite verified mathematical pipeline. "
                    "Takes extracted physics/math variables and equations, solves them deterministically "
                    "using SymPy/SciPy, runs numerical domain sweeps to prove correctness, and outputs "
                    "both Socratic explainer prompts and Desmos graphical states."
                ),
                "parameters": SolveMathProblemSchema.model_json_schema()
            }
        }
    @staticmethod
    def execute_tool(extracted_problem_dict: dict, dev_mode: bool = False) -> str:
        """
        Dispatches the rigorous mathematical pipeline to a background Celery worker.
        Returns the asynchronous job_id to the Orchestrator/OpenWebUI so the UI
        doesn't hang while background engines compute deep limits.
        """
        job = execute_deterministic_pipeline.delay(extracted_problem_dict, dev_mode)
        return f"Validating math deterministically off-thread. Background Job ID: {job.id}. Poll endpoint to retrieve the structured Seminar UI block."
