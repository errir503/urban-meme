"""Read the balance of your bank accounts via FinTS."""
from __future__ import annotations

from collections import namedtuple
from datetime import timedelta
import logging
from typing import Any

from fints.client import FinTS3PinTanClient
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_NAME, CONF_PIN, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=4)

ICON = "mdi:currency-eur"

BankCredentials = namedtuple("BankCredentials", "blz login pin url")

CONF_BIN = "bank_identification_number"
CONF_ACCOUNTS = "accounts"
CONF_HOLDINGS = "holdings"
CONF_ACCOUNT = "account"

ATTR_ACCOUNT = CONF_ACCOUNT
ATTR_BANK = "bank"
ATTR_ACCOUNT_TYPE = "account_type"

SCHEMA_ACCOUNTS = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT): cv.string,
        vol.Optional(CONF_NAME, default=None): vol.Any(None, cv.string),
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_BIN): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PIN): cv.string,
        vol.Required(CONF_URL): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ACCOUNTS, default=[]): cv.ensure_list(SCHEMA_ACCOUNTS),
        vol.Optional(CONF_HOLDINGS, default=[]): cv.ensure_list(SCHEMA_ACCOUNTS),
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensors.

    Login to the bank and get a list of existing accounts. Create a
    sensor for each account.
    """
    credentials = BankCredentials(
        config[CONF_BIN], config[CONF_USERNAME], config[CONF_PIN], config[CONF_URL]
    )
    fints_name = config.get(CONF_NAME, config[CONF_BIN])

    account_config = {
        acc[CONF_ACCOUNT]: acc[CONF_NAME] for acc in config[CONF_ACCOUNTS]
    }

    holdings_config = {
        acc[CONF_ACCOUNT]: acc[CONF_NAME] for acc in config[CONF_HOLDINGS]
    }

    client = FinTsClient(credentials, fints_name)
    balance_accounts, holdings_accounts = client.detect_accounts()
    accounts: list[SensorEntity] = []

    for account in balance_accounts:
        if config[CONF_ACCOUNTS] and account.iban not in account_config:
            _LOGGER.info("Skipping account %s for bank %s", account.iban, fints_name)
            continue

        if not (account_name := account_config.get(account.iban)):
            account_name = f"{fints_name} - {account.iban}"
        accounts.append(FinTsAccount(client, account, account_name))
        _LOGGER.debug("Creating account %s for bank %s", account.iban, fints_name)

    for account in holdings_accounts:
        if config[CONF_HOLDINGS] and account.accountnumber not in holdings_config:
            _LOGGER.info(
                "Skipping holdings %s for bank %s", account.accountnumber, fints_name
            )
            continue

        account_name = holdings_config.get(account.accountnumber)
        if not account_name:
            account_name = f"{fints_name} - {account.accountnumber}"
        accounts.append(FinTsHoldingsAccount(client, account, account_name))
        _LOGGER.debug(
            "Creating holdings %s for bank %s", account.accountnumber, fints_name
        )

    add_entities(accounts, True)


class FinTsClient:
    """Wrapper around the FinTS3PinTanClient.

    Use this class as Context Manager to get the FinTS3Client object.
    """

    def __init__(self, credentials: BankCredentials, name: str) -> None:
        """Initialize a FinTsClient."""
        self._credentials = credentials
        self.name = name

    @property
    def client(self):
        """Get the client object.

        As the fints library is stateless, there is not benefit in caching
        the client objects. If that ever changes, consider caching the client
        object and also think about potential concurrency problems.

        Note: As of version 2, the fints library is not stateless anymore.
        This should be considered when reworking this integration.
        """

        return FinTS3PinTanClient(
            self._credentials.blz,
            self._credentials.login,
            self._credentials.pin,
            self._credentials.url,
        )

    def detect_accounts(self):
        """Identify the accounts of the bank."""

        bank = self.client
        accounts = bank.get_sepa_accounts()
        account_types = {
            x["iban"]: x["type"]
            for x in bank.get_information()["accounts"]
            if x["iban"] is not None
        }

        balance_accounts = []
        holdings_accounts = []
        for account in accounts:
            account_type = account_types[account.iban]
            if 1 <= account_type <= 9:  # 1-9 is balance account
                balance_accounts.append(account)
            elif 30 <= account_type <= 39:  # 30-39 is holdings account
                holdings_accounts.append(account)

        return balance_accounts, holdings_accounts


class FinTsAccount(SensorEntity):
    """Sensor for a FinTS balance account.

    A balance account contains an amount of money (=balance). The amount may
    also be negative.
    """

    def __init__(self, client: FinTsClient, account, name: str) -> None:
        """Initialize a FinTs balance account."""
        self._client = client
        self._account = account
        self._attr_name = name
        self._attr_icon = ICON
        self._attr_extra_state_attributes = {
            ATTR_ACCOUNT: self._account.iban,
            ATTR_ACCOUNT_TYPE: "balance",
        }
        if self._client.name:
            self._attr_extra_state_attributes[ATTR_BANK] = self._client.name

    def update(self) -> None:
        """Get the current balance and currency for the account."""
        bank = self._client.client
        balance = bank.get_balance(self._account)
        self._attr_native_value = balance.amount.amount
        self._attr_native_unit_of_measurement = balance.amount.currency
        _LOGGER.debug("updated balance of account %s", self.name)


class FinTsHoldingsAccount(SensorEntity):
    """Sensor for a FinTS holdings account.

    A holdings account does not contain money but rather some financial
    instruments, e.g. stocks.
    """

    def __init__(self, client: FinTsClient, account, name: str) -> None:
        """Initialize a FinTs holdings account."""
        self._client = client
        self._attr_name = name
        self._account = account
        self._holdings: list[Any] = []
        self._attr_icon = ICON
        self._attr_native_unit_of_measurement = "EUR"

    def update(self) -> None:
        """Get the current holdings for the account."""
        bank = self._client.client
        self._holdings = bank.get_holdings(self._account)
        self._attr_native_value = sum(h.total_value for h in self._holdings)

    @property
    def extra_state_attributes(self) -> dict:
        """Additional attributes of the sensor.

        Lists each holding of the account with the current value.
        """
        attributes = {
            ATTR_ACCOUNT: self._account.accountnumber,
            ATTR_ACCOUNT_TYPE: "holdings",
        }
        if self._client.name:
            attributes[ATTR_BANK] = self._client.name
        for holding in self._holdings:
            total_name = f"{holding.name} total"
            attributes[total_name] = holding.total_value
            pieces_name = f"{holding.name} pieces"
            attributes[pieces_name] = holding.pieces
            price_name = f"{holding.name} price"
            attributes[price_name] = holding.market_value

        return attributes
