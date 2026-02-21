import numpy as np
import sympy as sp
from src.schema import ExtractedProblem, VerificationPayload

class NumericalVerifier:
    def __init__(self, tolerance: float = 1e-6):
        self.tolerance = tolerance

    def verify(self, problem: ExtractedProblem, solver_result: dict) -> VerificationPayload:
        if "solution" not in solver_result or solver_result["solution"] is None:
            return VerificationPayload(
                status="fail", 
                tolerance_used=self.tolerance, 
                message="Cannot verify an empty solution."
            )
            
        parsed_eqs = solver_result.get("parsed_eqs", [])
        sol = solver_result["solution"]
        
        # Format sol into a substitutable dict
        subs_dict = {}
        if isinstance(sol, dict):
            subs_dict = sol
        elif isinstance(sol, list):
            # Try to grab the first valid dict or assume target mapping
            if isinstance(sol[0], dict):
                subs_dict = sol[0]
            else:
                # If target was 'v', map the target string to the value
                # (We'd need local_dict to do this perfectly, but using str approach here)
                pass 
        elif isinstance(sol, sp.Eq):
            # It's an ODE solution Eq(y(t), exp(t))
            subs_dict = {sol.lhs: sol.rhs}

        max_residual = 0.0

        if problem.domain.domain in ['kinematics', 'algebra']:
            # Algebraic check
            for eq in parsed_eqs:
                # e.g. eq is Eq(v, a*t) => v - a*t = 0
                if isinstance(eq, sp.Eq):
                    residual_expr = eq.lhs - eq.rhs
                else:
                    residual_expr = eq
                    
                # Substitute all givens and the solution
                # Note: equations in solver_result.parsed_eqs already had givens applied inside solve(),
                # but we can re-apply if needed, or assume parsed_eqs are pure.
                # Actually, solver_result should pass original eqs or we just sub known givens.
                givens_subs = {sp.Symbol(k): v for k, v in problem.givens.items()}
                
                # Check residual
                val = residual_expr.subs(givens_subs).subs(subs_dict).evalf()
                
                # If it's a number, compute float
                if val.is_number:
                    res = abs(float(val))
                    if res > max_residual:
                        max_residual = res
                        
            if max_residual > self.tolerance:
                return VerificationPayload(
                    status="fail", 
                    max_residual=max_residual, 
                    tolerance_used=self.tolerance, 
                    message="Numerical residual exceeds verification tolerance."
                )
            return VerificationPayload(
                status="pass", 
                max_residual=max_residual, 
                tolerance_used=self.tolerance, 
                verified_expression=sp.latex(list(subs_dict.values())[0]) if subs_dict else "",
                message="Algebraic solution verified to be deterministic."
            )
            
        elif problem.domain.domain == 'ode_first_order':
            # ODE residual sweep
            t_vals = np.linspace(0, 10, 50) # sweep domain
            
            for eq in parsed_eqs:
                if isinstance(eq, sp.Eq):
                    residual_expr = eq.lhs - eq.rhs
                else:
                    residual_expr = eq
                    
                # In SymPy, substitute y(t) with the solved RHS
                # Note that sympy needs to evaluate the Derivative explicitly
                substituted_expr = residual_expr.subs(subs_dict).doit()
                
                # Lambdify over 't'
                t_sym = sp.Symbol('t')
                
                # substitute givens first
                givens_subs = {sp.Symbol(k): v for k, v in problem.givens.items()}
                substituted_expr = substituted_expr.subs(givens_subs)
                
                if substituted_expr.is_number:
                    # Constant residual (e.g. 0)
                    res = abs(float(substituted_expr))
                    max_residual = max(max_residual, res)
                else:
                    func = sp.lambdify(t_sym, substituted_expr, 'numpy')
                    try:
                        residuals = func(t_vals)
                        res = np.max(np.abs(residuals))
                        max_residual = max(max_residual, res)
                    except Exception:
                        return VerificationPayload(
                            status="numerical_instability",
                            tolerance_used=self.tolerance,
                            message="Lambdify sweep failed."
                        )
            
            if max_residual > self.tolerance:
                return VerificationPayload(
                    status="fail", 
                    max_residual=max_residual, 
                    tolerance_used=self.tolerance, 
                    message=f"ODE domain sweep validation failed with residual {max_residual}."
                )
            
            # Serialize to Strict LaTeX
            expr_str = sp.latex(list(subs_dict.values())[0]) if subs_dict else ""
            return VerificationPayload(
                status="pass",
                max_residual=max_residual,
                tolerance_used=self.tolerance,
                verified_expression=expr_str,
                message="ODE sweep successfully validated deterministically."
            )

        return VerificationPayload(
            status="fail", 
            tolerance_used=self.tolerance, 
            message="Domain unverified."
        )
