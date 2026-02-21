import pytest
from pydantic import ValidationError
from src.schema import ExtractedProblem, MathVariable, MathEquation, DomainClassification

def test_valid_extracted_problem_laplace():
    payload = {
        "domain": {
            "domain": "laplace_transform",
            "confidence": 0.98,
            "reasoning": "The problem asks for RC-circuit current using Laplace."
        },
        "variables": [
            {"symbol": "R", "description": "Resistance", "unit": "Ohms"},
            {"symbol": "C", "description": "Capacitance", "unit": "Farads"},
            {"symbol": "i(t)", "description": "Current"},
            {"symbol": "v(t)", "description": "Voltage"}
        ],
        "equations": [
            {
                "expression": "R * i(t) + 1/C * Integral(i(tau), (tau, 0, t)) = v(t)",
                "description": "Kirchhoff's Voltage Law"
            }
        ],
        "givens": {
            "R": 10.0,
            "C": 0.1
        },
        "initial_conditions": {
            "q(0)": 0.0
        },
        "goal": "i(t)"
    }
    
    # Should validate and parse successfully
    problem = ExtractedProblem(**payload)
    assert problem.domain.domain == "laplace_transform"
    assert len(problem.variables) == 4
    assert problem.givens["R"] == 10.0

def test_invalid_domain_classification():
    with pytest.raises(ValidationError):
        DomainClassification(
            domain="astrophysics", # Invalid domain
            confidence=0.9,
            reasoning="Testing invalid"
        )
