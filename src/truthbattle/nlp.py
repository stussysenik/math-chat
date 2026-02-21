from __future__ import annotations

import re
from typing import Any

from truthbattle.glm import glm_extract_task, glm_repair_task
from truthbattle.types import TaskSpec

_WORD_VAR = re.compile(r"\bfor\s+([a-zA-Z]\w*)\b", re.IGNORECASE)
_NUM_ASSUMPTION = re.compile(r"\b([a-zA-Z]\w*)\s*(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)\b")
_ODE_IC_PATTERN = re.compile(
    r"y\s*\(\s*([^)]+?)\s*\)\s*=\s*(.+?)(?=(?:,\s*y\s*\(|\band\s+y\s*\(|;|\.|\n|$))",
    re.IGNORECASE,
)
_VALUE_SPLIT_RE = re.compile(r"\s*,\s*|\s+or\s+", re.IGNORECASE)


def _clean_math(text: str) -> str:
    return text.replace("^", "**").replace("−", "-").strip()


def _infer_variable(text: str, default: str = "x") -> str:
    m = _WORD_VAR.search(text)
    if m:
        return m.group(1)
    for c in "xyzabc":
        if re.search(rf"\b{c}\b", text):
            return c
    return default


def _extract_equation_candidate(text: str) -> str:
    candidates: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = raw.strip().strip(".,;:")
        if "=" not in line:
            continue
        math_tokens = len(re.findall(r"[=+\-*/^()]", line))
        digits = len(re.findall(r"\d", line))
        long_words = len(re.findall(r"[A-Za-z]{5,}", line))
        score = 3 * math_tokens + digits - long_words
        candidates.append((score, line))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return text.strip()


def _strip_leading_label(s: str) -> str:
    out = s.strip()
    out = re.sub(r"^\(?\d+[a-z]?\)?[.)]?\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"^\(?[a-z]\)?[.)]?\s*", "", out, flags=re.IGNORECASE)
    return out.strip()


def _iter_ode_candidates(text: str) -> list[str]:
    q = text.strip()
    if not q:
        return []
    lines = [_strip_leading_label(x) for x in q.splitlines() if x.strip()]
    sentences = [
        _strip_leading_label(x)
        for x in re.split(r"[.;]\s+", q)
        if x.strip() and "=" in x
    ]
    scored: list[tuple[int, str]] = []
    for line in lines + sentences:
        low = line.lower()
        score = 0
        if "=" in line:
            score += 2
        if "dy" in low:
            score += 4
        if "dx" in low or "/dx" in low or "d/d" in low:
            score += 3
        if "y'" in low or "derivative(" in low:
            score += 3
        if " y " in f" {low} ":
            score += 1
        if " x " in f" {low} ":
            score += 1
        if score > 0:
            scored.append((score, line))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[str] = []
    seen: set[str] = set()
    for _, cand in scored:
        c = " ".join(cand.split())
        if c and c not in seen:
            seen.add(c)
            out.append(c)

    fallback = _extract_equation_candidate(q)
    if fallback and fallback not in seen:
        out.append(fallback)
    compact = " ".join(q.split())
    if compact and compact not in seen:
        out.append(compact)
    return out


