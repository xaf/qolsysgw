import contextlib
import copier
import os
import random
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

from unittest import mock

from types import SimpleNamespace

import testenv  # noqa: F401

from testutils.docker import AppDaemonDockerLogReader
from testutils.fixtures_data import get_summary
from testutils.homeassistant import HomeAssistantRestAPI
from testutils.mock_panel import PanelServer
from testutils.mock_types import ISODATE
from testutils.mock_types import ISODATE_S
from testutils.utils import get_free_port


def running_in_ci():
    return 'CI' in os.environ


class TestEndtoendQolsysGw(unittest.IsolatedAsyncioTestCase):

    # Valid for 10 years, might need to renew somewhere in december 2032
    HA_TOKEN = ('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI4MTM'
                '3YTczODczNzQ0MDE4ODM4YzkxZmU4Njc2MDdjMCIsImlhdCI6MTY'
                '3MTgzMzYxNCwiZXhwIjoxOTg3MTkzNjE0fQ.dHyImTwZFNbb3hUu'
                'BcUq74Q8LNplEfUPoeCUQbI3txg')

    # Same as in the configuration file
    PANEL_TOKEN = 'ThisIsMyToken'

    # Set a larger timeout for the actions here, as we need time for the
    # side effects to properly propagate
    TIMEOUT = 10

    def _docker_compose(self, *cmd):
        command = ['docker', 'compose'] + list(cmd)
        print(f'Running: {shlex.join(command)}')
        run = subprocess.run(
            command,
            cwd=self._tmpdir.name,
            capture_output=True,
            check=True,
        )
        print(f'Standard Output: {run.stdout.decode()}')
        print(f'Error Output: {run.stderr.decode()}')
        return run

    def _docker_compose_up(self):
        run = self._docker_compose('up', '-d')
        self._docker_is_up = True

        # Find container names, so we can use them after to read logs
        container_pattern = re.compile(
            r'^\s*(?:Container|Creating)\s*'
            r'(?P<container_name>[^ ]*[-_]'
            r'(?P<container>[^ ]*)[-_][0-9]*)'
            r'\s*(?:Started|\.\.\.\s*done)\r?$',
            re.MULTILINE,
        )

        for cont_name, cont_type in container_pattern.findall(run.stderr.decode()):
            self.CONTAINERS[cont_type] = cont_name

        return run

    def _docker_compose_down(self):
        self.CONTAINERS = {}
        run = self._docker_compose('down')
        self._docker_is_up = False
        return run

    def _print_container_versions(self):
        """Print the versions of the containers being used for debugging.

        Uses sys.stderr to ensure output is visible even when pytest
        captures stdout.
        """
        print('\n=== Container Versions ===', file=sys.stderr)
        for service, container_name in self.CONTAINERS.items():
            try:
                # Get the image name and digest
                result = subprocess.run(
                    ['docker', 'inspect', '--format',
                     '{{.Config.Image}} ({{.Image}})', container_name],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print(f'{service}: {result.stdout.strip()}', file=sys.stderr)
                else:
                    print(f'{service}: unable to get version', file=sys.stderr)
            except Exception as e:
                print(f'{service}: error getting version - {e}', file=sys.stderr)
        print('=== End Container Versions ===\n', file=sys.stderr)

    def setUp(self):
        self.CONTAINERS = {}
        self._tmpdir = tempfile.TemporaryDirectory(
            prefix='qolsysgw-end-to-end-',
            # ignore_cleanup_errors=True,
        )

    def tearDown(self):
        if hasattr(self, '_docker_is_up') and self._docker_is_up:
            # Fix permissions on files created by containers before stopping them
            # This allows the temp directory cleanup to work properly
            try:
                self._docker_compose('exec', '-T', 'appdaemon',
                                     'chmod', '-R', '777', '/conf')
            except Exception:
                pass  # Best effort - container might not be running

            # Stop and destroy containers
            self._docker_compose_down()

    @contextlib.asynccontextmanager
    async def get_context(self):
        # Start a panel
        panel = PanelServer()

        # Sometimes there's weird issues with ports, give it a few tries
        for i in reversed(range(10)):
            # Try starting the panel
            await panel.start(port=12345 if running_in_ci() else 0)

            # Check that we can connect to it
            try:
                await panel.test_connection()
                break
            except Exception:
                if not i:
                    raise

                panel.stop()

        # Get a free port for Home Assistant
        ha_port = 8123 if running_in_ci() else get_free_port()

        # Copy files to work with the panel
        copier.run_copy(
            testenv.FIXTURES_DIR,
            self._tmpdir.name,
            data={
                'ROOT_DIR': testenv.ROOT_DIR,
                'WORKSPACE': self._tmpdir.name,
                'HA_PORT': ha_port,
                'HA_TOKEN': self.HA_TOKEN,
                'PANEL_PORT': panel.port,
                'RUNNING_IN_CI': running_in_ci(),
            }
        )

        # Start containers
        self._docker_compose_up()

        # Print container versions for debugging
        self._print_container_versions()

        # Grab logs from AppDaemon
        appdaemon = AppDaemonDockerLogReader(
            container_name=self.CONTAINERS['appdaemon'],
        )
        appdaemon.start()

        # Wait for qolsysgw to ask for the summary
        await panel.wait_for_next_message(
            timeout=self.TIMEOUT * 2,
            filters={'action': 'INFO'},
            raise_on_timeout=True,
        )

        # Then send the summary
        summary = get_summary()
        await panel.writeline(summary.event)

        # Wait for the log saying that AppDaemon sent the last MQTT
        # publish message that we expect
        await appdaemon.wait_for_next_log(
            timeout=self.TIMEOUT,
            filters={
                'action': 'call_service',
                'action_target': 'mqtt/publish',
                'action_data/topic': summary.last_topic,
            },
        )

        try:
            yield SimpleNamespace(
                panel=panel,
                appdaemon=appdaemon,
                summary=summary,
                homeassistant=HomeAssistantRestAPI(
                    port=ha_port,
                    token=self.HA_TOKEN,
                ),
            )
        finally:
            pass

    def _check_entity_states(self, ctx, expected_states, msg=None):
        if msg:
            msg = f'{msg}: '

        # Read the states from the home assistant instance using the API
        resp = ctx.homeassistant.states()
        states = resp.json()

        # Check that the states of the different entities in Home Assistant
        # is as we expect it to be
        for expected_state in expected_states:
            entity_id = expected_state['entity_id']
            expected = {
                **expected_state,
                'context': mock.ANY,
                'last_changed': ISODATE,
                'last_reported': ISODATE,
                'last_updated': ISODATE,
            }

            with self.subTest(msg=f'{msg}Entity {entity_id} is correctly configured'):
                actual = [
                    state
                    for state in states
                    if state['entity_id'] == entity_id
                ]

                self.assertEqual(1, len(actual), f"Entity {entity_id} not found")
                actual = actual[0]

                self.maxDiff = None
                self.assertDictEqual(expected, actual)

    async def _check_initial_state(self, ctx):
        # Wait for the latest entity pushed in MQTT to exist
        # in Home Assistant
        await ctx.homeassistant.wait_for_entity(
            entity=f'binary_sensor.{ctx.summary.entity_ids[-1]}',
            filters={'state': 'off'},
            timeout=self.TIMEOUT,
            raise_if_timeout=True,
        )

        # Check that the states of the entities in Home Assistant are as
        # we expect them to be at this point
        expected_states = [
            {
                'attributes': {
                    'device_class': 'timestamp',
                    'friendly_name': 'Qolsys Panel Last Error',
                    'type': None,
                    'desc': None,
                },
                'entity_id': 'sensor.qolsys_panel_last_error',
                'state': 'unknown',
            },
            {
                'attributes': {
                    'alarm_type': None,
                    'changed_by': None,
                    'code_arm_required': False,
                    'code_format': 'number',
                    'friendly_name': 'Qolsys Panel partition0',
                    'last_error_at': None,
                    'last_error_type': None,
                    'last_error_desc': None,
                    'disarm_failed': 0,
                    'secure_arm': False,
                    'supported_features': 63,
                },
                'entity_id': 'alarm_control_panel.qolsys_panel_partition0',
                'state': 'disarmed',
            },
            {
                'attributes': {
                    'device_class': 'door',
                    'friendly_name': 'Qolsys Panel My Door',
                    'group': 'entryexitdelay',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 1,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_door',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'door',
                    'friendly_name': 'Qolsys Panel My Window',
                    'group': 'entryexitlongdelay',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 1,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_window',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'motion',
                    'friendly_name': 'Qolsys Panel My Motion',
                    'group': 'awayinstantmotion',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 2,
                    'zone_type': 2,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_motion',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'motion',
                    'friendly_name': 'Qolsys Panel Panel Motion',
                    'group': 'safetymotion',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 119,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_panel_motion',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'vibration',
                    'friendly_name': 'Qolsys Panel My Glass Break',
                    'group': 'glassbreakawayonly',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 1,
                    'zone_type': 116,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_glass_break',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'vibration',
                    'friendly_name': 'Qolsys Panel Panel Glass Break',
                    'group': 'glassbreakawayonly',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 1,
                    'zone_type': 116,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_panel_glass_break',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'presence',
                    'friendly_name': 'Qolsys Panel My Phone',
                    'group': 'mobileintrusion',
                    'zone_alarm_type': 1,
                    'zone_physical_type': 1,
                    'zone_type': 115,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_phone',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'smoke',
                    'friendly_name': 'Qolsys Panel My Smoke Detector',
                    'group': 'smoke_heat',
                    'zone_alarm_type': 9,
                    'zone_physical_type': 9,
                    'zone_type': 5,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_smoke_detector',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'gas',
                    'friendly_name': 'Qolsys Panel My CO Detector',
                    'group': 'entryexitdelay',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 1,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_co_detector',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'moisture',
                    'friendly_name': 'Qolsys Panel My Water Detector',
                    'group': 'WaterSensor',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 8,
                    'zone_type': 15,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_water_detector',
                'state': 'off',
            },
            {
                'attributes': {
                    'alarm_type': None,
                    'changed_by': None,
                    'code_arm_required': False,
                    'code_format': 'number',
                    'friendly_name': 'Qolsys Panel partition1',
                    'last_error_at': None,
                    'last_error_type': None,
                    'last_error_desc': None,
                    'disarm_failed': 0,
                    'secure_arm': False,
                    'supported_features': 63,
                },
                'entity_id': 'alarm_control_panel.qolsys_panel_partition1',
                'state': 'disarmed',
            },
            {
                'attributes': {
                    'device_class': 'door',
                    'friendly_name': 'Qolsys Panel My 2nd Door',
                    'group': 'instantperimeter',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 1,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_2nd_door',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'sound',
                    'friendly_name': 'Qolsys Panel My Doorbell Sensor',
                    'group': 'localsafety',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 109,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_doorbell_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'cold',
                    'friendly_name': 'Qolsys Panel My Freeze Sensor',
                    'group': 'freeze',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 6,
                    'zone_type': 17,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_freeze_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'heat',
                    'friendly_name': 'Qolsys Panel My Heat Sensor',
                    'group': 'smoke_heat',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 10,
                    'zone_type': 8,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_heat_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'heat',
                    'friendly_name': 'Qolsys Panel My Temperature Sensor',
                    'group': 'Temperature',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 1,
                    'zone_type': 8,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_temperature_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'garage_door',
                    'friendly_name': 'Qolsys Panel My Tilt Sensor',
                    'group': 'garageTilt1',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 16,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_tilt_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My Keypad Sensor',
                    'group': 'fixedintrusion',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 4,
                    'zone_type': 104,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_keypad_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My Auxiliary Pendant Sensor',
                    'group': 'fixedmedical',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 1,
                    'zone_type': 21,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_auxiliary_pendant_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My Siren Sensor',
                    'group': 'Siren',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 14,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_siren_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My KeyFob Sensor',
                    'group': 'mobileintrusion',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 3,
                    'zone_type': 102,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_keyfob_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My TakeoverModule Sensor',
                    'group': 'takeovermodule',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 13,
                    'zone_type': 18,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_takeovermodule_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My Translator Sensor',
                    'group': 'translator',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 14,
                    'zone_type': 20,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_translator_sensor',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'vibration',
                    'friendly_name': 'Qolsys Panel My Shock Sensor',
                    'group': 'shock',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 12,
                    'zone_type': 107,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_shock_sensor',
                'state': 'off',
            },
        ]
        self._check_entity_states(ctx, expected_states, msg='Initial state')

    async def _check_panel_events(self, ctx):
        # Send events to change the different entities
        events = [
            {
                'event': 'INFO',
                'info_type': 'SECURE_ARM',
                'partition_id': 1,
                'value': True,
                'version': 1,
                'requestID': '<request_id>',
            },
            {
                # Just an unknown event to test if the last error gets updated
                'event': 'UNKNOWN',
            },
        ]

        closed_entities = [
            10000,
            10010,
            10011,
            10020,
            10021,
            10030,
            10040,
            10041,
            10050,
            20000,
            20001,
            20010,
            20020,
            20021,
            20030,
            20040,
            20050,
            20060,
            20070,
            20080,
            200802,
            20081,
            20090,
        ]
        open_entities = [
            10001,
        ]
        tamper_entities = [
            10000,
            10010,
            10011,
            20010,
        ]
        untamper_entities_to_open = [
            10000,
        ]
        untamper_entities_to_closed_short = [
            10010,
        ]
        untamper_entities_to_closed_long = [
            10011,
        ]

        def zone_active_event(zone_id, closed=False):
            return {
                'event': 'ZONE_EVENT',
                'zone_event_type': 'ZONE_ACTIVE',
                'version': 1,
                'zone': {
                    'zone_id': zone_id,
                    'status': 'Closed' if closed else 'Open',
                },
                'requestID': '<request_id>',
            }

        for zone_id in closed_entities + tamper_entities:
            events.append(zone_active_event(zone_id, closed=False))

        for zone_id in open_entities:
            events.append(zone_active_event(zone_id, closed=True))

        for zone_id in untamper_entities_to_closed_short:
            events.append(zone_active_event(zone_id, closed=True))
            events.append(zone_active_event(zone_id, closed=True))

        for zone_id in untamper_entities_to_open + untamper_entities_to_closed_long:
            # Open then closed in the same second = not anymore tampered
            events.append(zone_active_event(zone_id, closed=False))
            events.append(zone_active_event(zone_id, closed=True))

        for zone_id in untamper_entities_to_open:
            events.append(zone_active_event(zone_id, closed=False))

        for zone_id in untamper_entities_to_closed_long:
            events.append(zone_active_event(zone_id, closed=True))

        events.append({
            'event': 'ARMING',
            'arming_type': 'ARM_AWAY',
            'partition_id': 0,
            'version': 1,
            'requestID': '<request_id>',
        })

        events.append({
            'event': 'ERROR',
            'error_type': 'DISARM_FAILED',
            'partition_id': 0,
            'description': 'Invalid usercode',
            'nonce': 'qolsys',
            'version': 1,
            'requestID': '<request_id>',
        })

        events.append({
            'event': 'ALARM',
            'alarm_type': 'FIRE',
            'partition_id': 1,
            'version': 1,
            'requestID': '<request_id>',
        })

        for event in events:
            await ctx.panel.writeline(event)

        # Now wait for the side effet of the last event to happen
        await ctx.homeassistant.wait_for_entity(
            entity='alarm_control_panel.qolsys_panel_partition1',
            filters={'state': 'triggered'},
            timeout=self.TIMEOUT,
            raise_if_timeout=True,
        )

        # Check that the states of the entities in Home Assistant are as
        # we expect them to be at this point
        expected_states = [
            {
                'attributes': {
                    'device_class': 'timestamp',
                    'friendly_name': 'Qolsys Panel Last Error',
                    'type': 'UnknownQolsysEventException',
                    'desc': "Event type 'UNKNOWN' unsupported "
                            "for event {'event': 'UNKNOWN'}",
                },
                'entity_id': 'sensor.qolsys_panel_last_error',
                'state': ISODATE_S,
            },
            {
                'attributes': {
                    'alarm_type': None,
                    'changed_by': None,
                    'code_arm_required': False,
                    'code_format': 'number',
                    'friendly_name': 'Qolsys Panel partition0',
                    'last_error_at': ISODATE,
                    'last_error_type': 'DISARM_FAILED',
                    'last_error_desc': 'Invalid usercode',
                    'disarm_failed': 1,
                    'secure_arm': False,
                    'supported_features': 63,
                },
                'entity_id': 'alarm_control_panel.qolsys_panel_partition0',
                'state': 'armed_away',
            },
            {
                'attributes': {
                    'device_class': 'door',
                    'friendly_name': 'Qolsys Panel My Door',
                    'group': 'entryexitdelay',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 1,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_door',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'door',
                    'friendly_name': 'Qolsys Panel My Window',
                    'group': 'entryexitlongdelay',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 1,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_window',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'motion',
                    'friendly_name': 'Qolsys Panel My Motion',
                    'group': 'awayinstantmotion',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 2,
                    'zone_type': 2,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_motion',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'motion',
                    'friendly_name': 'Qolsys Panel Panel Motion',
                    'group': 'safetymotion',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 119,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_panel_motion',
                'state': 'off',
            },
            {
                'attributes': {
                    'device_class': 'vibration',
                    'friendly_name': 'Qolsys Panel My Glass Break',
                    'group': 'glassbreakawayonly',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 1,
                    'zone_type': 116,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_glass_break',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'vibration',
                    'friendly_name': 'Qolsys Panel Panel Glass Break',
                    'group': 'glassbreakawayonly',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 1,
                    'zone_type': 116,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_panel_glass_break',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'presence',
                    'friendly_name': 'Qolsys Panel My Phone',
                    'group': 'mobileintrusion',
                    'zone_alarm_type': 1,
                    'zone_physical_type': 1,
                    'zone_type': 115,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_phone',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'smoke',
                    'friendly_name': 'Qolsys Panel My Smoke Detector',
                    'group': 'smoke_heat',
                    'zone_alarm_type': 9,
                    'zone_physical_type': 9,
                    'zone_type': 5,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_smoke_detector',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'gas',
                    'friendly_name': 'Qolsys Panel My CO Detector',
                    'group': 'entryexitdelay',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 1,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_co_detector',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'moisture',
                    'friendly_name': 'Qolsys Panel My Water Detector',
                    'group': 'WaterSensor',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 8,
                    'zone_type': 15,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_water_detector',
                'state': 'on',
            },
            {
                'attributes': {
                    'alarm_type': 'FIRE',
                    'changed_by': None,
                    'code_arm_required': True,
                    'code_format': 'number',
                    'friendly_name': 'Qolsys Panel partition1',
                    'last_error_at': None,
                    'last_error_type': None,
                    'last_error_desc': None,
                    'disarm_failed': 0,
                    'secure_arm': True,
                    'supported_features': 63,
                },
                'entity_id': 'alarm_control_panel.qolsys_panel_partition1',
                'state': 'triggered',
            },
            {
                'attributes': {
                    'device_class': 'door',
                    'friendly_name': 'Qolsys Panel My 2nd Door',
                    'group': 'instantperimeter',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 1,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_2nd_door',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'sound',
                    'friendly_name': 'Qolsys Panel My Doorbell Sensor',
                    'group': 'localsafety',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 109,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_doorbell_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'cold',
                    'friendly_name': 'Qolsys Panel My Freeze Sensor',
                    'group': 'freeze',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 6,
                    'zone_type': 17,
                    'tampered': True,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_freeze_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'heat',
                    'friendly_name': 'Qolsys Panel My Heat Sensor',
                    'group': 'smoke_heat',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 10,
                    'zone_type': 8,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_heat_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'heat',
                    'friendly_name': 'Qolsys Panel My Temperature Sensor',
                    'group': 'Temperature',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 1,
                    'zone_type': 8,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_temperature_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'garage_door',
                    'friendly_name': 'Qolsys Panel My Tilt Sensor',
                    'group': 'garageTilt1',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 16,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_tilt_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My Keypad Sensor',
                    'group': 'fixedintrusion',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 4,
                    'zone_type': 104,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_keypad_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My Auxiliary Pendant Sensor',
                    'group': 'fixedmedical',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 1,
                    'zone_type': 21,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_auxiliary_pendant_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My Siren Sensor',
                    'group': 'Siren',
                    'zone_alarm_type': 3,
                    'zone_physical_type': 1,
                    'zone_type': 14,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_siren_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My KeyFob Sensor',
                    'group': 'mobileintrusion',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 3,
                    'zone_type': 102,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_keyfob_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My TakeoverModule Sensor',
                    'group': 'takeovermodule',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 13,
                    'zone_type': 18,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_takeovermodule_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'safety',
                    'friendly_name': 'Qolsys Panel My Translator Sensor',
                    'group': 'translator',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 14,
                    'zone_type': 20,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_translator_sensor',
                'state': 'on',
            },
            {
                'attributes': {
                    'device_class': 'vibration',
                    'friendly_name': 'Qolsys Panel My Shock Sensor',
                    'group': 'shock',
                    'zone_alarm_type': 0,
                    'zone_physical_type': 12,
                    'zone_type': 107,
                    'tampered': False,
                },
                'entity_id': 'binary_sensor.qolsys_panel_my_shock_sensor',
                'state': 'on',
            },
        ]
        self._check_entity_states(ctx, expected_states, msg='Panel events')

    async def _check_panel_actions(self, ctx):
        partition0 = 'alarm_control_panel.qolsys_panel_partition0'
        partition1 = 'alarm_control_panel.qolsys_panel_partition1'
        code = f'{random.randint(0, 999999)}'.zfill(6)

        # Arming partition 0 so we can test the disarm on it
        event = {
            'event': 'ARMING',
            'arming_type': 'ARM_AWAY',
            'partition_id': 0,
            'version': 1,
            'requestID': '<request_id>',
        }
        await ctx.panel.writeline(event)

        # Now wait for the side effect to happen
        await ctx.homeassistant.wait_for_entity(
            entity=partition0,
            filters={'state': 'armed_away'},
            timeout=self.TIMEOUT,
            raise_if_timeout=True,
        )

        with self.subTest(msg='Disarming a partition'):
            ha_call = ctx.homeassistant.alarm_disarm(partition0, code=code)
            self.assertTrue(ha_call.ok)

            action = await ctx.panel.wait_for_next_message(
                timeout=self.TIMEOUT,
                filters={'action': 'ARMING'},
                raise_on_timeout=True,
            )

            expected = {
                'nonce': 'qolsys',
                'source': 'C4',
                'version': 0,
                'action': 'ARMING',
                'arming_type': 'DISARM',
                'partition_id': '0',
                'token': self.PANEL_TOKEN,
                'usercode': code,
            }
            self.maxDiff = None
            self.assertDictEqual(expected, action)

        with self.subTest(msg='Arm away a partition'):
            ha_call = ctx.homeassistant.alarm_arm_away(partition1)
            self.assertTrue(ha_call.ok)

            action = await ctx.panel.wait_for_next_message(
                timeout=self.TIMEOUT,
                filters={'action': 'ARMING'},
                raise_on_timeout=True,
            )

            expected = {
                'nonce': 'qolsys',
                'source': 'C4',
                'version': 0,
                'action': 'ARMING',
                'arming_type': 'ARM_AWAY',
                'partition_id': '1',
                'token': self.PANEL_TOKEN,
            }
            self.maxDiff = None
            self.assertDictEqual(expected, action)

        with self.subTest(msg='Arm vacation a partition'):
            ha_call = ctx.homeassistant.alarm_arm_vacation(partition1)
            self.assertTrue(ha_call.ok)

            action = await ctx.panel.wait_for_next_message(
                timeout=self.TIMEOUT,
                filters={'action': 'ARMING'},
                raise_on_timeout=True,
            )

            expected = {
                'nonce': 'qolsys',
                'source': 'C4',
                'version': 0,
                'action': 'ARMING',
                'arming_type': 'ARM_AWAY',
                'partition_id': '1',
                'token': self.PANEL_TOKEN,
            }
            self.maxDiff = None
            self.assertDictEqual(expected, action)

        with self.subTest(msg='Arm home a partition'):
            ha_call = ctx.homeassistant.alarm_arm_home(partition1)
            self.assertTrue(ha_call.ok)

            action = await ctx.panel.wait_for_next_message(
                timeout=self.TIMEOUT,
                filters={'action': 'ARMING'},
                raise_on_timeout=True,
            )

            expected = {
                'nonce': 'qolsys',
                'source': 'C4',
                'version': 0,
                'action': 'ARMING',
                'arming_type': 'ARM_STAY',
                'partition_id': '1',
                'token': self.PANEL_TOKEN,
            }
            self.maxDiff = None
            self.assertDictEqual(expected, action)

        with self.subTest(msg='Arm night a partition'):
            ha_call = ctx.homeassistant.alarm_arm_night(partition1)
            self.assertTrue(ha_call.ok)

            action = await ctx.panel.wait_for_next_message(
                timeout=self.TIMEOUT,
                filters={'action': 'ARMING'},
                raise_on_timeout=True,
            )

            expected = {
                'nonce': 'qolsys',
                'source': 'C4',
                'version': 0,
                'action': 'ARMING',
                'arming_type': 'ARM_STAY',
                'partition_id': '1',
                'token': self.PANEL_TOKEN,
            }
            self.maxDiff = None
            self.assertDictEqual(expected, action)

        with self.subTest(msg='Trigger alarm on partition'):
            ha_call = ctx.homeassistant.alarm_trigger(partition0)
            self.assertTrue(ha_call.ok)

            action = await ctx.panel.wait_for_next_message(
                timeout=self.TIMEOUT,
                filters={'action': 'ALARM'},
                raise_on_timeout=True,
            )

            expected = {
                'nonce': 'qolsys',
                'source': 'C4',
                'version': 0,
                'action': 'ALARM',
                'alarm_type': 'POLICE',
                'partition_id': '0',
                'token': self.PANEL_TOKEN,
            }
            self.maxDiff = None
            self.assertDictEqual(expected, action)

    async def test_endtoend_setup_and_run(self):
        async with self.get_context() as ctx:
            with self.subTest(msg='Initial state is correctly reflected in Home Assistant'):
                await self._check_initial_state(ctx)

            with self.subTest(msg='Home Assistant interactions lead to Panel actions'):
                await self._check_panel_actions(ctx)

            with self.subTest(msg='Panel events lead to updates in Home Assistant'):
                await self._check_panel_events(ctx)
