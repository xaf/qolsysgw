import logging

from qolsys.exceptions import QolsysGwConfigIncomplete
from qolsys.exceptions import QolsysGwConfigError
from qolsys.utils import get_mac_from_host


LOGGER = logging.getLogger(__name__)


class QolsysGatewayConfig(object):

    _SENTINEL = object()
    _DEFAULT_CONFIG = {
        'panel_host': _SENTINEL,
        'panel_port': None,
        'panel_mac': None,
        'panel_token': _SENTINEL,
        'panel_user_code': None,
        'panel_unique_id': 'qolsys_panel',
        'panel_device_name': 'Qolsys Panel',
        'arm_away_exit_delay': None,
        'arm_stay_exit_delay': None,
        'arm_away_bypass': None,
        'arm_stay_bypass': None,
        'arm_type_custom_bypass': 'arm_away',

        'mqtt_namespace': 'mqtt',
        'mqtt_retain': True,
        'discovery_topic': 'homeassistant',
        'control_topic': '{discovery_topic}/alarm_control_panel/{panel_unique_id}/set',
        'event_topic': 'qolsys/{panel_unique_id}/event',
        'user_control_token': None,

        'ha_check_user_code': True,
        'ha_user_code': None,
        'code_arm_required': False,
        'code_disarm_required': False,
        'code_trigger_required': False,
        'default_trigger_command': None,
        'default_sensor_device_class': 'safety',
        'enable_static_sensors_by_default': False,
        'enable_sensor_tamper_detection': True,
    }

    def __init__(self, args=None, check=True):
        self._override_config = {}

        if args:
            self.load(args)

        if check:
            self.check()

    def load(self, args):
        for k, v in args.items():
            if v is not None and k in self._DEFAULT_CONFIG:
                self._override_config[k] = v

    def check(self):
        errors = 0
        for k in self._DEFAULT_CONFIG.keys():
            if self.get(k) is self._SENTINEL:
                LOGGER.error(f"Missing mandatory configuration key '{k}'")
                errors += 1
        if errors > 0:
            raise QolsysGwConfigIncomplete

        if self.get('panel_user_code') is None:
            if self.get('ha_user_code'):
                raise QolsysGwConfigError("Cannot use 'ha_user_code' if "
                                          "'panel_user_code' is not set")

            for k in ['code_arm_required', 'code_trigger_required']:
                if self.get(k):
                    raise QolsysGwConfigError(
                        f"Cannot use '{k}' if no disarm code is set, as the "
                        "Qolsys Panel does not offer a built-in way to check "
                        "for the code on ARM or TRIGGER actions.")

            # Without a configured disarm code, we cannot have home assistant
            # checking it for us
            self._override_config['ha_check_user_code'] = False

            # Without a configured disarm code, we will use the one provided
            # in home assistant to try and disarm the alarm
            self._override_config['code_disarm_required'] = True

        trig_cmd = self.get('default_trigger_command')
        if trig_cmd:
            trig_cmd = trig_cmd.upper()
            valid_trigger = [
                'TRIGGER',
                'TRIGGER_AUXILIARY',
                'TRIGGER_FIRE',
                'TRIGGER_POLICE',
            ]
            if trig_cmd not in valid_trigger:
                raise QolsysGwConfigError(
                    f"Invalid trigger command '{trig_cmd}'; must be one of "
                    f"{', '.join(valid_trigger)}")

            self._override_config['default_trigger_command'] = trig_cmd

        arm_type = self.get('arm_type_custom_bypass')
        if arm_type:
            arm_type = arm_type.lower()
        valid_arm_type = [
            'arm_stay',
            'arm_away',
        ]
        if arm_type not in valid_arm_type:
            raise QolsysGwConfigError(
                f"Invalid arm type '{arm_type}' for custom bypass; must be "
                f"one of {', '.join(valid_arm_type)}")
        self._override_config['arm_type_custom_bypass'] = arm_type

        if self.get('panel_mac') is None:
            mac = get_mac_from_host(self.get('panel_host'))
            if mac:
                self._override_config['panel_mac'] = mac

        # Apply a template to the control and event topics if the unique id
        # is part of the requested topics
        for k in ('control_topic', 'event_topic'):
            v = self.get(k)
            if v:
                self._override_config[k] = v.format(
                    panel_unique_id=self.get('panel_unique_id'),
                    discovery_topic=self.get('discovery_topic'))

        # Make sure that user codes are stored as strings
        for k in ('panel_user_code', 'ha_user_code'):
            v = self.get(k)
            if v and not isinstance(v, str):
                self._override_config[k] = str(v)

    def get(self, name):
        value = self._override_config.get(name, self._SENTINEL)
        if value is self._SENTINEL:
            value = self._DEFAULT_CONFIG.get(name, self._SENTINEL)
        return value

    def __getattr__(self, name):
        value = self.get(name)
        if value is self._SENTINEL:
            raise AttributeError(f'Parameter `{name}` has not been defined')
        return value
