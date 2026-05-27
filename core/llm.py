"""LLM client for question generation and learning plan AI.

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

_SYSTEM_ARRAY = (
    "You are a JSON API. You output ONLY valid JSON arrays. "
    "No explanation, no markdown, no extra text — just the JSON array."
)
_SYSTEM_OBJECT = (
    "You are a JSON API. You output ONLY valid JSON objects. "
    "No explanation, no markdown, no extra text — just the JSON object."
)


# ------------------------------------------------------------------
# Internal raw LLM callers (return raw text string)
# ------------------------------------------------------------------

async def _call_anthropic_raw(
    prompt: str,
    api_key: str,
    model: str,
    system: str,
    max_tokens: int = 2048,
) -> str:
    try:
        import anthropic as _anthropic
    except ImportError as e:
        raise RuntimeError("anthropic package not installed — run pip install anthropic") from e

    client = _anthropic.AsyncAnthropic(api_key=api_key)
    msg = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text
    logger.info("Anthropic response: %d chars — %s", len(text), repr(text[:120]))
    return text


async def _call_local_raw(
    prompt: str,
    ollama_url: str,
    model: str,
    system: str,
    timeout: float = 120.0,
    max_tokens: int = 2048,
) -> str:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{ollama_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                "stream": False,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))

    text = data["choices"][0]["message"]["content"]
    logger.info("Local LLM response: %d chars — %s", len(text), repr(text[:120]))
    return text


# ------------------------------------------------------------------
# Public entry points
# ------------------------------------------------------------------

async def generate_questions(
    prompt: str,
    ollama_url: str,
    ollama_model: str,
    anthropic_api_key: str = "",
    anthropic_model: str = "claude-haiku-4-5-20251001",
    timeout: float = 120.0,
    max_tokens: int = 2048,
) -> tuple[list[dict], str]:
    """Generate a JSON array of question dicts. Returns (questions, source)."""
    if anthropic_api_key:
        logger.info("Using Anthropic  model=%s", anthropic_model)
        try:
            text = await _call_anthropic_raw(prompt, anthropic_api_key, anthropic_model, _SYSTEM_ARRAY, max_tokens)
            return _parse_json_questions(text), "anthropic"
        except Exception as exc:
            logger.warning("Anthropic failed (%s), falling back to local LLM", exc)

    logger.info("Using local LLM  url=%s  model=%s", ollama_url, ollama_model)
    text = await _call_local_raw(prompt, ollama_url, ollama_model, _SYSTEM_ARRAY, timeout, max_tokens)
    return _parse_json_questions(text), "local"


async def generate_json_object(
    prompt: str,
    ollama_url: str,
    ollama_model: str,
    anthropic_api_key: str = "",
    anthropic_model: str = "claude-haiku-4-5-20251001",
    timeout: float = 120.0,
    max_tokens: int = 1024,
) -> tuple[dict, str]:
    """Generate a single JSON object. Returns (parsed_dict, source)."""
    if anthropic_api_key:
        logger.info("Using Anthropic (object)  model=%s", anthropic_model)
        try:
            text = await _call_anthropic_raw(prompt, anthropic_api_key, anthropic_model, _SYSTEM_OBJECT, max_tokens)
            return _parse_json_object(text), "anthropic"
        except Exception as exc:
            logger.warning("Anthropic failed (%s), falling back to local LLM", exc)

    logger.info("Using local LLM (object)  url=%s  model=%s", ollama_url, ollama_model)
    text = await _call_local_raw(prompt, ollama_url, ollama_model, _SYSTEM_OBJECT, timeout, max_tokens)
    return _parse_json_object(text), "local"


async def list_models(ollama_url: str) -> list[str]:
    """Return model IDs available on the local server."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{ollama_url}/v1/models")
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", [])]


# ------------------------------------------------------------------
# JSON parsing helpers
# ------------------------------------------------------------------

def _parse_json_questions(text: str) -> list[dict]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"^```[a-z]*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```$", "", text, flags=re.MULTILINE).strip()

    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                logger.info("Parsed %d questions (full array)", len(data))
                return data
        except json.JSONDecodeError:
            pass

    objects = _extract_objects(text)
    if objects:
        logger.warning("Full array parse failed; recovered %d objects individually", len(objects))
        return objects

    raise ValueError("LLM returned no parseable JSON")


