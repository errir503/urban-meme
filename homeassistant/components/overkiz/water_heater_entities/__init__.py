"""Water heater entities for the Overkiz (by Somfy) integration."""
from pyoverkiz.enums.ui import UIWidget

from .atlantic_pass_apc_dhw import AtlanticPassAPCDHW

WIDGET_TO_WATER_HEATER_ENTITY = {
    UIWidget.ATLANTIC_PASS_APC_DHW: AtlanticPassAPCDHW,
}
