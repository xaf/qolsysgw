import unittest

from unittest import mock

import tests.unit.qolsysgw.mqtt.testenv  # noqa: F401

from mqtt.listener import MqttListener
from mqtt.listener import MqttQolsysControlListener
from mqtt.listener import MqttQolsysEventListener


class _OrderRecordingListener(MqttListener):
    async def event_callback(self, event_name, data, kwargs):  # pragma: no cover
        pass


# test MqttListener subscription behavior
#
# listen_event(event='MQTT_MESSAGE') only filters the events the MQTT plugin
# already emits; it does not subscribe at the broker. Both directions are
# broken by getting this wrong:
#
#  - never subscribing silently kills all MQTT input for anyone whose
#    `client_topics` does not cover our topic (issue #208);
#  - always subscribing leaves two overlapping subscriptions when it *does*
#    cover it, so the broker delivers every message twice, which double
#    applies state updates (false `tampered`, inflated counters -- #200).
class TestUnitMqttListenerSubscription(unittest.TestCase):

    def _listen_event_call(self, listener):
        return mock.call.listen_event(
            listener.event_callback,
            event='MQTT_MESSAGE',
            topic='test_topic',
            namespace='test_namespace')

    def test_unit_subscribes_when_topic_not_covered_by_client_topics(self):
        # client_topics is restricted and does not cover our topic (#208)
        app = mock.Mock()

        listener = _OrderRecordingListener(
            app=app,
            namespace='test_namespace',
            topic='test_topic',
            client_topics=['some/other/topic'],
        )

        # mqtt_subscribe must be called first, then listen_event, with the
        # exact arguments each expects
        self.assertEqual(
            app.mock_calls,
            [
                mock.call.mqtt_subscribe(
                    'test_topic', namespace='test_namespace'),
                self._listen_event_call(listener),
            ],
        )

    def test_unit_subscribes_when_client_topics_is_empty(self):
        # `client_topics: NONE` is normalized to an empty list by AppDaemon,
        # so the plugin subscribes to nothing at all -- this is the exact
        # configuration reported in #208
        app = mock.Mock()

        _OrderRecordingListener(
            app=app,
            namespace='test_namespace',
            topic='test_topic',
            client_topics=[],
        )

        app.mqtt_subscribe.assert_called_once_with(
            'test_topic', namespace='test_namespace')

    def test_unit_subscribes_when_client_topics_disabled(self):
        # Some versions report the raw `NONE` sentinel instead of a list
        app = mock.Mock()

        _OrderRecordingListener(
            app=app,
            namespace='test_namespace',
            topic='test_topic',
            client_topics='NONE',
        )

        app.mqtt_subscribe.assert_called_once_with(
            'test_topic', namespace='test_namespace')

    def test_unit_does_not_subscribe_when_client_topics_is_wildcard(self):
        # client_topics is the AppDaemon default wildcard -> already covered
        app = mock.Mock()

        listener = _OrderRecordingListener(
            app=app,
            namespace='test_namespace',
            topic='test_topic',
            client_topics=['#'],
        )

        # only listen_event; subscribing again would duplicate every message
        self.assertEqual(app.mock_calls, [self._listen_event_call(listener)])
        app.mqtt_subscribe.assert_not_called()

    def test_unit_does_not_subscribe_when_client_topics_unknown(self):
        # Not reported at all -> assume AppDaemon's default wildcard
        app = mock.Mock()

        listener = _OrderRecordingListener(
            app=app,
            namespace='test_namespace',
            topic='test_topic',
        )

        self.assertEqual(app.mock_calls, [self._listen_event_call(listener)])
        app.mqtt_subscribe.assert_not_called()

    def test_unit_does_not_subscribe_when_covered_by_prefix_wildcard(self):
        # A prefix multi-level wildcard that covers our topic, as would be
        # used to restrict the plugin to the Home Assistant topics
        app = mock.Mock()

        _OrderRecordingListener(
            app=app,
            namespace='test_namespace',
            topic='homeassistant/alarm_control_panel/panel/set',
            client_topics=['homeassistant/#'],
        )

        app.mqtt_subscribe.assert_not_called()

    def test_unit_subscribes_when_only_a_sibling_wildcard_is_covered(self):
        # A wildcard that does not cover our topic must still subscribe
        app = mock.Mock()

        _OrderRecordingListener(
            app=app,
            namespace='test_namespace',
            topic='qolsys/panel/event',
            client_topics=['homeassistant/#', 'other/+/thing'],
        )

        app.mqtt_subscribe.assert_called_once_with(
            'qolsys/panel/event', namespace='test_namespace')


