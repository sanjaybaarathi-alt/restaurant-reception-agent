"""Versioned YAML prompt loading."""

from pathlib import Path

import yaml

PROMPT_PATH = Path(__file__).parent / "prompt" / "agent_v1.yaml"


def load_system_prompt() -> str:
    data = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
    sections: list[str] = []
    headings = ("persona", "mission", "scope", "constraints", "rules", "workflow", "output_contract", "error_handling")
    for heading in headings:
        value = data[heading]
        if isinstance(value, list):
            body = "\n".join(f"- {item}" for item in value)
        else:
            body = str(value)
        sections.append(f"## {heading.replace('_', ' ').title()}\n{body}")
    return "\n\n".join(sections)
