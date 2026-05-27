"""LLM client for question generation.

Priority:
  1. Anthropic (Claude) — if ANTHROPIC_API_KEY is set
  2. Local LM Studio / Ollama — OpenAI-compatible /v1/chat/completions fallback
"""
from __future__ import annotations

import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a JSON API. You output ONLY valid JSON arrays. "
    "No explanation, no markdown, no extra text — just the JSON array."
)


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------

async def generate_questions(
    prompt: str,
    ollama_url: str,
    ollama_model: str,
    anthropic_api_key: str = "",
    anthropic_model: str = "claude-haiku-4-5-20251001",
    timeout: float = 120.0,
) -> tuple[list[dict], str]:
    """Generate questions, preferring Anthropic if an API key is configured.

    Returns (questions, source) where source is 'anthropic' or 'local'.
    """
    if anthropic_api_key:
        logger.info("Using Anthropic  model=%s", anthropic_model)
        try:
            questions = await _generate_anthropic(prompt, anthropic_api_key, anthropic_model)
            return questions, "anthropic"
        except Exception as exc:
            logger.warning("Anthropic failed (%s), falling back to local LLM", exc)

    logger.info("Using local LLM  url=%s  model=%s", ollama_url, ollama_model)
    questions = await _generate_local(prompt, ollama_url, ollama_model, timeout)
    return questions, "local"


# ------------------------------------------------------------------
# Anthropic backend
# ------------------------------------------------------------------

async def _generate_anthropic(prompt: str, api_key: str, model: str) -> list[dict]:
    try:
        import anthropic as _anthropic
    except ImportError as e:
        raise RuntimeError("anthropic package not installed — run pip install anthropic") from e

    client = _anthropic.AsyncAnthropic(api_key=api_key)
    msg = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text
    logger.info("Anthropic response: %d chars — %s", len(text), repr(text[:120]))
    return _parse_json_questions(text)


# ------------------------------------------------------------------
# Local LM Studio / Ollama backend  (OpenAI-compatible)
# ------------------------------------------------------------------

async def _generate_local(
    prompt: str,
    ollama_url: str,
    model: str,
    timeout: float = 120.0,
) -> list[dict]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{ollama_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                "stream": False,
                "max_tokens": 2048,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))

    text = data["choices"][0]["message"]["content"]
    logger.info("Local LLM response: %d chars — %s", len(text), repr(text[:120]))
    return _parse_json_questions(text)


async def list_models(ollama_url: str) -> list[str]:
    """Return model IDs available on the local server."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{ollama_url}/v1/models")
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", [])]


# ------------------------------------------------------------------
# JSON parsing (shared, robust against truncation)
# ------------------------------------------------------------------

def _parse_json_questions(text: str) -> list[dict]:
    # Strip thinking blocks (Qwen3 / DeepSeek-R1) and markdown fences
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"^```[a-z]*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```$", "", text, flags=re.MULTILINE).strip()

    # Try 1: full well-formed JSON array
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                logger.info("Parsed %d questions (full array)", len(data))
                return data
        except json.JSONDecodeError:
            pass

    # Try 2: recover individual objects from a truncated array
    objects = _extract_objects(text)
    if objects:
        logger.warning("Full array parse failed; recovered %d objects individually", len(objects))
        return objects

    raise ValueError("LLM returned no parseable JSON")


def _extract_objects(text: str) -> list[dict]:
    """Walk char-by-char extracting every complete balanced {...} block."""
    results = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != '{':
            i += 1
            continue
        depth, in_str, escaped = 0, False, False
        j = i
        while j < n:
            ch = text[j]
            if escaped:
                escaped = False
            elif ch == '\\' and in_str:
                escaped = True
            elif ch == '"':
                in_str = not in_str
            elif not in_str:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(text[i: j + 1])
                            if isinstance(obj, dict):
                                results.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
            j += 1
        else:
            break
    return results


# ------------------------------------------------------------------
# Prompt builder
# ------------------------------------------------------------------

def build_generation_prompt(
    stats_pct: int,
    weak_cats: list[str],
    recent_mistakes: list[dict],
    available_cats: list[str],
    example_questions: list[dict],
    rejected_questions: list[dict] | None = None,
    total_answered: int = 0,
    total_correct: int = 0,
    by_category: dict | None = None,
) -> str:
    mistakes_text = "".join(
        f"  - [{m.get('difficulty', '')}|{m.get('cat', '')}] {m.get('q', '')[:80]}\n"
        for m in recent_mistakes[:3]
    ) or "  (none yet)\n"

    weak_str = ", ".join(weak_cats) if weak_cats else "none identified"
    cats_str = ", ".join(available_cats)
    good_json = json.dumps(example_questions, ensure_ascii=False, indent=2)

    # Category breakdown table
    cat_lines = ""
    if by_category:
        rows = sorted(by_category.items(), key=lambda x: x[1][1], reverse=True)
        for cat, (correct, total) in rows:
            pct = round(100 * correct / total) if total else 0
            flag = " ← weak" if cat in weak_cats else ""
            cat_lines += f"  {cat:<30} {correct}/{total} ({pct}%){flag}\n"
    cat_section = f"\nCategory breakdown:\n{cat_lines}" if cat_lines else ""

    bad_section = ""
    if rejected_questions:
        bad_json = json.dumps(rejected_questions, ensure_ascii=False, indent=2)
        bad_section = (
            "\nThe following questions were previously REJECTED as low-quality. "
            "Do NOT repeat these patterns — avoid ambiguous questions, wrong answers, "
            "incomplete German, or nonsensical distractors:\n\n"
            + bad_json + "\n"
        )

    return f"""You are creating German language exam questions for a specific student. Use the performance data below to generate questions that target their weaknesses.

===STUDENT PERFORMANCE===
Total answered: {total_answered}  |  Correct: {total_correct}  |  Overall accuracy: {stats_pct}%
Weak areas (accuracy < 60%): {weak_str}
{cat_section}
3 most recent mistakes (most relevant targets):
{mistakes_text}
===GOOD EXAMPLES (from the real question bank — copy this quality exactly)===

{good_json}
{bad_section}
===YOUR TASK===
Generate 5 NEW questions. Do NOT copy or paraphrase the examples above.
Prioritise the student's weak categories and question types similar to their recent mistakes.

CORRECTNESS IS MANDATORY — every question will be shown to a learner as fact:
1. German grammar must be 100% correct. Every article (der/die/das/ein), case ending, verb form, and word order must be standard written German.
2. The correct answer must be definitively and unambiguously right — no edge cases, no dialects, no register variation.
3. Wrong options (distractors) must be grammatically plausible but clearly wrong for a specific, explainable reason.
4. The sentence or phrase must be semantically complete and natural — not a fragment, not nonsense.
5. If the question uses a blank (___), the blank must be the ONLY thing that changes; the rest of the sentence must be correct as-is.
6. The explanation must state WHY the correct answer is right and briefly why the others are wrong.

FORMAT RULES:
- "cat" must be one of: {cats_str}
- "difficulty": A1 (basic), A2 (elementary), B1 (intermediate), B2 (upper-intermediate)
- "opts": exactly 4 strings
- "answer": integer 0–3 (index of correct option)
- "explanation": 1–2 sentences in English

Output ONLY the JSON array, nothing else."""
