import asyncio
import logging
import uuid

from unittest import mock
from copy import deepcopy

from testutils.utils import MessageStorage
from appdaemon.utils import sync_wrapper


LOGGER = logging.getLogger(__name__)


class ADBase(object):
    def __init__(self, *args, **kwargs):
        self.name = uuid.uuid4()

    def get_ad_api(self):
        raise RuntimeError('Not defined yet')

    async def get_plugin_api(self, plugin_name):
        raise RuntimeError('Not defined yet')

    def register_constraint(self, name):
        raise RuntimeError('Not defined yet')

    def deregister_constraint(self, name):
        raise RuntimeError('Not defined yet')

    def list_constraints(self):
        raise RuntimeError('Not defined yet')


class ADAPI(object):

    CAPTURED_LOGS = MessageStorage(name='log', match_check_key='message')
    PLUGIN_CONFIG = {
        'birth_topic': 'appdaemon/birth_and_will',
        'will_topic': 'appdaemon/birth_and_will',
        'birth_payload': 'online',
        'will_payload': 'offline',
    }

    def log(self, msg, *args, **kwargs):
        log = dict(kwargs.items())

        log['message'] = msg

        for i, v in enumerate(args):
            log[f'arg{i}'] = v

        self.CAPTURED_LOGS.append(log)

    def error(self, msg, *args, **kwargs):
        self.log(msg, *args, level='ERROR', **kwargs)

    @sync_wrapper
    async def create_task(self, coro, callback=None, **kwargs):
        if callback is not None:
            raise RuntimeError('Not defined yet')

        return asyncio.create_task(coro)

    def get_ad_version(self):
        return '4.5.2'

    async def get_plugin_config(self, **kwargs):
        return deepcopy(self.PLUGIN_CONFIG)

    async def wait_for_next_log(self, *args, **kwargs):
        return await self.CAPTURED_LOGS.wait_for_next(*args, **kwargs)


class Mqtt(ADBase, ADAPI):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.SUBSCRIBED_TO = []
        self.PUBLISHED = MessageStorage(name='publish')
        self.LISTEN_EVENT = []

        self.mqtt_publish_func = mock.Mock(name='mqtt_publish')

    @sync_wrapper
    async def listen_event(self, callback, event=None, **kwargs):
        listen_event = deepcopy(kwargs)
        listen_event['callback'] = callback
        listen_event['event'] = event

        self.LISTEN_EVENT.append(listen_event)

        LOGGER.debug(f'listen_event: event={event} callback={callback} kwargs={kwargs}')

    @sync_wrapper
    async def mqtt_publish(self, topic, payload=None, **kwargs):
        published = deepcopy(kwargs)
        published['topic'] = topic
        published['payload'] = payload

        # Store the messages in case we might need them
        self.PUBLISHED.append(published)

        # Let's use a mock function that we forward the call to, so we can
        # then use it for assertions in the tests
        self.mqtt_publish_func(topic, payload, **kwargs)

        # In case we want to follow the logs of what happens in our mock
        LOGGER.debug(f'publishing: topic={topic} payload={payload} kwargs={kwargs}')

        # Let's go through the LISTEN_EVENT data and check if we have
        # any LISTEN_EVENT with MQTT_MESSAGE as event, for the same topic,
        # and in which case we can call the callback
        for listener in self.LISTEN_EVENT:
            if listener['event'] != 'MQTT_MESSAGE' or listener['topic'] != topic:
                continue

            # This is not at all complete, as we only put the payload in the
            # data and give nothing for the kwargs, but that's sufficient for
            # out mock here
            await listener['callback']('MQTT_MESSAGE', {'payload': payload}, {})

    def mqtt_subscribe(self, topic, **kwargs):
        subscribe = deepcopy(kwargs)
        subscribe['topic'] = topic

        self.SUBSCRIBED_TO.append(subscribe)

        LOGGER.debug(f'subscribed: topic={topic} kwargs={kwargs}')

    def mqtt_unsubscribe(self, topic, **kwargs):
        subscribe = deepcopy(kwargs)
        subscribe['topic'] = topic

        self.SUBSCRIBED_TO.remove(subscribe)

    async def is_client_connected(self, **kwargs):
        raise RuntimeError('Not defined yet')

    async def find_last_mqtt_publish(self, *args, **kwargs):
        return await self.PUBLISHED.find_last(*args, **kwargs)

    async def wait_for_next_mqtt_publish(self, *args, **kwargs):
        return await self.PUBLISHED.wait_for_next(*args, **kwargs)
