"""Generate ssdp file."""
from __future__ import annotations

from collections import defaultdict

import black

from .model import Config, Integration
from .serializer import to_string

BASE = """
\"\"\"Automatically generated by hassfest.

To update, run python3 -m script.hassfest
\"\"\"

SSDP = {}
""".strip()


def sort_dict(value):
    """Sort a dictionary."""
    return {key: value[key] for key in sorted(value)}


def generate_and_validate(integrations: dict[str, Integration]):
    """Validate and generate ssdp data."""

    data = defaultdict(list)

    for domain in sorted(integrations):
        integration = integrations[domain]

        if not integration.manifest or not integration.config_flow:
            continue

        ssdp = integration.manifest.get("ssdp")

        if not ssdp:
            continue

        for matcher in ssdp:
            data[domain].append(sort_dict(matcher))

    return black.format_str(BASE.format(to_string(data)), mode=black.Mode())


def validate(integrations: dict[str, Integration], config: Config):
    """Validate ssdp file."""
    ssdp_path = config.root / "homeassistant/generated/ssdp.py"
    config.cache["ssdp"] = content = generate_and_validate(integrations)

    if config.specific_integrations:
        return

    with open(str(ssdp_path)) as fp:
        if fp.read() != content:
            config.add_error(
                "ssdp",
                "File ssdp.py is not up to date. Run python3 -m script.hassfest",
                fixable=True,
            )
        return


def generate(integrations: dict[str, Integration], config: Config):
    """Generate ssdp file."""
    ssdp_path = config.root / "homeassistant/generated/ssdp.py"
    with open(str(ssdp_path), "w") as fp:
        fp.write(f"{config.cache['ssdp']}")
