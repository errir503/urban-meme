"""The Home Assistant alerts integration."""
from __future__ import annotations

import asyncio
import dataclasses
from datetime import timedelta
import logging

import aiohttp
from awesomeversion import AwesomeVersion, AwesomeVersionStrategy

from homeassistant.const import __version__
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.start import async_at_start
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.yaml import parse_yaml

DOMAIN = "homeassistant_alerts"
UPDATE_INTERVAL = timedelta(hours=3)
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up alerts."""
    last_alerts: dict[str, str | None] = {}

    async def async_update_alerts() -> None:
        nonlocal last_alerts

        active_alerts: dict[str, str | None] = {}

        for issue_id, alert in coordinator.data.items():
            # Skip creation if already created and not updated since then
            if issue_id in last_alerts and alert.date_updated == last_alerts[issue_id]:
                active_alerts[issue_id] = alert.date_updated
                continue

            # Fetch alert to get title + description
            try:
                response = await async_get_clientsession(hass).get(
                    f"https://alerts.home-assistant.io/alerts/{alert.filename}",
                    timeout=aiohttp.ClientTimeout(total=10),
                )
            except asyncio.TimeoutError:
                _LOGGER.warning("Error fetching %s: timeout", alert.filename)
                continue

            alert_content = await response.text()
            alert_parts = alert_content.split("---")

            if len(alert_parts) != 3:
                _LOGGER.warning(
                    "Error parsing %s: unexpected metadata format", alert.filename
                )
                continue

            try:
                alert_info = parse_yaml(alert_parts[1])
            except ValueError as err:
                _LOGGER.warning("Error parsing %s metadata: %s", alert.filename, err)
                continue

            if not isinstance(alert_info, dict) or "title" not in alert_info:
                _LOGGER.warning("Error in %s metadata: title not found", alert.filename)
                continue

            alert_title = alert_info["title"]
            alert_content = alert_parts[2].strip()

            async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                issue_domain=alert.integration,
                severity=IssueSeverity.WARNING,
                translation_key="alert",
                translation_placeholders={
                    "title": alert_title,
                    "description": alert_content,
                },
            )
            active_alerts[issue_id] = alert.date_updated

        inactive_alerts = last_alerts.keys() - active_alerts.keys()
        for issue_id in inactive_alerts:
            async_delete_issue(hass, DOMAIN, issue_id)

        last_alerts = active_alerts

    @callback
    def async_schedule_update_alerts() -> None:
        if not coordinator.last_update_success:
            return

        hass.async_create_task(async_update_alerts())

    coordinator = AlertUpdateCoordinator(hass)
    coordinator.async_add_listener(async_schedule_update_alerts)

    async def initial_refresh(hass: HomeAssistant) -> None:
        await coordinator.async_refresh()

    async_at_start(hass, initial_refresh)

    return True


@dataclasses.dataclass(frozen=True)
class IntegrationAlert:
    """Issue Registry Entry."""

    integration: str
    filename: str
    date_updated: str | None

    @property
    def issue_id(self) -> str:
        """Return the issue id."""
        return f"{self.filename}_{self.integration}"


class AlertUpdateCoordinator(DataUpdateCoordinator[dict[str, IntegrationAlert]]):
    """Data fetcher for HA Alerts."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the data updater."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.ha_version = AwesomeVersion(
            __version__,
            ensure_strategy=AwesomeVersionStrategy.CALVER,
        )

    async def _async_update_data(self) -> dict[str, IntegrationAlert]:
        response = await async_get_clientsession(self.hass).get(
            "https://alerts.home-assistant.io/alerts.json",
            timeout=aiohttp.ClientTimeout(total=10),
        )
        alerts = await response.json()

        result = {}

        for alert in alerts:
            if "integrations" not in alert:
                continue

            if "homeassistant" in alert:
                if "affected_from_version" in alert["homeassistant"]:
                    affected_from_version = AwesomeVersion(
                        alert["homeassistant"]["affected_from_version"],
                    )
                    if self.ha_version < affected_from_version:
                        continue
                if "resolved_in_version" in alert["homeassistant"]:
                    resolved_in_version = AwesomeVersion(
                        alert["homeassistant"]["resolved_in_version"],
                    )
                    if self.ha_version >= resolved_in_version:
                        continue

            for integration in alert["integrations"]:
                if "package" not in integration:
                    continue

                if integration["package"] not in self.hass.config.components:
                    continue

                integration_alert = IntegrationAlert(
                    integration=integration["package"],
                    filename=alert["filename"],
                    date_updated=alert.get("date_updated"),
                )

                result[integration_alert.issue_id] = integration_alert

        return result
