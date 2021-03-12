"""
Support for Pioneer Network Receivers.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.pioneer/
"""
import logging
import telnetlib

import voluptuous as vol

from homeassistant.components.media_player import (
    MediaPlayerEntity, PLATFORM_SCHEMA)
from homeassistant.components.media_player.const import (
    SUPPORT_PAUSE, SUPPORT_SELECT_SOURCE, SUPPORT_TURN_OFF, SUPPORT_TURN_ON, 
	SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_STEP, SUPPORT_VOLUME_SET, SUPPORT_PLAY)
from homeassistant.const import (
    CONF_HOST, STATE_OFF, STATE_ON, STATE_UNKNOWN, CONF_NAME, CONF_PORT,
    CONF_TIMEOUT)
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'Pioneer AVR SX-LC58'
DEFAULT_PORT = 8102   # Some use other use 23 telnet default.
DEFAULT_TIMEOUT = 10

SUPPORT_PIONEER = SUPPORT_PAUSE | SUPPORT_VOLUME_SET | SUPPORT_VOLUME_STEP | SUPPORT_VOLUME_MUTE | \
                  SUPPORT_TURN_ON | SUPPORT_TURN_OFF | \
                  SUPPORT_SELECT_SOURCE | SUPPORT_PLAY

MAX_VOLUME = 160

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.socket_timeout,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Pioneer platform."""
    pioneer = PioneerDevice(
        config.get(CONF_NAME), config.get(CONF_HOST), config.get(CONF_PORT),
        config.get(CONF_TIMEOUT))

    if pioneer.update():
        add_devices([pioneer])


class PioneerDevice(MediaPlayerEntity):
    """Representation of a Pioneer device."""

    def __init__(self, name, host, port, timeout):
        """Initialize the Pioneer device."""
        self._name = name
        self._host = host
        self._port = port
        self._timeout = timeout
        self._pwstate = 'PWR2'
        self._volume = 0
        self._muted = False
        self._selected_source = ''
        self._source_name_to_number = {"Vinyl":"01","BRD":"25","Switch":"04","TV":"05","ChromeCast":"06","iPod":"17","HDMI4":"22","HDMI5":"23","HDMI6":"24"}
        self._source_number_to_name = {"01":"Vinyl","25":"BRD","04":"Switch","05":"TV","06":"ChromeCast","17":"iPod","22":"HDMI4","23":"HDMI5","24":"HDMI6"}

    @classmethod
    def telnet_request(cls, telnet, command, expected_prefix):
        """Execute `command` and return the response."""
        try:
            telnet.write(command.encode("ASCII") + b"\r")
        except telnetlib.socket.timeout:
            _LOGGER.debug("Pioneer command %s timed out in telnet_request", command)
            if telnet:
                telnet.close()
            return None

        # The receiver will randomly send state change updates, make sure
        # we get the response we are looking for
        for _ in range(3):
            result = telnet.read_until(b"\r\n", timeout=0.2).decode("ASCII") \
                .strip()
            if result.startswith(expected_prefix):
                return result

        return None

    def telnet_command(self, command):
        """Establish a telnet connection and sends command."""
        try:
            try:
                telnet = telnetlib.Telnet(
                    self._host, self._port, self._timeout)
            except (ConnectionRefusedError, OSError):
                _LOGGER.warning("Pioneer %s refused connection in command", self._name)
                if telnet:
                    telnet.close()
                return
            telnet.write(command.encode("ASCII") + b"\r")
            telnet.read_very_eager()  # skip response
            telnet.close()
        except telnetlib.socket.timeout:
            _LOGGER.debug(
                "Pioneer %s command %s timed out", self._name, command)
            if telnet:
                telnet.close()

    def update(self):
        """Get the latest details from the device."""
        try:
            telnet = telnetlib.Telnet(self._host, self._port, self._timeout)
        except (ConnectionRefusedError, OSError):
            _LOGGER.info("Pioneer %s refused connection in update", self._name)
            return True

        pwstate = self.telnet_request(telnet, "?P", "PWR")
        if pwstate:
            self._pwstate = pwstate

        volume_str = self.telnet_request(telnet, "?V", "VOL")
        self._volume = int(volume_str[3:]) / MAX_VOLUME if volume_str else None

        muted_value = self.telnet_request(telnet, "?M", "MUT")
        self._muted = (muted_value == "MUT0") if muted_value else None

        source_number = self.telnet_request(telnet, "?F", "FN")

        if source_number:
            self._selected_source = self._source_number_to_name \
                .get(source_number[2:])
        else:
            self._selected_source = None

        if telnet:
            telnet.close()
        return True

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def state(self):
        """Return the state of the device."""
        if self._pwstate == "PWR2":
            return STATE_OFF
        if self._pwstate == "PWR0":
            return STATE_ON

        # return STATE_UNKNOWN
        return STATE_OFF

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._volume

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._muted

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_PIONEER

    @property
    def source(self):
        """Return the current input source."""
        return self._selected_source

    @property
    def source_list(self):
        """List of available input sources."""
        return list(self._source_name_to_number.keys())

    @property
    def media_title(self):
        """Title of current playing media."""
        return self._selected_source

    def turn_off(self):
        """Turn off media player."""
        self.telnet_command("PF")

    def volume_up(self):
        """Volume up media player."""
        self.telnet_command("VU")

    def volume_down(self):
        """Volume down media player."""
        self.telnet_command("VD")

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        # 60dB max
        self.telnet_command(str(round(volume * MAX_VOLUME)).zfill(3) + "VL")

    def mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        self.telnet_command("MO" if mute else "MF")

    def turn_on(self):
        """Turn the media player on."""
        self.telnet_command("PO")

    def select_source(self, source):
        """Select input source."""
        self.telnet_command(self._source_name_to_number.get(source) + "FN")