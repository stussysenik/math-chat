import pytest
import sympy as sp
from src.schema import ExtractedProblem, DomainClassification, MathVariable, MathEquation
from src.solver import SymPySolver
from src.verifier import NumericalVerifier

def test_verifier_algebraic_pass():
    problem = ExtractedProblem(
        domain=DomainClassification(domain="kinematics", confidence=1.0, reasoning="test"),
        variables=[
            MathVariable(symbol="v", description="Final velocity", assumptions=["real"]),
            MathVariable(symbol="t", description="Time", assumptions=["positive", "real"]),
        ],
        equations=[
            MathEquation(expression="v = 9.8*t", description="Kinematic equation")
        ],
        givens={"t": 2.0},
        initial_conditions={},
        goal="v"
    )
    
    solver = SymPySolver()
    result = solver.solve(problem)
    
    verifier = NumericalVerifier(tolerance=1e-5)
    payload = verifier.verify(problem, result)
    
    assert payload.status == "pass"
    assert payload.max_residual < 1e-5

def test_verifier_ode_sweep_pass():
    problem = ExtractedProblem(
        domain=DomainClassification(domain="ode_first_order", confidence=1.0, reasoning="y' = y ODE"),
        variables=[
            MathVariable(symbol="y(t)", description="Function of time", assumptions=["real"]),
            MathVariable(symbol="t", description="Time", assumptions=["real"]),
        ],
        equations=[
            MathEquation(expression="Derivative(y(t), t) = y(t)", description="ODE y' = y")
        ],
        givens={},
        initial_conditions={"y(0)": 1.0},
        goal="y(t)"
    )
    
    solver = SymPySolver()
    result = solver.solve(problem)
    
    verifier = NumericalVerifier(tolerance=1e-6)
    payload = verifier.verify(problem, result)
    
    assert payload.status == "pass"
    assert payload.max_residual < 1e-6
    assert 'e^{t}' in payload.verified_expression
