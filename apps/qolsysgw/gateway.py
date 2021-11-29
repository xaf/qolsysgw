import asyncio
import logging
import sys
import traceback
import uuid

from appdaemon.plugins.mqtt.mqttapi import Mqtt

from mqtt.listener import MqttQolsysEventListener
from mqtt.listener import MqttQolsysControlListener
from mqtt.updater import MqttUpdater
from mqtt.updater import MqttWrapperFactory

from qolsys.actions import QolsysAction
from qolsys.config import QolsysGatewayConfig
from qolsys.control import QolsysControl
from qolsys.events import QolsysEvent
from qolsys.events import QolsysEventAlarm
from qolsys.events import QolsysEventArming
from qolsys.events import QolsysEventInfo
from qolsys.events import QolsysEventZoneEventActive
from qolsys.events import QolsysEventZoneEventUpdate
from qolsys.exceptions import MissingDisarmCodeException
from qolsys.socket import QolsysSocket
from qolsys.state import QolsysState


LOGGER = logging.getLogger(__name__)


class AppDaemonLoggingHandler(logging.Handler):
    def __init__(self, app):
        super().__init__()
        self._app = app

    def emit(self, record):
        message = record.getMessage()
        if record.exc_info:
            message += '\nTraceback (most recent call last):\n'
            message += '\n'.join(traceback.format_tb(record.exc_info[2]))
            message += f'{record.exc_info[0].__name__}: {record.exc_info[1]}'
        self._app.log(message, level=record.levelname)


class QolsysGateway(Mqtt):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._qolsys_socket = None
        self._factory = None
        self._state = None
        self._redirect_logging()

    def _redirect_logging(self):
        # Add a handler for the logging module that will convert the
        # calls to AppDaemon's logger with the self instance, so that
        # we can simply use logging in the rest of the application
        rlogger = logging.getLogger()
        rlogger.handlers = [
            h for h in rlogger.handlers
            if type(h).__name__ != AppDaemonLoggingHandler.__name__
        ]
        rlogger.addHandler(AppDaemonLoggingHandler(self))

        # We want to grab all the logs, AppDaemon will
        # then care about filtering those we asked for
        rlogger.setLevel(logging.DEBUG)

    async def initialize(self):
        LOGGER.info('Starting')

        cfg = self._cfg = QolsysGatewayConfig(self.args)
        mqtt_plugin_cfg = await self.get_plugin_config(namespace=cfg.mqtt_namespace)
        self._session_token = str(uuid.uuid4())

        self._factory = MqttWrapperFactory(
            mqtt_publish=self.mqtt_publish,
            cfg=cfg,
            mqtt_plugin_cfg=mqtt_plugin_cfg,
            session_token=self._session_token,
        )

        self._state = QolsysState()
        try:
            self._factory.wrap(self._state).set_unavailable()
        except:
            LOGGER.exception('Error setting state unavailable; pursuing')

        mqtt_updater = MqttUpdater(
            state=self._state,
            factory=self._factory
        )

        mqtt_event_listener = MqttQolsysEventListener(
            app=self,
            namespace=cfg.mqtt_namespace,
            topic=cfg.event_topic,
            callback=self.mqtt_event_callback,
        )

        mqtt_control_listener = MqttQolsysControlListener(
            app=self,
            namespace=cfg.mqtt_namespace,
            topic=cfg.control_topic,
            callback=self.mqtt_control_callback,
        )

        self._qolsys_socket = QolsysSocket(
            hostname=cfg.panel_host,
            port=cfg.panel_port,
            token=cfg.panel_token,
            callback=self.qolsys_event_callback,
            connected_callback=self.qolsys_connected_callback,
            disconnected_callback=self.qolsys_disconnected_callback,
        )
        self.create_task(self._qolsys_socket.listen())
        self.create_task(self._qolsys_socket.keep_alive())

        LOGGER.info('Started')

    async def terminate(self):
        LOGGER.info('Terminating')

        if not self._state or not self._factory:
            LOGGER.info('No state or factory, nothing to terminate.')
            return

        self._factory.wrap(self._state).set_unavailable()

        for partition in self._state.partitions:
            for sensor in partition.sensors:
                try:
                    self._factory.wrap(sensor).set_unavailable()
                except:
                    LOGGER.exception(f"Error setting sensor '{sensor.id}' "\
                            f"({sensor.name}) unavailable")

            try:
                self._factory.wrap(partition).set_unavailable()
            except:
                LOGGER.exception(f"Error setting partition '{partition.id}' "\
                        f"({partition.name}) unavailable")

        LOGGER.info('Terminated')

    async def qolsys_connected_callback(self):
        LOGGER.debug(f'Qolsys callback for connection event')
        self._factory.wrap(self._state).set_available()

    async def qolsys_disconnected_callback(self):
        LOGGER.debug(f'Qolsys callback for disconnection event')
        self._factory.wrap(self._state).set_unavailable()

    async def qolsys_event_callback(self, event: QolsysEvent):
        LOGGER.debug(f'Qolsys callback for event: {event}')
        await self.mqtt_publish(
            namespace=self._cfg.mqtt_namespace,
            topic=self._cfg.event_topic,
            payload=event.raw_str,
        )

    async def mqtt_event_callback(self, event: QolsysEvent):
        LOGGER.debug(f'MQTT callback for event: {event}')

        if isinstance(event, QolsysEventInfo):
            self._state.update(event)

        elif isinstance(event, QolsysEventZoneEventActive):
            LOGGER.debug(f'ACTIVE zone={event.zone}')

            if event.zone.status.lower() == 'open':
                self._state.zone_open(event.zone.id)
            else:
                self._state.zone_closed(event.zone.id)

        elif isinstance(event, QolsysEventZoneEventUpdate):
            LOGGER.debug(f'UPDATE zone={event.zone}')

            self._state.zone_update(event.zone)

        elif isinstance(event, QolsysEventArming):
            LOGGER.debug(f'ARMING partition_id={event.partition_id} '\
                         f'status={event.arming_type}')

            partition = self._state.partition(event.partition_id)
            if partition is None:
                LOGGER.warning(f'Partition {event.partition_id} not found')
                return

            partition.status = event.arming_type

        elif isinstance(event, QolsysEventAlarm):
            LOGGER.debug(f'ALARM partition_id={event.partition_id}')

            partition = self._state.partition(event.partition_id)
            if partition is None:
                LOGGER.warning(f'Partition {event.partition_id} not found')
                return

            partition.triggered()

    async def mqtt_control_callback(self, control: QolsysControl):
        if control.session_token != self._session_token:
            LOGGER.error(f'invalid session token for {control}')
            return

        if control.requires_config:
            control.configure(self._cfg)

        try:
            control.check
        except MissingDisarmCodeException as e:
            LOGGER.error(f'{e} for control event {control}')
            return

        action = control.action
        if action is None:
            LOGGER.info(f'Action missing for control event {control}')
            return

        await self._qolsys_socket.send(action)

