import json
import unittest

from datetime import datetime

import tests.unit.qolsysgw.mqtt.testenv  # noqa: F401

from mqtt.exceptions import MqttException
from mqtt.updater import MqttUpdater
from mqtt.updater import MqttWrapperFactory
from qolsys.config import QolsysGatewayConfig
from qolsys.exceptions import QolsysException
from qolsys.state import QolsysState


class TestUnitMqttLastError(unittest.TestCase):

    def setUp(self):
        self.addCleanup(setattr, QolsysException, 'STATE', QolsysException.STATE)
        self.addCleanup(setattr, MqttException, 'STATE', MqttException.STATE)
        self.messages = []
        self.state = QolsysState()
        self.factory = MqttWrapperFactory(
            mqtt_publish=lambda **message: self.messages.append(message),
            cfg=QolsysGatewayConfig(check=False),
            mqtt_plugin_cfg={
                'birth_topic': 'appdaemon',
                'will_topic': 'appdaemon',
                'birth_payload': 'online',
                'will_payload': 'offline',
            },
            session_token='TestSessionToken',
        )
        self.updater = MqttUpdater(self.state, self.factory)

    def last_message(self, suffix):
        topic = f'homeassistant/sensor/qolsys_panel_last_error/{suffix}'
        return [message for message in self.messages if message['topic'] == topic][-1]

    def test_unit_startup_without_error_publishes_unknown_timestamp(self):
        self.factory.wrap(self.state).configure()

        message = self.last_message('state')
        self.assertEqual(message['payload'], 'None')
        self.assertTrue(message['retain'])
        self.assertEqual(
            json.loads(self.last_message('attributes')['payload']),
            {'type': None, 'desc': None},
        )

    def test_unit_real_error_preserves_timestamp_and_details(self):
        error = QolsysException('Test connection failure')

        payload = self.last_message('state')['payload']
        self.assertEqual(payload, error.at)
        self.assertIsNotNone(datetime.fromisoformat(payload).tzinfo)
        self.assertEqual(
            json.loads(self.last_message('attributes')['payload']),
            {'type': 'QolsysException', 'desc': 'Test connection failure'},
        )

    def test_unit_clearing_error_replaces_retained_timestamp_with_unknown(self):
        QolsysException('Test connection failure')
        self.messages.clear()

        self.state.last_exception = None

        message = self.last_message('state')
        self.assertEqual(message['payload'], 'None')
        self.assertTrue(message['retain'])
        self.assertEqual(
            json.loads(self.last_message('attributes')['payload']),
            {'type': None, 'desc': None},
        )
