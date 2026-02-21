import pytest
from src.tool import OrchestratorTool

def test_tool_schema_generation():
    schema = OrchestratorTool.get_tool_schema()
    
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "solve_deterministic_math_problem"
    assert "parameters" in schema["function"]
    
    params = schema["function"]["parameters"]
    assert "problem_definition" in params["properties"]
    
    # Check that ExtractedProblem nested properties are successfully pushed to JSON schema
    assert "$defs" in schema["function"]["parameters"]
    extracted_problem_schema = schema["function"]["parameters"]["$defs"]["ExtractedProblem"]
    assert "domain" in extracted_problem_schema["properties"]
    assert "variables" in extracted_problem_schema["properties"]

def test_tool_execution():
    async def run_test():
        # Simulate an unstructured LLM dict matching our schema
        llm_payload = {
            "problem_definition": {
                "domain": {
                     "domain": "algebra",
                     "confidence": 0.9,
                     "reasoning": "Simple linear algebra"
                },
                "variables": [
                     {"symbol": "x", "description": "Unknown"}
                ],
                "equations": [
                     {"expression": "2*x = 10", "description": "Basic isolating"}
                ],
                "givens": {},
                "goal": "x"
            }
        }
        
        events = await OrchestratorTool.execute_tool(llm_payload["problem_definition"], dev_mode=True)
        
        # We expect multiple SSE states
        assert len(events) >= 4
        
        # End-to-end check
        socratic_event = events[-2]
        assert "event: socratic_dialogue" in socratic_event
        assert "DEV MODE TELEMETRY" in socratic_event
        assert "fold the origami piece backwards" in socratic_event

    import asyncio
    asyncio.run(run_test())
