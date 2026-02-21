import os
import wolframalpha

class WolframProver:
    """
    Secondary deterministic verification engine using Wolfram Alpha API.
    Used for proving deep limits, recursive sequence generating functions,
    and combinatorial problems where SymPy struggles to yield a native closed form.
    """
    def __init__(self):
        # Requires WOLFRAM_ALPHA_APPID in the environment
        app_id = os.environ.get('WOLFRAM_ALPHA_APPID', 'DEMO_KEY')
        self.client = wolframalpha.Client(app_id)
        
    def prove_sequence_limit(self, sequence_expr: str, limit_condition: str) -> dict:
        """
        Queries Wolfram Alpha to rigorously prove a sequence or generating function.
        E.g., sequence_expr="Limit[(1/sqrt(5))*(((1+sqrt(5))/2)^n - ((1-sqrt(5))/2)^n), n->infinity]"
        """
        query_string = f"prove {sequence_expr} {limit_condition}"
        try:
            res = self.client.query(query_string)
            
            # Extract the rigorous mathematical result from the pods
            for pod in res.pods:
                if pod.title in ['Result', 'Exact result', 'Limit']:
                    for sub in pod.subpods:
                        return {
                            "status": "pass",
                            "engine": "wolfram_alpha",
                            "verified_expression": sub.plaintext,
                            "raw_pods": [p.title for p in res.pods]
                        }
            
            return {
                "status": "fail",
                "engine": "wolfram_alpha",
                "reason": "Could not extract a definitive limit/result pod."
            }
            
        except Exception as e:
             return {
                "status": "error",
                "engine": "wolfram_alpha",
                "reason": str(e)
            }
