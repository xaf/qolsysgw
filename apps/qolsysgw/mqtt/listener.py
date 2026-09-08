import json
import logging

from appdaemon.plugins.mqtt.mqttapi import Mqtt

from qolsys.control import QolsysControl
from qolsys.events import QolsysEvent
from qolsys.exceptions import UnknownQolsysControlException
from qolsys.exceptions import UnknownQolsysEventException
from qolsys.utils import defaultLoggerCallback


LOGGER = logging.getLogger(__name__)


class MqttListener(object):
    def __init__(self, app: Mqtt, namespace: str, topic: str,
                 callback: callable = None, logger=None):
        self._callback = callback or defaultLoggerCallback
        self._logger = logger or LOGGER

        app.mqtt_subscribe(topic, namespace=namespace)
        app.listen_event(self.event_callback, event='MQTT_MESSAGE',
                         topic=topic, namespace=namespace)


class MqttQolsysEventListener(MqttListener):
    async def event_callback(self, event_name, data, kwargs):
        self._logger.debug(f'Received {event_name} with data={data} and kwargs={kwargs}')

        event_str = data.get('payload')
        if not event_str:
            self._logger.warning('Received empty event: {data}')
            return

        try:
            # We try to parse the event to one of our event classes
            event = QolsysEvent.from_json(event_str)
        except json.decoder.JSONDecodeError:
            self._logger.debug(f'Data is not JSON: {data}')
            return
        except UnknownQolsysEventException:
            self._logger.debug(f'Unknown Qolsys event: {data}')
            return

        try:
            await self._callback(event)
        except:  # noqa: E722
            self._logger.exception(f'Error calling callback for event: {event}')


class MqttQolsysControlListener(MqttListener):
    async def event_callback(self, event_name, data, kwargs):
        self._logger.debug(f'Received {event_name} with data={data} '
                           f'and kwargs={kwargs}')

        control_str = data.get('payload')
        if not control_str:
            self._logger.warning('Received empty control: {data}')
            return

        try:
            # We try to parse the event to one of our event classes
            control = QolsysControl.from_json(control_str)
        except json.decoder.JSONDecodeError:
            self._logger.debug(f'Data is not JSON: {data}')
            return
        except UnknownQolsysControlException:
            self._logger.debug(f'Unknown Qolsys control: {data}')
            return

        try:
            await self._callback(control)
        except:  # noqa: E722
            self._logger.exception(f'Error calling callback for control: {control}')
