import asyncio

import testenv  # noqa: F401
from testbase import TestQolsysGatewayBase
from testutils.mock_types import ISODATE

from gateway import QolsysGateway
from mqtt.exceptions import MqttPluginUnavailableException


class TestIntegrationQolsysGateway(TestQolsysGatewayBase):

    async def test_integration_gateway_raise_proper_error_if_mqtt_plugin_unavailable(self):
        # Initialize a gateway instance to connect to that panel
        gw = QolsysGateway()
        gw.args = {
            'panel_host': 'localhost',
            'panel_token': '<panel_token>',
        }

        # Override what will be returned as plugins
        gw.PLUGIN_CONFIG = None

        with self.assertRaises(MqttPluginUnavailableException):
            await gw.initialize()

    async def test_integration_gateway_sends_info_message_on_connection(self):
        panel, gw, info = await self._init_panel_and_gw_and_wait(
            return_info=True,
        )

        # Make sure that we got the message, and not a timeout
        self.assertIsNotNone(info)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_gateway_waits_from_start_of_messages(self):
        calls = []

        class MockPanel:
            async def wait_for_next_message(self, **kwargs):
                calls.append(kwargs)
                return {'action': 'INFO'}

        panel = MockPanel()
        gw = object()

        async def mock_init_panel_and_gw(**kwargs):
            return panel, gw

        self._init_panel_and_gw = mock_init_panel_and_gw

        await self._init_panel_and_gw_and_wait()
        await self._init_panel_and_gw_and_wait(return_info=True)

        self.assertDictEqual(
            {
                'timeout': self._TIMEOUT,
                'raise_on_timeout': True,
                'startpos': 0,
            },
            calls[0],
        )
        self.assertDictEqual(
            {
                'timeout': self._TIMEOUT,
                'filters': {'action': 'INFO'},
                'startpos': 0,
            },
            calls[1],
        )

    async def test_integration_gateway_stays_connected_on_non_json_data(self):
        panel, gw = await self._init_panel_and_gw_and_wait()

        await panel.writeline('blah')
        await asyncio.sleep(self._TIMEOUT)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_gateway_stays_connected_on_unknown_json_data(self):
        panel, gw = await self._init_panel_and_gw_and_wait()

        await panel.writeline({'not': 'expected'})
        await asyncio.sleep(self._TIMEOUT)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_gateway_publish_error_on_unknown_json_data(self):
        panel, gw = await self._init_panel_and_gw_and_wait()

        data = {'not': 'expected'}
        await panel.writeline(data)

        topic_prefix = 'homeassistant/sensor/qolsys_panel_last_error'

        state = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': f'{topic_prefix}/state'},
            raise_on_timeout=True,
        )

        attributes = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': f'{topic_prefix}/attributes'},
            raise_on_timeout=True,
            continued=True,
        )

        self.assertEqual(ISODATE, state['payload'])
        self.assertJsonDictEqual(
            {
                'type': 'UnknownQolsysEventException',
                'desc': f'Event type not found for event {data}',
            },
            attributes['payload'],
        )

    async def test_integration_gateway_stays_connected_on_unknown_event_type(self):
        panel, gw = await self._init_panel_and_gw_and_wait()

        await panel.writeline({'event': 'unknown'})
        await asyncio.sleep(self._TIMEOUT)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_gateway_publish_error_on_unknown_event_type(self):
        panel, gw = await self._init_panel_and_gw_and_wait()

        data = {'event': 'unknown'}
        await panel.writeline(data)

        topic_prefix = 'homeassistant/sensor/qolsys_panel_last_error'

        state = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': f'{topic_prefix}/state'},
            raise_on_timeout=True,
        )

        attributes = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': f'{topic_prefix}/attributes'},
            raise_on_timeout=True,
            continued=True,
        )

        self.assertEqual(ISODATE, state['payload'])
        self.assertJsonDictEqual(
            {
                'type': 'UnknownQolsysEventException',
                'desc': f"Event type '{data['event']}' unsupported for event {data}",
            },
            attributes['payload'],
        )
