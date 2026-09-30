import re
from typing import List

HUMAN_WRITING_SYSTEM_PROMPT = """
HUMAN WRITING PRINCIPLES:
Write this as a specific person with a real position, not as a survey of the topic.

Commit: make one arguable claim and defend it. Qualify once if genuinely needed, then move on — don't stack hedges ("could potentially… may sometimes"). If it's contested, say what the evidence favors and what would change your mind. Don't give every side equal airtime to avoid concluding.

Be specific: replace category nouns (many companies, studies show, experts agree, users) with named instances, real numbers, actual dates. If you don't have a verified specific, say so plainly rather than inventing a plausible one.

Vary rhythm: mix short blunt sentences with long ones. Never write five same-length, same-structure sentences in a row.

Cut scaffolding: no scene-setting opener ("In today's fast-paced world"), no restating questions before answering, no "moreover/furthermore/additionally" between paragraphs, no "in conclusion" summary. Start on the point, stop at the last real one.

Avoid: buzzwords (delve, tapestry, landscape, robust, seamless, unlock, elevate, foster, leverage, empower, game-changer); reflexive lists of exactly three; em dashes used as a drama beat; "it's not X, it's Y" as a punchline; emojis as bullets; headers and bullet points unless the content is genuinely meant to be scanned rather than read.

Let structure follow the argument — if it's two points, write two points, and let sections be uneven in length.

Then revise: delete your first and last paragraph and check whether anything was lost. Read it aloud and cut whatever you'd never say out loud.

Don't overcorrect into punchy contrarianism — that's just a different recognizable style. Aim for someone who thought carefully about one specific thing.
""".strip()

FORBIDDEN_BUZZWORDS = [
    "delve", "tapestry", "landscape", "robust", "seamless",
    "unlock", "elevate", "foster", "leverage", "empower",
    "game-changer", "game changer", "revolutionary", "skyrocket",
    "10x your", "will blow your mind"
]

FORBIDDEN_SCAFFOLDING = [
    "in today's fast-paced world",
    "in the fast-paced world",
    "in today's rapidly evolving",
    "in today's digital age",
    "moreover",
    "furthermore",
    "additionally",
    "in conclusion",
    "to conclude",
    "in summary"
]

FORBIDDEN_CATEGORY_NOUNS = [
    "studies show",
    "experts agree",
    "many companies",
    "research suggests"
]

def build_human_writing_instruction(role_description: str = "") -> str:
    """Build a unified system prompt combining agent role with the Human Writing Principles."""
    if role_description:
        return f"{role_description}\n\n---\n{HUMAN_WRITING_SYSTEM_PROMPT}"
    return HUMAN_WRITING_SYSTEM_PROMPT

def check_human_writing_violations(text: str) -> List[str]:
    """Scan text for explicit violations of the Human Writing guidelines."""
    violations = []
    text_lower = text.lower()
    
    for word in FORBIDDEN_BUZZWORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            violations.append(f"Forbidden buzzword used: '{word}'")
            
    for scaf in FORBIDDEN_SCAFFOLDING:
        if scaf in text_lower:
            violations.append(f"Forbidden scaffolding phrase: '{scaf}'")

    for cat in FORBIDDEN_CATEGORY_NOUNS:
        if cat in text_lower:
            violations.append(f"Forbidden vague category noun: '{cat}'")

    # Check for drama beat em-dashes
    if " — " in text or " – " in text:
        violations.append("Contains em dash drama beat ('—'). Rephrase naturally.")

    return violations