# test MqttQolsysEventListener
class TestUnitMqttQolsysEventListener(unittest.IsolatedAsyncioTestCase):

    async def test_unit_event_callback_on_success(self):
        # mock event_callback
        event_callback = mock.AsyncMock()
        # mock Mqtt object
        mqtt = mock.Mock()
        # create MqttQolsysEventListener
        listener = MqttQolsysEventListener(
            app=mqtt,
            namespace='test_namespace',
            topic='test_topic',
            callback=event_callback,
        )
        # mock event_name
        event_name = 'MQTT_MESSAGE'
        # mock event_data
        event_data = {
            'topic': 'test_topic',
            'payload': 'test_payload',
        }
        # call event_callback
        qolsys_event = object()
        with mock.patch('qolsys.events.QolsysEvent.from_json', return_value=qolsys_event):
            await listener.event_callback(event_name, event_data, {})
        # assert event_callback was called
        event_callback.assert_called_once_with(qolsys_event)

    async def test_unit_event_callback_on_empty_data(self):
        # mock event_callback
        event_callback = mock.AsyncMock()
        # mock Mqtt object
        mqtt = mock.Mock()
        # create MqttQolsysEventListener
        listener = MqttQolsysEventListener(
            app=mqtt,
            namespace='test_namespace',
            topic='test_topic',
            callback=event_callback,
        )
        # mock event_name
        event_name = 'MQTT_MESSAGE'
        # mock event_data
        event_data = {}
        # call event_callback
        await listener.event_callback(event_name, event_data, {})
        # assert event_callback was not called
        event_callback.assert_not_called()

    async def test_unit_event_callback_on_unhandled_failure(self):
        # mock event_callback
        event_callback = mock.AsyncMock()
        # mock Mqtt object
        mqtt = mock.Mock()
        # create MqttQolsysEventListener
        listener = MqttQolsysEventListener(
            app=mqtt,
            namespace='test_namespace',
            topic='test_topic',
            callback=event_callback,
        )
        # mock event_name
        event_name = 'MQTT_MESSAGE'
        # mock event_data
        event_data = {
            'topic': 'test_topic',
            'payload': 'test_payload',
        }
        # mock QolsysEvent.from_json
        QolsysEvent = mock.Mock()
        QolsysEvent.from_json.side_effect = Exception('test_exception')
        # call event_callback
        await listener.event_callback(event_name, event_data, {})
        # assert event_callback was not called
        event_callback.assert_not_called()


# test MqttQolsysControlListener
class TestUnitMqttQolsysControlListener(unittest.IsolatedAsyncioTestCase):

    async def test_unit_event_callback_on_success(self):
        # mock event_callback
        event_callback = mock.AsyncMock()
        # mock Mqtt object
        mqtt = mock.Mock()
        # create MqttQolsysControlListener
        listener = MqttQolsysControlListener(
            app=mqtt,
            namespace='test_namespace',
            topic='test_topic',
            callback=event_callback,
        )
        # mock event_name
        event_name = 'MQTT_MESSAGE'
        # mock event_data
        event_data = {
            'topic': 'test_topic',
            'payload': 'test_payload',
        }
        # call event_callback
        qolsys_control = object()
        with mock.patch('qolsys.control.QolsysControl.from_json', return_value=qolsys_control):
            await listener.event_callback(event_name, event_data, {})
        # assert event_callback was called
        event_callback.assert_called_once_with(qolsys_control)

    async def test_unit_event_callback_on_empty_data(self):
        # mock event_callback
        event_callback = mock.AsyncMock()
        # mock Mqtt object
        mqtt = mock.Mock()
        # create MqttQolsysControlListener
        listener = MqttQolsysControlListener(
            app=mqtt,
            namespace='test_namespace',
            topic='test_topic',
            callback=event_callback,
        )
        # mock event_name
        event_name = 'MQTT_MESSAGE'
        # mock event_data
        event_data = {}
        # call event_callback
        await listener.event_callback(event_name, event_data, {})
        # assert event_callback was not called
        event_callback.assert_not_called()

    async def test_unit_event_callback_on_unhandled_failure(self):
        # mock event_callback
        event_callback = mock.AsyncMock()
        # mock Mqtt object
        mqtt = mock.Mock()
        # create MqttQolsysControlListener
        listener = MqttQolsysControlListener(
            app=mqtt,
            namespace='test_namespace',
            topic='test_topic',
            callback=event_callback,
        )
        # mock event_name
        event_name = 'MQTT_MESSAGE'
        # mock event_data
        event_data = {
            'topic': 'test_topic',
            'payload': 'test_payload',
        }
        # mock QolsysEvent.from_json
        QolsysEvent = mock.Mock()
        QolsysEvent.from_json.side_effect = Exception('test_exception')
        # call event_callback
        await listener.event_callback(event_name, event_data, {})
        # assert event_callback was not called
        event_callback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