def _parse_json_object(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"^```[a-z]*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```$", "", text, flags=re.MULTILINE).strip()

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                logger.info("Parsed JSON object with keys: %s", list(obj.keys()))
                return obj
        except json.JSONDecodeError:
            pass

    raise ValueError("LLM returned no parseable JSON object")


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
# Prompt builders
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


def build_learning_plan_prompt(
    bank_cats: dict[str, int],
    total_questions: int,
    stats_pct: int,
    total_answered: int,
    total_correct: int,
    mastered_count: int,
    by_category: dict,
) -> str:
    bank_lines = "\n".join(
        f"  {cat}: {count} questions"
        for cat, count in sorted(bank_cats.items(), key=lambda x: -x[1])
    )
    cat_lines = ""
    for cat, (correct, total) in sorted(by_category.items(), key=lambda x: (x[1][0] / x[1][1]) if x[1][1] else 0):
        pct = round(100 * correct / total) if total else 0
        bank_total = bank_cats.get(cat, 0)
        cat_lines += f"  {cat}: {correct}/{total} answered ({pct}%), {bank_total} total in bank\n"

    return f"""You are an expert German language teacher. Analyze this student's complete learning data and generate a structured learning plan.

## Question Bank
Total: {total_questions} questions across {len(bank_cats)} categories
{bank_lines}

## Student Performance
Total answered: {total_answered}  |  Correct: {total_correct}  |  Overall: {stats_pct}%
Mastered (answered correctly 4+ times): {mastered_count} questions

By category (sorted worst → best):
{cat_lines}
Generate a learning plan JSON object:
{{
  "summary": "2-3 sentence analysis: the student's current level, biggest gaps, and recommended focus going forward",
  "recommended_progression": [
    "Theme 1: <name> — <one-line description>",
    "Theme 2: ...",
    "Theme 3: ...",
    "Theme 4: ...",
    "Theme 5: ..."
  ],
  "weak_areas": ["area1", "area2"],
  "strengths": ["area1"]
}}

recommended_progression: 5-8 concrete, sequenced learning themes tailored to this student's gaps, ordered from most urgent to advanced.
Output ONLY the JSON object."""


def build_new_theme_prompt(
    ai_summary: str,
    completed_themes: list[str],
    stats_pct: int,
    total_answered: int,
    available_cats: list[str],
) -> str:
    completed_str = (
        "\n".join(f"  - {t}" for t in completed_themes)
        or "  (none — this is the first theme)"
    )
    cats_str = ", ".join(available_cats)

    return f"""You are an expert German language teacher creating the next learning theme for a student.

## Student Analysis
{ai_summary if ai_summary else "No formal plan yet — choose an appropriate starting theme based on the student's stats."}

## Completed Themes (do NOT repeat these)
{completed_str}

## Current Stats
Overall accuracy: {stats_pct}%  |  Total questions answered: {total_answered}

## Available Question Categories
{cats_str}

Generate the NEXT most appropriate learning theme as a JSON object:
{{
  "name": "Concise theme name (e.g. 'Modal Verbs: können and müssen')",
  "description": "Thorough explanation of the topic: what it is, when to use it, key rules. 3-5 sentences in English.",
  "grammar_rules": [
    "Rule 1: ...",
    "Rule 2: ...",
    "Rule 3: ..."
  ],
  "examples": [
    {{"german": "Ich kann Deutsch sprechen.", "english": "I can speak German."}},
    {{"german": "Du musst das lernen.", "english": "You must learn this."}},
    {{"german": "Er darf hier nicht parken.", "english": "He is not allowed to park here."}}
  ],
  "focus_categories": ["category1", "category2"]
}}

Choose the theme that best addresses this student's gaps and follows naturally from what they've already studied.
Output ONLY the JSON object."""


