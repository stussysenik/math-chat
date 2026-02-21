import sympy as sp
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
from src.schema import ExtractedProblem

class SymPySolver:
    """
    Sandboxed execution layer that translates standardized ASTs into definitive
    symbolic results using SymPy.
    """
    def __init__(self):
        # Enable implicit multiplication (e.g., "2x" -> "2*x")
        self.transformations = (standard_transformations + (implicit_multiplication_application,))
        
    def _parse_equation(self, eq_str: str, local_dict: dict):
        import re
        # Pre-process Laplace notation L{...} to LaplaceTransform(...) function call
        eq_str = re.sub(r'L\{([^}]+)\}', r'LaplaceTransform(\1)', eq_str)
        
        if '=' in eq_str:
            lhs_str, rhs_str = eq_str.split('=', 1)
            lhs = parse_expr(lhs_str.strip(), local_dict=local_dict, transformations=self.transformations)
            rhs = parse_expr(rhs_str.strip(), local_dict=local_dict, transformations=self.transformations)
            return sp.Eq(lhs, rhs)
        else:
            return parse_expr(eq_str.strip(), local_dict=local_dict, transformations=self.transformations)

    def solve(self, problem: ExtractedProblem) -> dict:
        local_dict = {}
        
        # 1. Register variables and domains
        for var in problem.variables:
            name = var.symbol.split('(')[0]
            if '(' in var.symbol:
                local_dict[name] = sp.Function(name)
            else:
                kwargs = {assump: True for assump in var.assumptions}
                local_dict[name] = sp.Symbol(name, **kwargs)
                
        # Inject standard physics/math variables if missing but implied
        if 't' not in local_dict:
            local_dict['t'] = sp.Symbol('t', real=True)
        if 's' not in local_dict:
            local_dict['s'] = sp.Symbol('s', complex=True)
            
        local_dict['LaplaceTransform'] = sp.Function('LaplaceTransform')
        local_dict['u'] = sp.Function('u') # Heaviside step function which often pairs with Laplace
            
        # 2. Parse equations into SymPy nodes
        parsed_eqs = [self._parse_equation(eq.expression, local_dict) for eq in problem.equations]
        
        # 3. Substitute givens
        subs_dict = {}
        for k, v in problem.givens.items():
            if k in local_dict:
                subs_dict[local_dict[k]] = v
                
        subbed_eqs = [eq.subs(subs_dict) if hasattr(eq, 'subs') else eq for eq in parsed_eqs]
        
        # 4. Domain-specific solver routing
        if problem.domain.domain == 'ode_first_order':
            # Example heuristic for Initial Conditions (y(0) -> subs t=0)
            ics = {}
            for k, v in problem.initial_conditions.items():
                if '(0)' in k:
                    func_name = k.split('(')[0]
                    ics[local_dict[func_name](0)] = v
                
            target = self._parse_equation(problem.goal, local_dict)
            solution = sp.dsolve(subbed_eqs[0], target, ics=ics)
            return {"solution": solution, "parsed_eqs": parsed_eqs}
            
        elif problem.domain.domain in ['algebra', 'kinematics']:
            target = self._parse_equation(problem.goal, local_dict)
            solution = sp.solve(subbed_eqs, target)
            return {"solution": solution, "parsed_eqs": parsed_eqs}
            
        return {"solution": None, "error": f"Domain {problem.domain.domain} solver not implemented"}
