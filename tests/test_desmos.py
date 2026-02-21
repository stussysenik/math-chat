import pytest
import sympy as sp
from src.schema import ExtractedProblem, DomainClassification, MathVariable, MathEquation, VerificationPayload
from src.desmos import DesmosAdapter

def test_desmos_adapter_generates_valid_latex():
    problem = ExtractedProblem(
        domain=DomainClassification(domain="ode_first_order", confidence=1.0, reasoning="ODE"),
        variables=[
            MathVariable(symbol="y(t)", description="Height"),
            MathVariable(symbol="t", description="Time"),
        ],
        equations=[],
        givens={"k": 9.8},
        initial_conditions={},
        goal="y(t)"
    )
    
    # Mock sympy result
    t = sp.Symbol('t')
    y = sp.Function('y')
    eq = sp.Eq(y(t), sp.exp(t) - 9.8)
    
    sympy_result = {"solution": eq}
    verification = VerificationPayload(status="pass", tolerance_used=1e-6)
    
    adapter = DesmosAdapter()
    payload = adapter.generate_payload(problem, sympy_result, verification)
    
    assert payload["enabled"] is True
    expressions = payload["calculator_state"]["expressions"]["list"]
    
    # We expect y(t) = exp(t) - 9.8 to be in LaTeX and 'k = 9.8'
    lat_list = [e["latex"] for e in expressions]
    assert any("e^{t}" in expr for expr in lat_list)
    assert any("k = 9.8" in expr for expr in lat_list)

def test_desmos_skips_unverified():
    adapter = DesmosAdapter()
    payload = adapter.generate_payload(
        ExtractedProblem.construct(givens={}, goal=""), 
        {}, 
        VerificationPayload(status="fail", tolerance_used=1.0, message="")
    )
    assert payload["enabled"] is False