def build_daily_routine_decision_prompt(
    learning_plan: dict,
    current_theme: dict,
    theme_progress: dict,
    theme_answers: list[dict],
    stats_pct: int,
) -> str:
    total = theme_progress.get("total", 0)
    attempted = theme_progress.get("attempted", 0)
    correct = theme_progress.get("correct", 0)
    theme_accuracy = round(100 * correct / attempted) if attempted else 0

    recent_lines = ""
    for r in theme_answers[-12:]:
        status = "✓" if r["correct"] else "✗"
        recent_lines += f"  {status}\n"

    completed = [t["name"] for t in learning_plan.get("themes_history", [])]
    progression = learning_plan.get("recommended_progression", [])

    return f"""You are an AI tutor managing a German student's daily learning session.

## Learning Plan Summary
{learning_plan.get("ai_summary", "N/A")}

## Recommended Progression
{chr(10).join(f"  {i+1}. {t}" for i, t in enumerate(progression[:6])) or "  N/A"}

## Current Theme
Name: {current_theme.get("name", "")}
Started: {current_theme.get("started_at", "")[:10]}
Total exercises generated: {total}

## Theme Progress
Attempted: {attempted}/{total}  |  Answered correctly: {correct}  |  Theme accuracy: {theme_accuracy}%
Overall student accuracy: {stats_pct}%

## Recent answers on this theme (✓ = correct, ✗ = wrong)
{recent_lines or "  (no answers yet)"}

## Completed Themes
{", ".join(completed) or "(none — this is the first theme)"}

DECISION: Based on this data, decide what to do next for this student.

Move to the NEXT THEME if:
  - The student has attempted ≥70% of exercises with ≥75% accuracy on this theme
  - OR the student is clearly ready to advance based on overall progress

Continue with MORE EXERCISES if:
  - The student hasn't practiced enough yet (<50% attempted)
  - OR accuracy is below 70% and more practice on this topic would help
  - OR the student is making good recent progress and could benefit from variety

Output ONLY this JSON object:
{{
  "decision": "continue" | "next_theme",
  "reason": "One sentence explaining your decision"
}}"""


def build_lesson_questions_prompt(
    theme: dict,
    stats_pct: int,
    total_answered: int,
    recent_mistakes: list[dict],
    available_cats: list[str],
    count: int = 20,
) -> str:
    rules_text = "\n".join(
        f"  {i + 1}. {r}" for i, r in enumerate(theme.get("grammar_rules", []))
    ) or "  (see description)"
    examples_text = "\n".join(
        f"  • {e.get('german', '')} → {e.get('english', '')}"
        for e in theme.get("examples", [])[:5]
    ) or "  (see description)"
    mistakes_text = "".join(
        f"  - [{m.get('difficulty', '')}|{m.get('cat', '')}] {m.get('q', '')[:80]}\n"
        for m in recent_mistakes
    ) or "  (none yet)\n"

    if stats_pct >= 80:
        target_diff = "B1–B2"
    elif stats_pct >= 60:
        target_diff = "A2–B1"
    else:
        target_diff = "A1–A2"

    cats_str = ", ".join(available_cats)
    focus_cats = ", ".join(theme.get("focus_categories", available_cats[:3]))
    mc_count = round(count * 0.6)
    fill_count = count - mc_count

    return f"""You are creating German language exercises for a student studying a specific theme.

## Current Theme
Name: {theme.get('name', 'German Grammar')}
Description: {theme.get('description', '')}

Grammar Rules:
{rules_text}

Examples:
{examples_text}

## Student Context
Overall accuracy: {stats_pct}%  |  Total answered: {total_answered}
Target difficulty: {target_diff}

## Recent Mistakes (prioritize these patterns)
{mistakes_text}
## Your Task
Generate {count} practice exercises that DIRECTLY test: {theme.get('name', 'the theme above')}.
Focus categories: {focus_cats}

Mix of types:
- {mc_count} multiple choice (type: "mc") with exactly 4 options each
- {fill_count} fill-in-the-blank (type: "fill") targeting key grammatical forms

ALL questions must practice the grammar rules listed above.

CORRECTNESS IS MANDATORY:
1. German grammar must be 100% correct. Every article, case ending, verb form, and word order must be standard written German.
2. The correct answer must be definitively and unambiguously right.
3. Wrong options must be grammatically plausible but clearly wrong for a specific reason.
4. The explanation must state WHY the correct answer is right.

REQUIRED JSON FIELDS (use exactly these names):
- "type": "mc" or "fill"
- "q": the question or sentence with blank (NOT "question" — must be "q")
- "cat": one of: {cats_str}
- "difficulty": A1/A2/B1/B2 — target {target_diff}
- "answer": integer 0–3 for mc (index into opts), text string for fill
- "opts": list of exactly 4 strings (mc only — omit for fill)
- "hint": short hint string (fill only, optional)
- "explanation": 1–2 sentences in English

Output ONLY the JSON array of {count} question objects."""
