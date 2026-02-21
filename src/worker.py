import os
from celery import Celery
from src.schema import ExtractedProblem
from src.solver import SymPySolver
from src.verifier import NumericalVerifier
from src.desmos import DesmosAdapter
from src.socratic import SocraticExplainer

# Initialize Celery with Redis broker and backend
celery_app = Celery(
    'math_worker',
    broker=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
)

@celery_app.task(bind=True)
def execute_deterministic_pipeline(self, extracted_problem_dict: dict, dev_mode: bool = False) -> dict:
    """
    Background worker that executes the entire LEAN-verified deterministic pipeline.
    This frees the HTTP loop from hanging during deep SymPy/Wolfram combinations.
    """
    problem = ExtractedProblem(**extracted_problem_dict)
    
    solver = SymPySolver()
    verifier = NumericalVerifier()
    socratic = SocraticExplainer() # DSPy compiled module
    
    # 1. SymPy / Wolfram Solve
    sympy_result = solver.solve(problem)
    if "solution" not in sympy_result or sympy_result["solution"] is None:
        return {"error": "Deterministic solvers failed to resolve the algebraic constraints natively."}
        
    # 2. LEAN-Lite Numerical Verification
    verification = verifier.verify(problem, sympy_result)
    
    # 3. Compile Socratic Reverse-Origami via DSPy
    # Yields a strict SocraticUIBlock Pydantic object designed for OpenWebUI ID-Messages
    socratic_ui_block = socratic.forward(problem, sympy_result, verification, dev_mode)
    
    return socratic_ui_block.model_dump()
