from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Core Problem Formulation (Vision -> LLM -> JSON)
# ---------------------------------------------------------------------------

class MathVariable(BaseModel):
    """Represents a symbolic variable in the problem (e.g., time 't', velocity 'v')."""
    symbol: str = Field(..., description="The standard mathematical symbol (e.g., 't', 'v_0', 'm_1')")
    description: str = Field(..., description="Human-readable description (e.g., 'initial velocity')")
    unit: Optional[str] = Field(None, description="SI unit if explicitly stated or inferred (e.g., 'm/s')")
    assumptions: List[str] = Field(default_factory=list, description="SymPy assumptions (e.g., 'positive', 'real')")

class MathEquation(BaseModel):
    """Represents an extracted formula, ODE, or physical law."""
    expression: str = Field(..., description="The mathematical expression in a SymPy-parsable format (e.g., 'R*i(t) + v = 0')")
    condition: Optional[str] = Field(None, description="When this equation holds (e.g., 't > 0')")
    description: str = Field(..., description="What this equation describes (e.g., 'Coulomb friction law')")

class DomainClassification(BaseModel):
    """Categorizes the problem to route it to the correct SymPy/SciPy solver engine."""
    domain: Literal["kinematics", "ode_first_order", "laplace_transform", "probability_discrete", "algebra", "geometry"] = Field(
        ..., description="The strict domain category"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this classification")
    reasoning: str = Field(..., description="Why this domain was chosen")

class ExtractedProblem(BaseModel):
    """The absolute root payload the LLM must generate from the raw image/text."""
    domain: DomainClassification
    variables: List[MathVariable] = Field(..., description="All symbolic variables involved")
    equations: List[MathEquation] = Field(..., description="General laws or system ODEs")
    givens: Dict[str, float] = Field(
        ..., description="Known numerical parameters mapped to their symbols (e.g., {'m_1': 10.0, 'k_1': 20.0})"
    )
    initial_conditions: Dict[str, float] = Field(
        default_factory=dict, description="Initial values for ODEs/Laplace (e.g., {'y(0)': 0, 'y''(0)': 1})"
    )
    goal: str = Field(..., description="The symbol or expression we are trying to solve for (e.g., 'v(t)' or 'y_1(t)')")

# ---------------------------------------------------------------------------
# Server-Sent Events (SSE) Streaming Contracts
# ---------------------------------------------------------------------------

class SSEEvent(BaseModel):
    """Base payload for real-time pedagogical streaming."""
    event: Literal["extraction", "sympy_solve", "numerical_verify", "desmos_graph", "socratic_dialogue", "error", "complete"]
    data: Dict[str, Any]
    message: str = Field(..., description="A user-facing status message")

class VerificationPayload(BaseModel):
    """Used in the SSE stream once the numerical verifier runs."""
    status: Literal["pass", "fail", "numerical_instability"]
    max_residual: Optional[float] = None
    tolerance_used: float
    verified_expression: Optional[str] = None

class SocraticUIBlock(BaseModel):
    """
    The strict JSON structured output for the Socratic Mathematical Explainer.
    Maps directly to OpenWebUI ID-Message components.
    """
    lean_validation: str = Field(..., description="String describing LEAN verification success.")
    sympy_terminal: str = Field(..., description="Exact equations that SymPy solved.")
    feynman_explanation: str = Field(..., description="The highly structural Reverse Origami conceptual breakdown in Markdown.")
    dev_telemetry: Optional[str] = Field(None, description="Optional raw JSON/string dump of maximum residuals and SymPy boundaries.")
