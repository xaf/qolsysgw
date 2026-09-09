import json
import logging

from appdaemon.plugins.mqtt.mqttapi import Mqtt

from qolsys.control import QolsysControl
from qolsys.events import QolsysEvent
from qolsys.exceptions import UnknownQolsysControlException
from qolsys.exceptions import UnknownQolsysEventException
from qolsys.utils import defaultLoggerCallback


LOGGER = logging.getLogger(__name__)


def _topic_matches_filter(topic: str, topic_filter: str) -> bool:
    """Return whether an MQTT `topic` matches a subscription `topic_filter`.

    Implements the MQTT wildcard rules: `+` matches exactly one level, and `#`
    matches the remaining levels.
    """
    if topic_filter == '#':
        return True

    filter_levels = topic_filter.split('/')
    topic_levels = topic.split('/')

    for i, level in enumerate(filter_levels):
        if level == '#':
            # Multi-level wildcard matches the rest of the topic
            return True
        if i >= len(topic_levels):
            return False
        if level == '+':
            # Single-level wildcard matches any one level
            continue
        if level != topic_levels[i]:
            return False

    return len(filter_levels) == len(topic_levels)


def _topic_covered_by_client_topics(topic: str, client_topics) -> bool:
    """Return whether `topic` is already subscribed to by the MQTT plugin.

    The plugin subscribes to every entry of its `client_topics` configuration
    when it connects. That value defaults to `['#']` (everything), and the
    `NONE` sentinel means it subscribes to nothing. When it is not reported at
    all we assume the default, hence that the topic is covered.

    Note that an exact string comparison is not enough: the default `#` covers
    our topic without being equal to it. AppDaemon's own subscribe service
    only dedupes on exact equality, so it will happily add a second,
    overlapping subscription -- which is what makes the broker deliver every
    message twice.
    """
    if client_topics is None:
        return True

    if isinstance(client_topics, str):
        client_topics = [client_topics]

    return any(
        entry.upper() != 'NONE' and _topic_matches_filter(topic, entry)
        for entry in client_topics
        if isinstance(entry, str)
    )


class MqttListener(object):
    def __init__(self, app: Mqtt, namespace: str, topic: str,
                 callback: callable = None, logger=None,
                 client_topics=None):
        self._callback = callback or defaultLoggerCallback
        self._logger = logger or LOGGER

        # listen_event() only filters the events the MQTT plugin already
        # emits; it does not subscribe at the broker. So the subscription has
        # to exist, or we receive nothing at all whenever `client_topics` does
        # not cover our topic (#208). But subscribing when it *is* covered
        # leaves two overlapping subscriptions, and the broker then delivers
        # every message twice -- which double-counts state updates, showing
        # sensors as tampered and inflating counters (#200).
        if not _topic_covered_by_client_topics(topic, client_topics):
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
