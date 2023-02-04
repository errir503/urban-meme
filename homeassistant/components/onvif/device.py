"""ONVIF device abstraction."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import datetime as dt
import os
import time

from httpx import RequestError
import onvif
from onvif import ONVIFCamera
from onvif.exceptions import ONVIFError
from zeep.exceptions import Fault, XMLParseError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from .const import (
    ABSOLUTE_MOVE,
    CONTINUOUS_MOVE,
    GOTOPRESET_MOVE,
    LOGGER,
    PAN_FACTOR,
    RELATIVE_MOVE,
    STOP_MOVE,
    TILT_FACTOR,
    ZOOM_FACTOR,
)
from .event import EventManager
from .models import PTZ, Capabilities, DeviceInfo, Profile, Resolution, Video


class ONVIFDevice:
    """Manages an ONVIF device."""

    device: ONVIFCamera
    events: EventManager

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the device."""
        self.hass: HomeAssistant = hass
        self.config_entry: ConfigEntry = config_entry
        self.available: bool = True

        self.info: DeviceInfo = DeviceInfo()
        self.capabilities: Capabilities = Capabilities()
        self.profiles: list[Profile] = []
        self.max_resolution: int = 0

        self._dt_diff_seconds: float = 0

    @property
    def name(self) -> str:
        """Return the name of this device."""
        return self.config_entry.data[CONF_NAME]

    @property
    def host(self) -> str:
        """Return the host of this device."""
        return self.config_entry.data[CONF_HOST]

    @property
    def port(self) -> int:
        """Return the port of this device."""
        return self.config_entry.data[CONF_PORT]

    @property
    def username(self) -> str:
        """Return the username of this device."""
        return self.config_entry.data[CONF_USERNAME]

    @property
    def password(self) -> str:
        """Return the password of this device."""
        return self.config_entry.data[CONF_PASSWORD]

    async def async_setup(self) -> bool:
        """Set up the device."""
        self.device = get_device(
            self.hass,
            host=self.config_entry.data[CONF_HOST],
            port=self.config_entry.data[CONF_PORT],
            username=self.config_entry.data[CONF_USERNAME],
            password=self.config_entry.data[CONF_PASSWORD],
        )

        # Get all device info
        try:
            await self.device.update_xaddrs()
            await self.async_check_date_and_time()

            # Create event manager
            assert self.config_entry.unique_id
            self.events = EventManager(
                self.hass, self.device, self.config_entry.unique_id
            )

            # Fetch basic device info and capabilities
            self.info = await self.async_get_device_info()
            LOGGER.debug("Camera %s info = %s", self.name, self.info)
            self.capabilities = await self.async_get_capabilities()
            LOGGER.debug("Camera %s capabilities = %s", self.name, self.capabilities)
            self.profiles = await self.async_get_profiles()
            LOGGER.debug("Camera %s profiles = %s", self.name, self.profiles)

            # No camera profiles to add
            if not self.profiles:
                return False

            if self.capabilities.ptz:
                self.device.create_ptz_service()

            # Determine max resolution from profiles
            self.max_resolution = max(
                profile.video.resolution.width
                for profile in self.profiles
                if profile.video.encoding == "H264"
            )
        except RequestError as err:
            LOGGER.warning(
                "Couldn't connect to camera '%s', but will retry later. Error: %s",
                self.name,
                err,
            )
            self.available = False
            await self.device.close()
        except Fault as err:
            LOGGER.error(
                (
                    "Couldn't connect to camera '%s', please verify "
                    "that the credentials are correct. Error: %s"
                ),
                self.name,
                err,
            )
            return False

        return True

    async def async_stop(self, event=None):
        """Shut it all down."""
        if self.events:
            await self.events.async_stop()
        await self.device.close()

    async def async_manually_set_date_and_time(self) -> None:
        """Set Date and Time Manually using SetSystemDateAndTime command."""
        device_mgmt = self.device.create_devicemgmt_service()

        # Retrieve DateTime object from camera to use as template for Set operation
        device_time = await device_mgmt.GetSystemDateAndTime()

        system_date = dt_util.utcnow()
        LOGGER.debug("System date (UTC): %s", system_date)

        dt_param = device_mgmt.create_type("SetSystemDateAndTime")
        dt_param.DateTimeType = "Manual"
        # Retrieve DST setting from system
        dt_param.DaylightSavings = bool(time.localtime().tm_isdst)
        dt_param.UTCDateTime = device_time.UTCDateTime
        # Retrieve timezone from system
        dt_param.TimeZone = str(system_date.astimezone().tzinfo)
        dt_param.UTCDateTime.Date.Year = system_date.year
        dt_param.UTCDateTime.Date.Month = system_date.month
        dt_param.UTCDateTime.Date.Day = system_date.day
        dt_param.UTCDateTime.Time.Hour = system_date.hour
        dt_param.UTCDateTime.Time.Minute = system_date.minute
        dt_param.UTCDateTime.Time.Second = system_date.second
        LOGGER.debug("SetSystemDateAndTime: %s", dt_param)
        await device_mgmt.SetSystemDateAndTime(dt_param)

    async def async_check_date_and_time(self) -> None:
        """Warns if device and system date not synced."""
        LOGGER.debug("Setting up the ONVIF device management service")
        device_mgmt = self.device.create_devicemgmt_service()

        LOGGER.debug("Retrieving current device date/time")
        try:
            system_date = dt_util.utcnow()
            device_time = await device_mgmt.GetSystemDateAndTime()
            if not device_time:
                LOGGER.debug(
                    """Couldn't get device '%s' date/time.
                    GetSystemDateAndTime() return null/empty""",
                    self.name,
                )
                return

            LOGGER.debug("Device time: %s", device_time)

            tzone = dt_util.DEFAULT_TIME_ZONE
            cdate = device_time.LocalDateTime
            if device_time.UTCDateTime:
                tzone = dt_util.UTC
                cdate = device_time.UTCDateTime
            elif device_time.TimeZone:
                tzone = dt_util.get_time_zone(device_time.TimeZone.TZ) or tzone

            if cdate is None:
                LOGGER.warning("Could not retrieve date/time on this camera")
            else:
                cam_date = dt.datetime(
                    cdate.Date.Year,
                    cdate.Date.Month,
                    cdate.Date.Day,
                    cdate.Time.Hour,
                    cdate.Time.Minute,
                    cdate.Time.Second,
                    0,
                    tzone,
                )

                cam_date_utc = cam_date.astimezone(dt_util.UTC)

                LOGGER.debug(
                    "Device date/time: %s | System date/time: %s",
                    cam_date_utc,
                    system_date,
                )

                dt_diff = cam_date - system_date
                self._dt_diff_seconds = dt_diff.total_seconds()

                if self._dt_diff_seconds > 5:
                    LOGGER.warning(
                        (
                            "The date/time on %s (UTC) is '%s', "
                            "which is different from the system '%s', "
                            "this could lead to authentication issues"
                        ),
                        self.name,
                        cam_date_utc,
                        system_date,
                    )
                    if device_time.DateTimeType == "Manual":
                        # Set Date and Time ourselves if Date and Time is set manually in the camera.
                        await self.async_manually_set_date_and_time()
        except RequestError as err:
            LOGGER.warning(
                "Couldn't get device '%s' date/time. Error: %s", self.name, err
            )

    async def async_get_device_info(self) -> DeviceInfo:
        """Obtain information about this device."""
        device_mgmt = self.device.create_devicemgmt_service()
        device_info = await device_mgmt.GetDeviceInformation()

        # Grab the last MAC address for backwards compatibility
        mac = None
        try:
            network_interfaces = await device_mgmt.GetNetworkInterfaces()
            for interface in network_interfaces:
                if interface.Enabled:
                    mac = interface.Info.HwAddress
        except Fault as fault:
            if "not implemented" not in fault.message:
                raise fault

            LOGGER.debug(
                "Couldn't get network interfaces from ONVIF device '%s'. Error: %s",
                self.name,
                fault,
            )

        return DeviceInfo(
            device_info.Manufacturer,
            device_info.Model,
            device_info.FirmwareVersion,
            device_info.SerialNumber,
            mac,
        )

    async def async_get_capabilities(self):
        """Obtain information about the available services on the device."""
        snapshot = False
        with suppress(ONVIFError, Fault, RequestError):
            media_service = self.device.create_media_service()
            media_capabilities = await media_service.GetServiceCapabilities()
            snapshot = media_capabilities and media_capabilities.SnapshotUri

        pullpoint = False
        with suppress(ONVIFError, Fault, RequestError, XMLParseError):
            pullpoint = await self.events.async_start()

        ptz = False
        with suppress(ONVIFError, Fault, RequestError):
            self.device.get_definition("ptz")
            ptz = True

        imaging = False
        with suppress(ONVIFError, Fault, RequestError):
            self.device.create_imaging_service()
            imaging = True

        return Capabilities(snapshot, pullpoint, ptz, imaging)

    async def async_get_profiles(self) -> list[Profile]:
        """Obtain media profiles for this device."""
        media_service = self.device.create_media_service()
        result = await media_service.GetProfiles()
        profiles: list[Profile] = []

        if not isinstance(result, list):
            return profiles

        for key, onvif_profile in enumerate(result):
            # Only add H264 profiles
            if (
                not onvif_profile.VideoEncoderConfiguration
                or onvif_profile.VideoEncoderConfiguration.Encoding != "H264"
            ):
                continue

            profile = Profile(
                key,
                onvif_profile.token,
                onvif_profile.Name,
                Video(
                    onvif_profile.VideoEncoderConfiguration.Encoding,
                    Resolution(
                        onvif_profile.VideoEncoderConfiguration.Resolution.Width,
                        onvif_profile.VideoEncoderConfiguration.Resolution.Height,
                    ),
                ),
            )

            # Configure PTZ options
            if self.capabilities.ptz and onvif_profile.PTZConfiguration:
                profile.ptz = PTZ(
                    onvif_profile.PTZConfiguration.DefaultContinuousPanTiltVelocitySpace
                    is not None,
                    onvif_profile.PTZConfiguration.DefaultRelativePanTiltTranslationSpace
                    is not None,
                    onvif_profile.PTZConfiguration.DefaultAbsolutePantTiltPositionSpace
                    is not None,
                )

                try:
                    ptz_service = self.device.create_ptz_service()
                    presets = await ptz_service.GetPresets(profile.token)
                    profile.ptz.presets = [preset.token for preset in presets if preset]
                except (Fault, RequestError):
                    # It's OK if Presets aren't supported
                    profile.ptz.presets = []

            # Configure Imaging options
            if self.capabilities.imaging and onvif_profile.VideoSourceConfiguration:
                profile.video_source_token = (
                    onvif_profile.VideoSourceConfiguration.SourceToken
                )

            profiles.append(profile)

        return profiles

    async def async_get_stream_uri(self, profile: Profile) -> str:
        """Get the stream URI for a specified profile."""
        media_service = self.device.create_media_service()
        req = media_service.create_type("GetStreamUri")
        req.ProfileToken = profile.token
        req.StreamSetup = {
            "Stream": "RTP-Unicast",
            "Transport": {"Protocol": "RTSP"},
        }
        result = await media_service.GetStreamUri(req)
        return result.Uri

    async def async_perform_ptz(
        self,
        profile: Profile,
        distance,
        speed,
        move_mode,
        continuous_duration,
        preset,
        pan=None,
        tilt=None,
        zoom=None,
    ):
        """Perform a PTZ action on the camera."""
        if not self.capabilities.ptz:
            LOGGER.warning("PTZ actions are not supported on device '%s'", self.name)
            return

        ptz_service = self.device.create_ptz_service()

        pan_val = distance * PAN_FACTOR.get(pan, 0)
        tilt_val = distance * TILT_FACTOR.get(tilt, 0)
        zoom_val = distance * ZOOM_FACTOR.get(zoom, 0)
        speed_val = speed
        preset_val = preset
        LOGGER.debug(
            (
                "Calling %s PTZ | Pan = %4.2f | Tilt = %4.2f | Zoom = %4.2f | Speed ="
                " %4.2f | Preset = %s"
            ),
            move_mode,
            pan_val,
            tilt_val,
            zoom_val,
            speed_val,
            preset_val,
        )
        try:
            req = ptz_service.create_type(move_mode)
            req.ProfileToken = profile.token
            if move_mode == CONTINUOUS_MOVE:
                # Guard against unsupported operation
                if not profile.ptz or not profile.ptz.continuous:
                    LOGGER.warning(
                        "ContinuousMove not supported on device '%s'", self.name
                    )
                    return

                velocity = {}
                if pan is not None or tilt is not None:
                    velocity["PanTilt"] = {"x": pan_val, "y": tilt_val}
                if zoom is not None:
                    velocity["Zoom"] = {"x": zoom_val}

                req.Velocity = velocity

                await ptz_service.ContinuousMove(req)
                await asyncio.sleep(continuous_duration)
                req = ptz_service.create_type("Stop")
                req.ProfileToken = profile.token
                await ptz_service.Stop(
                    {"ProfileToken": req.ProfileToken, "PanTilt": True, "Zoom": False}
                )
            elif move_mode == RELATIVE_MOVE:
                # Guard against unsupported operation
                if not profile.ptz or not profile.ptz.relative:
                    LOGGER.warning(
                        "RelativeMove not supported on device '%s'", self.name
                    )
                    return

                req.Translation = {
                    "PanTilt": {"x": pan_val, "y": tilt_val},
                    "Zoom": {"x": zoom_val},
                }
                req.Speed = {
                    "PanTilt": {"x": speed_val, "y": speed_val},
                    "Zoom": {"x": speed_val},
                }
                await ptz_service.RelativeMove(req)
            elif move_mode == ABSOLUTE_MOVE:
                # Guard against unsupported operation
                if not profile.ptz or not profile.ptz.absolute:
                    LOGGER.warning(
                        "AbsoluteMove not supported on device '%s'", self.name
                    )
                    return

                req.Position = {
                    "PanTilt": {"x": pan_val, "y": tilt_val},
                    "Zoom": {"x": zoom_val},
                }
                req.Speed = {
                    "PanTilt": {"x": speed_val, "y": speed_val},
                    "Zoom": {"x": speed_val},
                }
                await ptz_service.AbsoluteMove(req)
            elif move_mode == GOTOPRESET_MOVE:
                # Guard against unsupported operation
                if not profile.ptz or not profile.ptz.presets:
                    LOGGER.warning(
                        "Absolute Presets not supported on device '%s'", self.name
                    )
                    return
                if preset_val not in profile.ptz.presets:
                    LOGGER.warning(
                        (
                            "PTZ preset '%s' does not exist on device '%s'. Available"
                            " Presets: %s"
                        ),
                        preset_val,
                        self.name,
                        ", ".join(profile.ptz.presets),
                    )
                    return

                req.PresetToken = preset_val
                req.Speed = {
                    "PanTilt": {"x": speed_val, "y": speed_val},
                    "Zoom": {"x": speed_val},
                }
                await ptz_service.GotoPreset(req)
            elif move_mode == STOP_MOVE:
                await ptz_service.Stop(req)
        except ONVIFError as err:
            if "Bad Request" in err.reason:
                LOGGER.warning("Device '%s' doesn't support PTZ", self.name)
            else:
                LOGGER.error("Error trying to perform PTZ action: %s", err)

    async def async_run_aux_command(
        self,
        profile: Profile,
        cmd: str,
    ) -> None:
        """Execute a PTZ auxiliary command on the camera."""
        if not self.capabilities.ptz:
            LOGGER.warning("PTZ actions are not supported on device '%s'", self.name)
            return

        ptz_service = self.device.create_ptz_service()

        LOGGER.debug(
            "Running Aux Command | Cmd = %s",
            cmd,
        )
        try:
            req = ptz_service.create_type("SendAuxiliaryCommand")
            req.ProfileToken = profile.token
            req.AuxiliaryData = cmd
            await ptz_service.SendAuxiliaryCommand(req)
        except ONVIFError as err:
            if "Bad Request" in err.reason:
                LOGGER.warning("Device '%s' doesn't support PTZ", self.name)
            else:
                LOGGER.error("Error trying to send PTZ auxiliary command: %s", err)

    async def async_set_imaging_settings(
        self,
        profile: Profile,
        settings: dict,
    ) -> None:
        """Set an imaging setting on the ONVIF imaging service."""
        # The Imaging Service is defined by ONVIF standard
        # https://www.onvif.org/specs/srv/img/ONVIF-Imaging-Service-Spec-v210.pdf
        if not self.capabilities.imaging:
            LOGGER.warning(
                "The imaging service is not supported on device '%s'", self.name
            )
            return

        imaging_service = self.device.create_imaging_service()

        LOGGER.debug("Setting Imaging Setting | Settings = %s", settings)
        try:
            req = imaging_service.create_type("SetImagingSettings")
            req.VideoSourceToken = profile.video_source_token
            req.ImagingSettings = settings
            await imaging_service.SetImagingSettings(req)
        except ONVIFError as err:
            if "Bad Request" in err.reason:
                LOGGER.warning(
                    "Device '%s' doesn't support the Imaging Service", self.name
                )
            else:
                LOGGER.error("Error trying to set Imaging settings: %s", err)


def get_device(
    hass: HomeAssistant,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
) -> ONVIFCamera:
    """Get ONVIFCamera instance."""
    return ONVIFCamera(
        host,
        port,
        username,
        password,
        f"{os.path.dirname(onvif.__file__)}/wsdl/",
        no_cache=True,
    )