def _normalize_ode_rhs(rhs: str, indep: str, dep: str = "y") -> str:
    s = _clean_math(rhs)
    s = re.sub(r"[+\-*/\s]+$", "", s)  # strip trailing dangling operators
    s = re.sub(rf"\b{re.escape(dep)}\b", f"{dep}({indep})", s)
    s = re.sub(r"\bsin\s+([a-zA-Z]\w*)\b", r"sin(\1)", s)
    s = re.sub(r"\bcos\s+([a-zA-Z]\w*)\b", r"cos(\1)", s)
    s = re.sub(r"\btan\s+([a-zA-Z]\w*)\b", r"tan(\1)", s)
    s = re.sub(r"(?<=[0-9\)])(?=[a-zA-Z(])", "*", s)
    s = re.sub(r"(?<=\bpi)(?=[a-zA-Z(])", "*", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _expand_plus_minus(value: str) -> list[str]:
    token = value.strip().replace("−", "-")
    token = re.sub(r"\s+", "", token)
    if not token:
        return []

    prefixes = ("±", "+-", "+/-")
    for prefix in prefixes:
        if token.startswith(prefix):
            core = token[len(prefix) :].lstrip("+").lstrip("-")
            if not core:
                return []
            return [core, f"-{core}"]
    return [token]


def _clean_condition_token(token: str) -> str:
    out = token.strip()
    out = re.sub(r"(?i)\(.*?figure.*?\)", "", out)
    out = re.sub(r"(?i)\bsee\b.*$", "", out)
    out = out.strip().strip(".,;:()[]{}")
    return out


def _is_valid_condition_value(token: str) -> bool:
    if not token:
        return False
    if "=" in token:
        return False
    if not re.fullmatch(r"[A-Za-z0-9_+\-*/().^\s]+", token):
        return False
    lowered = token.lower()
    if (
        re.search(r"[a-z]{4,}", lowered)
        and "sqrt" not in lowered
        and "pi" not in lowered
    ):
        return False
    return True


def _extract_ode_initial_conditions(text: str) -> list[str]:
    q = text.replace("−", "-")
    matches = list(_ODE_IC_PATTERN.finditer(q))
    if not matches:
        return []

    conditions: list[str] = []
    for m in matches:
        x0 = _clean_math(m.group(1))
        rhs_blob = m.group(2)
        for raw_token in _VALUE_SPLIT_RE.split(rhs_blob):
            token = _clean_condition_token(raw_token)
            if not token:
                continue
            expanded = _expand_plus_minus(token)
            for val in expanded:
                cleaned_val = _clean_condition_token(val)
                if not _is_valid_condition_value(cleaned_val):
                    continue
                conditions.append(f"y({x0}) = {_clean_math(cleaned_val)}")

    deduped: list[str] = []
    seen: set[str] = set()
    for cond in conditions:
        key = cond.replace(" ", "")
        if key not in seen:
            seen.add(key)
            deduped.append(cond)
    return deduped


def _parse_ode(text: str) -> TaskSpec | None:
    q = text.strip()
    if not q:
        return None
    ic_assumptions = _extract_ode_initial_conditions(q)
    for cand in _iter_ode_candidates(q):
        compact = " ".join(cand.split())
        m_div = re.search(
            r"\bd\s*y\s*/\s*d\s*([a-zA-Z]\w*)\s*=\s*(.+)$",
            compact,
            re.IGNORECASE,
        )
        if m_div:
            indep = m_div.group(1)
            rhs = _normalize_ode_rhs(m_div.group(2), indep)
            expr = f"Derivative(y({indep}), {indep}) - ({rhs})"
            return TaskSpec(
                "ode",
                expression=expr,
                variable=indep,
                domain=_infer_domain(q),
                assumptions=ic_assumptions,
                reasoning="heuristic_ode_division",
            )

        m_prime = re.search(r"\by'\s*=\s*(.+)$", compact)
        if m_prime:
            indep = "x"
            rhs = _normalize_ode_rhs(m_prime.group(1), indep)
            expr = f"Derivative(y({indep}), {indep}) - ({rhs})"
            return TaskSpec(
                "ode",
                expression=expr,
                variable=indep,
                domain=_infer_domain(q),
                assumptions=ic_assumptions,
                reasoning="heuristic_ode_prime",
            )

        m_diff_form = re.search(
            r"\bd\s*y\s*([+-])\s*(.+?)\s*\*?\s*d\s*([a-zA-Z]\w*)\s*=\s*0\b",
            compact,
            re.IGNORECASE,
        )
        if m_diff_form:
            sign = m_diff_form.group(1)
            rhs_raw = m_diff_form.group(2)
            indep = m_diff_form.group(3)
            rhs = _normalize_ode_rhs(rhs_raw, indep)
            op = "-" if sign == "-" else "+"
            expr = f"Derivative(y({indep}), {indep}) {op} ({rhs})"
            return TaskSpec(
                "ode",
                expression=expr,
                variable=indep,
                domain=_infer_domain(q),
                assumptions=ic_assumptions,
                reasoning="heuristic_ode_diff_form",
            )
    return None


def _looks_symbolic_equation(s: str) -> bool:
    if "=" not in s:
        return False
    text = s.strip()
    if not text:
        return False
    ops = len(re.findall(r"[=+\-*/^()]", text))
    digits = len(re.findall(r"\d", text))
    words = len(re.findall(r"[A-Za-z]{4,}", text))
    if ops >= 2 and words <= 18:
        return True
    if digits >= 1 and ops >= 1 and words <= 20:
        return True
    return False


def _infer_domain(text: str) -> str:
    low = text.lower()
    if "over reals" in low or "in reals" in low or "real numbers" in low:
        return "real"
    if "over complex" in low or "in complex" in low or "complex numbers" in low:
        return "complex"
    if "over integers" in low or "in integers" in low or "integer" in low:
        return "integer"
    if "natural numbers" in low or "over naturals" in low:
        return "natural"
    return "unspecified"


def _infer_assumptions(text: str, variable: str) -> list[str]:
    assumptions: list[str] = []
    for var, op, value in _NUM_ASSUMPTION.findall(text):
        if var.lower() == variable.lower():
            assumptions.append(f"{variable} {op} {value}")

    low = text.lower()
    if re.search(rf"\b{re.escape(variable)}\b.*\bnonnegative\b", low):
        assumptions.append(f"{variable} >= 0")
    if re.search(rf"\b{re.escape(variable)}\b.*\bpositive\b", low):
        assumptions.append(f"{variable} > 0")

    deduped: list[str] = []
    seen = set()
    for a in assumptions:
        if a not in seen:
            deduped.append(a)
            seen.add(a)
    return deduped


def _heuristic_parse(question: str) -> TaskSpec:
    q = question.strip()
    low = q.lower()
    variable = _infer_variable(q)
    domain = _infer_domain(q)
    assumptions = _infer_assumptions(q, variable)

    if ("integrate" in low or "integral" in low) and "=" not in q:
        expr = re.sub(r"(?i)^.*?(integrate|integral of)\s*", "", q).strip()
        expr = re.sub(r"(?i)\s*d\s*[a-zA-Z]\w*\s*$", "", expr).strip()
        return TaskSpec(
            "integrate",
            expression=_clean_math(expr),
            variable=variable,
            domain=domain,
            assumptions=assumptions,
            reasoning="heuristic",
        )

    if (
        "differentiate" in low
        or "derivative" in low
        or re.search(r"d\s*/\s*d[a-zA-Z]", low)
    ):
        expr = re.sub(r"(?i)^.*?(differentiate|derivative of)\s*", "", q).strip()
        expr = re.sub(r"(?i)^d\s*/\s*d[a-zA-Z]\s*", "", expr).strip()
        return TaskSpec(
            "differentiate",
            expression=_clean_math(expr),
            variable=variable,
            domain=domain,
            assumptions=assumptions,
            reasoning="heuristic",
        )

    if "simplify" in low:
        expr = re.sub(r"(?i)^.*?simplify\s*", "", q).strip()
        return TaskSpec(
            "simplify",
            expression=_clean_math(expr),
            variable=variable,
            domain=domain,
            assumptions=assumptions,
            reasoning="heuristic",
        )

    ode = _parse_ode(q)
    if ode:
        return ode

    if "=" in q or "solve" in low or "find" in low:
        eq_text = re.sub(r"(?i)^\s*(solve|find|compute)\s*", "", q).strip()
        eq_text = _extract_equation_candidate(eq_text)
        eq_text = re.sub(r"(?i)\s+for\s+[a-zA-Z]\w*.*$", "", eq_text).strip()
        if _looks_symbolic_equation(eq_text):
            lhs, rhs = eq_text.split("=", 1)
            return TaskSpec(
                "solve",
                lhs=_clean_math(lhs),
                rhs=_clean_math(rhs),
                variable=variable,
                domain=domain,
                assumptions=assumptions,
                reasoning="heuristic",
            )

    return TaskSpec(
        "explain",
        expression=q,
        variable=variable,
        domain=domain,
        assumptions=assumptions,
        reasoning="fallback",
    )


def _coerce_task(data: dict[str, Any]) -> TaskSpec | None:
    task = str(data.get("task_type", "")).strip().lower()
    if task not in {
        "solve",
        "simplify",
        "differentiate",
        "integrate",
        "ode",
        "explain",
    }:
        return None
    return TaskSpec(
        task_type=task,  # type: ignore[arg-type]
        expression=_clean_math(str(data.get("expression", "")).strip()),
        lhs=_clean_math(str(data.get("lhs", "")).strip()),
        rhs=_clean_math(str(data.get("rhs", "")).strip()),
        variable=str(data.get("variable", "x") or "x").strip(),
        domain=str(data.get("domain", "unspecified") or "unspecified").strip(),
        assumptions=[str(x) for x in data.get("assumptions", []) if str(x).strip()],
        reasoning=str(data.get("reasoning", "glm")).strip() or "glm",
    )


def _task_ready(task: TaskSpec) -> bool:
    if task.task_type == "solve":
        return bool(task.lhs and task.rhs)
    if task.task_type in {"simplify", "differentiate", "integrate", "ode"}:
        return bool(task.expression)
    return False


async def repair_task(
    question: str,
    previous_task: TaskSpec,
    sympy_error: str,
) -> TaskSpec | None:
    data = await glm_repair_task(question, previous_task.__dict__, sympy_error)
    if not data:
        return None
    task = _coerce_task(data)
    if not task:
        return None
    if task.task_type == "explain":
        return None
    if not _task_ready(task):
        return None
    return task


async def parse_task(question: str) -> TaskSpec:
    heuristic = _heuristic_parse(question)
    if heuristic.task_type != "explain":
        return heuristic

    glm_data = await glm_extract_task(question)
    if glm_data:
        task = _coerce_task(glm_data)
        if task:
            if task.task_type == "solve" and (not task.lhs or not task.rhs):
                fallback = _heuristic_parse(question)
                if fallback.task_type == "solve":
                    return fallback
            if task.task_type != "solve" and not task.expression:
                return _heuristic_parse(question)
            if task.task_type == "explain":
                repaired = await repair_task(
                    question,
                    task,
                    "Parser returned explain; attempt symbolic reduction if data is sufficient.",
                )
                if repaired:
                    return repaired
            return task
    if heuristic.task_type == "explain":
        repaired = await repair_task(
            question,
            heuristic,
            "Heuristic parser returned explain; attempt symbolic reduction if data is sufficient.",
        )
        if repaired:
            return repaired
    return heuristic
