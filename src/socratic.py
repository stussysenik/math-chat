import dspy
from src.schema import ExtractedProblem, VerificationPayload, SocraticUIBlock

class SocraticExplainerSignature(dspy.Signature):
    """
    You are a Staff Principal Engineer and Elite Socratic Math Tutor.
    Your objective is to explain the physical and mathematical concepts driving the solution
    in the style of Richard Feynman. You will NEVER guess the math or invent numbers.
    You MUST rely strictly on the verified mathematical truth provided.
    
    THE REVERSE ORIGAMI METHOD: You now possess the absolute mathematical truth. 
    Your job is to fold the origami piece backwards. Start from the verified goal, 
    and break down the atomic instructions step-by-step using first principles. 
    Keep it concise, punchy, and deeply rigorous.
    """
    
    goal_variable: str = dspy.InputField(desc="The symbol we are trying to solve for.")
    known_parameters: str = dspy.InputField(desc="Given parameters mapped to their symbols.")
    core_physical_equations: str = dspy.InputField(desc="The extracted physical/mathematical equations.")
    verified_symbolic_solution: str = dspy.InputField(desc="The absolute verified final result output by the deterministic solver.")
    dev_telemetry_payload: str = dspy.InputField(desc="Raw telemetry boundaries from the verifier.")
    
    structured_explanation: SocraticUIBlock = dspy.OutputField()

class SocraticExplainer(dspy.Module):
    """
    A compiled DSPy Module that executes the Reverse Origami pedagogy 
    and yields native OpenWebUI ID-Message structured outputs.
    """
    def __init__(self):
        super().__init__()
        self.predictor = dspy.TypedPredictor(SocraticExplainerSignature)
        
    def forward(self, problem: ExtractedProblem, sympy_result: dict, verification: VerificationPayload, dev_mode: bool = False) -> SocraticUIBlock:
        if verification.status != "pass":
            return SocraticUIBlock(
                lean_validation="SYSTEM INSTRUCTION: Numerical verification failed.",
                sympy_terminal="",
                feynman_explanation="The mathematical translation was unstable or incorrect. Apologize briefly to the student.",
                dev_telemetry=None
            )
            
        # Build the formal context
        givens_str = ", ".join([f"{k} = {v}" for k, v in problem.givens.items()])
        equations_str = "\n".join([f"- {eq.expression} ({eq.description})" for eq in problem.equations])
        
        dev_telemetry = ""
        if dev_mode:
            dev_telemetry = f"Max Residual: {verification.max_residual}, Tolerance: {verification.tolerance_used}, SymPy Nodes: {str(sympy_result.get('parsed_eqs', []))}"
            
        # Execute the compiled DSPy chain
        result = self.predictor(
            goal_variable=problem.goal,
            known_parameters=givens_str,
            core_physical_equations=equations_str,
            verified_symbolic_solution=str(verification.verified_expression), 
            dev_telemetry_payload=dev_telemetry
        )
        
        return result.structured_explanation
