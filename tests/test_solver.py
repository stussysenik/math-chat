import pytest
import sympy as sp
from src.schema import ExtractedProblem, DomainClassification, MathVariable, MathEquation
from src.solver import SymPySolver

def test_algebraic_kinematics_solver():
    """Test solving a basic algebraic kinematics problem: v = v0 + a*t"""
    problem = ExtractedProblem(
        domain=DomainClassification(domain="kinematics", confidence=1.0, reasoning="test"),
        variables=[
            MathVariable(symbol="v", description="Final velocity", assumptions=["real"]),
            MathVariable(symbol="v0", description="Initial velocity", assumptions=["real"]),
            MathVariable(symbol="a", description="Acceleration", assumptions=["real"]),
            MathVariable(symbol="t", description="Time", assumptions=["positive", "real"]),
        ],
        equations=[
            MathEquation(expression="v = v0 + a*t", description="Kinematic equation")
        ],
        givens={"v0": 0.0, "a": 9.8, "t": 2.0},
        initial_conditions={},
        goal="v"
    )
    
    solver = SymPySolver()
    result = solver.solve(problem)
    
    assert "solution" in result
    assert result["solution"] is not None
    # Depending on sympy, sp.solve returns a list of dictionaries or a dict
    sol = result["solution"]
    if isinstance(sol, dict):
        val = list(sol.values())[0]
    elif isinstance(sol, list):
        val = sol[0] if not isinstance(sol[0], dict) else list(sol[0].values())[0]
    else:
        val = sol
        
    assert pytest.approx(float(val)) == 19.6

def test_ode_first_order_solver():
    """Test solving Section 1.2 Euler Method style problem: y' = y"""
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
    
    assert "solution" in result
    sol = result["solution"]
    # sp.dsolve returns Eq(y(t), exp(t))
    assert isinstance(sol, sp.Eq)
    assert 'exp(t)' in str(sol.rhs)

def test_laplace_parsing():
    """Test solving an extracted Laplace string like L{(t - 2)*u(t - 2)} = exp(-2*s)/s**2"""
    problem = ExtractedProblem(
        domain=DomainClassification(domain="algebra", confidence=1.0, reasoning="Verification of Laplace"),
        variables=[
            MathVariable(symbol="s", description="Frequency domain"),
            MathVariable(symbol="t", description="Time domain")
        ],
        equations=[
            MathEquation(expression="L{(t - 2)*u(t - 2)} = exp(-2*s)/s**2", description="Laplace Pair")
        ],
        givens={},
        initial_conditions={},
        goal="LaplaceTransform((t - 2)*u(t - 2))"
    )
    
    solver = SymPySolver()
    result = solver.solve(problem)
    
    assert "solution" in result
    sol = result["solution"]
    assert len(sol) > 0
    
    if isinstance(sol, dict):
        val = list(sol.values())[0]
    elif isinstance(sol, list):
        val = sol[0] if not isinstance(sol[0], dict) else list(sol[0].values())[0]
    else:
        val = sol
        
    # The solver algebra router should return the explicit RHS
    assert "exp(-2*s)/s**2" in str(val)

