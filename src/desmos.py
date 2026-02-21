import sympy as sp
from typing import List, Dict, Any
from src.schema import ExtractedProblem, VerificationPayload

class DesmosAdapter:
    """
    Translates deterministically verified SymPy output into Desmos Calculator API payloads.
    Desmos natively supports LaTeX strings.
    """
    
    def generate_payload(self, problem: ExtractedProblem, sympy_result: dict, verification: VerificationPayload) -> Dict[str, Any]:
        if verification.status != "pass":
            return {"enabled": False, "reason": "Cannot graph unverified mathematical truth."}
            
        expressions = []
        
        # 1. Grab the solution equations
        sol = sympy_result.get("solution")
        if isinstance(sol, sp.Eq):
            # Form: y = f(x)
            latex_expr = f"{sp.latex(sol.lhs)} = {sp.latex(sol.rhs)}"
            expressions.append({"latex": latex_expr})
        elif isinstance(sol, dict):
            # Form: target = result
            for k, v in sol.items():
                latex_expr = f"{sp.latex(k)} = {sp.latex(v)}"
                expressions.append({"latex": latex_expr})
        elif isinstance(sol, list):
            # E.g. [19.6] for goal 'v'
            target = problem.goal
            if isinstance(sol[0], dict):
                for k, v in sol[0].items():
                    latex_expr = f"{sp.latex(k)} = {sp.latex(v)}"
                    expressions.append({"latex": latex_expr})
            else:
                latex_expr = f"{sp.latex(sp.Symbol(target.split('(')[0]))} = {sp.latex(sol[0])}"
                expressions.append({"latex": latex_expr})
                
        # 2. Add original physical givens to the graph context (optional, but helpful for visual sliders)
        for k, v in problem.givens.items():
            expressions.append({"latex": f"{sp.latex(sp.Symbol(k))} = {v}"})
            
        return {
            "enabled": True,
            "calculator_state": {
                "expressions": {"list": [{"id": str(i), "latex": expr["latex"]} for i, expr in enumerate(expressions)]}
            }
        }
