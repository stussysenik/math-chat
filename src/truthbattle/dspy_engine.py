import os
import dspy
import asyncio

# Configure DSPy to use the OpenWebUI compatible LLM mapped to the `.env` variables
from truthbattle.glm import _base_config, SOCRATIC_TUTOR_SYSTEM_PROMPT

def configure_dspy():
    base_url, api_key, model_str = _base_config()
    if not base_url:
        return False
    # Use litellm standard initialization behind the scenes via DSPy LM
    try:
        from dspy import LM
        lm = LM(
            model=f"openai/{model_str}",
            api_base=f"{base_url}",
            api_key=api_key or "sk-local",
            temperature=0.15,
            max_tokens=2048
        )
        dspy.settings.configure(lm=lm)
        return True
    except Exception as e:
        print(f"Failed to configure DSPy: {e}")
        return False


class MathWordProblemExplanationSignature(dspy.Signature):
    """
    You are an elite Staff Principal Engineer and mathematical tutor.
    You will examine an extracted mathematical textbook example, probability question, or word problem.
    Since we cannot easily map this to a direct SymPy calculation right now, your job is to logically
    derive the answer step-by-step from first principles, just like Richard Feynman.
    """
    problem_text = dspy.InputField(desc="The extracted word problem, text, or textbook example to explain.")
    step_by_step_derivation = dspy.OutputField(desc="A rigorous, step-by-step derivation and explanation formatting in beautiful Markdown with LaTeX.")


class WordProblemExplainer(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predictor = dspy.Predict(MathWordProblemExplanationSignature)

    def forward(self, problem_text: str) -> str:
        res = self.predictor(problem_text=problem_text)
        return res.step_by_step_derivation


async def dspy_fallback_explain_async(problem_text: str) -> str | None:
    """
    Asynchronously invokes the DSPy word problem optimizer. 
    """
    has_dspy = configure_dspy()
    if not has_dspy:
        return None

    explainer = WordProblemExplainer()
    try:
        # Run synchronously in a thread so we don't block the FastAPI loop
        result = await asyncio.to_thread(explainer.forward, problem_text)
        return result
    except Exception as e:
        print(f"DSPy explainer failed: {e}")
        return None
