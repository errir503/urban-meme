"""Tests for the Nina integration."""
import json
from typing import Any

from tests.common import load_fixture


def mocked_request_function(url: str) -> dict[str, Any]:
    """Mock of the request function."""
    dummy_response: dict[str, Any] = json.loads(
        load_fixture("sample_warnings.json", "nina")
    )

    dummy_response_details: dict[str, Any] = json.loads(
        load_fixture("sample_warning_details.json", "nina")
    )

    if url == "https://warnung.bund.de/api31/dashboard/083350000000.json":
        return dummy_response

    warning_id = url.replace("https://warnung.bund.de/api31/warnings/", "").replace(
        ".json", ""
    )

    return dummy_response_details[warning_id]
