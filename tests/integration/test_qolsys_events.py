from copy import deepcopy
from types import SimpleNamespace

from unittest import mock

import testenv  # noqa: F401
from testbase import TestQolsysGatewayBase

from testutils.mock_types import ISODATE

from qolsys.sensors import QolsysSensorAuxiliaryPendant
from qolsys.sensors import QolsysSensorBluetooth
from qolsys.sensors import QolsysSensorCODetector
from qolsys.sensors import QolsysSensorDoorWindow
from qolsys.sensors import QolsysSensorDoorbell
from qolsys.sensors import QolsysSensorFreeze
from qolsys.sensors import QolsysSensorGlassBreak
from qolsys.sensors import QolsysSensorHeat
from qolsys.sensors import QolsysSensorKeyFob
from qolsys.sensors import QolsysSensorKeypad
from qolsys.sensors import QolsysSensorMotion
from qolsys.sensors import QolsysSensorPanelGlassBreak
from qolsys.sensors import QolsysSensorPanelMotion
from qolsys.sensors import QolsysSensorShock
from qolsys.sensors import QolsysSensorSiren
from qolsys.sensors import QolsysSensorSmokeDetector
from qolsys.sensors import QolsysSensorTakeoverModule
from qolsys.sensors import QolsysSensorTemperature
from qolsys.sensors import QolsysSensorTilt
from qolsys.sensors import QolsysSensorTranslator
from qolsys.sensors import QolsysSensorWater
from qolsys.sensors import QolsysSensorTamperSensor


class TestIntegrationQolsysEvents(TestQolsysGatewayBase):

    async def _check_partition_mqtt_messages(self, gw, partition_flat_name,
                                             partition_state, expected_state):
        state = partition_state

        mqtt_prefix = ('homeassistant/alarm_control_panel/'
                       f'qolsys_panel/{partition_flat_name}')

        with self.subTest(msg=f'MQTT config of partition {state.id} is correct'):
            mqtt_config = await gw.find_last_mqtt_publish(
                filters={'topic': f'{mqtt_prefix}/config'},
                raise_if_not_found=True,
            )

            self.assertIsNotNone(mqtt_config)
            self.maxDiff = None
            self.assertJsonDictEqual(
                {
                    'name': state.name,
                    'state_topic': f'{mqtt_prefix}/state',
                    'command_topic': 'homeassistant/alarm_control_panel/'
                                     'qolsys_panel/set',
                    'command_template': mock.ANY,
                    'code': 'REMOTE_CODE',
                    'code_disarm_required': True,
                    'code_arm_required': False,
                    'code_trigger_required': False,
                    'availability_mode': 'all',
                    'availability': [
                        {
                            'topic': 'homeassistant/alarm_control_panel/'
                                     'qolsys_panel/availability',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                        {
                            'topic': f'{mqtt_prefix}/availability',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                        {
                            'topic': 'appdaemon/birth_and_will',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                    ],
                    'json_attributes_topic': f'{mqtt_prefix}/attributes',
                    'unique_id': f'qolsys_panel_p{state.id}',
                    'device': mock.ANY,
                },
                mqtt_config['payload'],
            )

        with self.subTest(msg=f'MQTT availability of partition {state.id} is correct'):
            mqtt_availability = await gw.find_last_mqtt_publish(
                filters={'topic': f'{mqtt_prefix}/availability'},
                raise_if_not_found=True,
            )

            self.assertIsNotNone(mqtt_availability)
            self.assertEqual('online', mqtt_availability['payload'])

        with self.subTest(msg=f'MQTT state of partition {state.id} is correct'):
            mqtt_state = await gw.find_last_mqtt_publish(
                filters={'topic': f'{mqtt_prefix}/state'},
                raise_if_not_found=True,
            )

            self.assertIsNotNone(mqtt_state)
            self.assertEqual(expected_state, mqtt_state['payload'])

        with self.subTest(msg=f'MQTT attributes of partition {state.id} are correct'):
            mqtt_attributes = await gw.find_last_mqtt_publish(
                filters={'topic': f'{mqtt_prefix}/attributes'},
                raise_if_not_found=True,
            )

            self.assertIsNotNone(mqtt_attributes)
            self.maxDiff = None
            self.assertJsonDictEqual(
                {
                    'alarm_type': state.alarm_type,
                    'secure_arm': state.secure_arm,
                    'last_error_type': state.last_error_type,
                    'last_error_desc': state.last_error_desc,
                    'last_error_at': state.last_error_at,
                    'disarm_failed': state.disarm_failed,
                },
                mqtt_attributes['payload'],
            )

    async def _check_sensor_mqtt_messages(self, gw, sensor_flat_name,
                                          sensor_unique_id,
                                          sensor_state, expected_device_class,
                                          expected_enabled_by_default=True):
        state = sensor_state

        mqtt_prefix = f'homeassistant/binary_sensor/{sensor_flat_name}'

        with self.subTest(msg=f'MQTT config of sensor {state.zone_id} is correct'):
            mqtt_config = await gw.find_last_mqtt_publish(
                filters={'topic': f'{mqtt_prefix}/config'},
            )

            self.assertIsNotNone(mqtt_config)

            self.maxDiff = None
            self.assertJsonDictEqual(
                {
                    'name': state.name,
                    'device_class': expected_device_class,
                    'state_topic': f'{mqtt_prefix}/state',
                    'payload_on': 'Open',
                    'payload_off': 'Closed',
                    'availability_mode': 'all',
                    'availability': [
                        {
                            'topic': 'homeassistant/alarm_control_panel/'
                                     'qolsys_panel/availability',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                        {
                            'topic': f'{mqtt_prefix}/availability',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                        {
                            'topic': 'appdaemon/birth_and_will',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                    ],
                    'json_attributes_topic': f'{mqtt_prefix}/attributes',
                    'unique_id': f'qolsys_panel_s{sensor_unique_id}',
                    'device': mock.ANY,
                    'enabled_by_default': expected_enabled_by_default,
                },
                mqtt_config['payload'],
            )

        with self.subTest(msg=f'MQTT availability of sensor {state.zone_id} is correct'):
            mqtt_availability = await gw.find_last_mqtt_publish(
                filters={'topic': f'{mqtt_prefix}/availability'},
            )

            self.assertIsNotNone(mqtt_availability)
            self.assertEqual('online', mqtt_availability['payload'])

        with self.subTest(msg=f'MQTT state of sensor {state.zone_id} is correct'):
            mqtt_state = await gw.find_last_mqtt_publish(
                filters={'topic': f'{mqtt_prefix}/state'},
            )

            self.assertIsNotNone(mqtt_state)
            self.assertEqual(state.status, mqtt_state['payload'])

        with self.subTest(msg=f'MQTT attributes of sensor {state.zone_id} is correct'):
            mqtt_attributes = await gw.find_last_mqtt_publish(
                filters={'topic': f'{mqtt_prefix}/attributes'},
            )

            self.assertIsNotNone(mqtt_attributes)
            self.assertJsonDictEqual(
                {
                    'group': state.group,
                    'state': state.state,
                    'zone_physical_type': state.zone_physical_type,
                    'zone_alarm_type': state.zone_alarm_type,
                    'zone_type': state.zone_type,
                    'tampered': state.tampered,
                },
                mqtt_attributes['payload'],
            )

    async def test_integration_event_info_summary_initializes_all_entities(self):
        panel, gw, entity_ids, topics = await self._ready_panel_and_gw()

        mqtt_publish_calls = []

        for partition in ['partition0', 'partition1']:
            for topic in topics:
                mqtt_publish_calls.append(mock.call(
                    (f'homeassistant/alarm_control_panel/'
                     f'qolsys_panel/{partition}/{topic}'),
                    mock.ANY,
                    namespace=mock.ANY,
                    retain=mock.ANY,
                ))

        for entity_id in entity_ids:
            for topic in topics:
                mqtt_publish_calls.append(mock.call(
                    f'homeassistant/binary_sensor/{entity_id}/{topic}',
                    mock.ANY,
                    namespace=mock.ANY,
                    retain=mock.ANY,
                ))

        # Now we can actually check if the topics have been published
        gw.mqtt_publish_func.assert_has_calls(
            mqtt_publish_calls, any_order=True)

        # Check that the client is still connected
        self.assertTrue(panel.is_client_connected)

        # Check the state information
        state = gw._state
        with self.subTest(msg='State has the right number of partitions'):
            self.assertEqual(2, len(state.partitions))

        # Check the partitions information
        with self.subTest(msg='Partition 0 is properly configured'):
            partition0 = state.partition(0)
            self.assertEqual(10, len(partition0.sensors))
            self.assertEqual(0, partition0.id)
            self.assertEqual('partition0', partition0.name)
            self.assertEqual('DISARM', partition0.status)
            self.assertEqual(False, partition0.secure_arm)
            self.assertIsNone(partition0.alarm_type)

            await self._check_partition_mqtt_messages(
                gw=gw,
                partition_flat_name='partition0',
                partition_state=partition0,
                expected_state='disarmed',
            )

        with self.subTest(msg='Partition 1 is properly configured'):
            partition1 = state.partition(1)
            self.assertEqual(15, len(partition1.sensors))
            self.assertEqual(1, partition1.id)
            self.assertEqual('partition1', partition1.name)
            self.assertEqual('DISARM', partition1.status)
            self.assertEqual(False, partition1.secure_arm)
            self.assertIsNone(partition1.alarm_type)

            await self._check_partition_mqtt_messages(
                gw=gw,
                partition_flat_name='partition1',
                partition_state=partition1,
                expected_state='disarmed',
            )

        # Check the sensors information
        with self.subTest(msg='Sensor 10000 is properly configured'):
            sensor10000 = partition0.zone(10000)
            self.assertEqual(QolsysSensorDoorWindow, sensor10000.__class__)
            self.assertEqual('001-0000', sensor10000.id)
            self.assertEqual('My Door', sensor10000.name)
            self.assertEqual('entryexitdelay', sensor10000.group)
            self.assertEqual('Closed', sensor10000.status)
            self.assertEqual('0', sensor10000.state)
            self.assertEqual(10000, sensor10000.zone_id)
            self.assertEqual(1, sensor10000.zone_physical_type)
            self.assertEqual(3, sensor10000.zone_alarm_type)
            self.assertEqual(1, sensor10000.zone_type)
            self.assertEqual(0, sensor10000.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_door',
                sensor_unique_id='001_0000',
                sensor_state=sensor10000,
                expected_device_class='door',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 10001 is properly configured'):
            sensor10001 = partition0.zone(10001)
            self.assertEqual(QolsysSensorDoorWindow, sensor10001.__class__)
            self.assertEqual('001-0001', sensor10001.id)
            self.assertEqual('My Window', sensor10001.name)
            self.assertEqual('entryexitlongdelay', sensor10001.group)
            self.assertEqual('Open', sensor10001.status)
            self.assertEqual('0', sensor10001.state)
            self.assertEqual(10001, sensor10001.zone_id)
            self.assertEqual(1, sensor10001.zone_physical_type)
            self.assertEqual(3, sensor10001.zone_alarm_type)
            self.assertEqual(1, sensor10001.zone_type)
            self.assertEqual(0, sensor10001.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_window',
                sensor_unique_id='001_0001',
                sensor_state=sensor10001,
                expected_device_class='door',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 10010 is properly configured'):
            sensor10010 = partition0.zone(10010)
            self.assertEqual(QolsysSensorMotion, sensor10010.__class__)
            self.assertEqual('001-0010', sensor10010.id)
            self.assertEqual('My Motion', sensor10010.name)
            self.assertEqual('awayinstantmotion', sensor10010.group)
            self.assertEqual('Closed', sensor10010.status)
            self.assertEqual('0', sensor10010.state)
            self.assertEqual(10010, sensor10010.zone_id)
            self.assertEqual(2, sensor10010.zone_physical_type)
            self.assertEqual(3, sensor10010.zone_alarm_type)
            self.assertEqual(2, sensor10010.zone_type)
            self.assertEqual(0, sensor10010.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_motion',
                sensor_unique_id='001_0010',
                sensor_state=sensor10010,
                expected_device_class='motion',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 10011 is properly configured'):
            sensor10011 = partition0.zone(10011)
            self.assertEqual(QolsysSensorPanelMotion, sensor10011.__class__)
            self.assertEqual('001-0011', sensor10011.id)
            self.assertEqual('Panel Motion', sensor10011.name)
            self.assertEqual('safetymotion', sensor10011.group)
            self.assertEqual('Closed', sensor10011.status)
            self.assertEqual('0', sensor10011.state)
            self.assertEqual(10011, sensor10011.zone_id)
            self.assertEqual(1, sensor10011.zone_physical_type)
            self.assertEqual(3, sensor10011.zone_alarm_type)
            self.assertEqual(119, sensor10011.zone_type)
            self.assertEqual(0, sensor10011.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='panel_motion',
                sensor_unique_id='001_0011',
                sensor_state=sensor10011,
                expected_device_class='motion',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 10020 is properly configured'):
            sensor10020 = partition0.zone(10020)
            self.assertEqual(QolsysSensorGlassBreak, sensor10020.__class__)
            self.assertEqual('001-0020', sensor10020.id)
            self.assertEqual('My Glass Break', sensor10020.name)
            self.assertEqual('glassbreakawayonly', sensor10020.group)
            self.assertEqual('Closed', sensor10020.status)
            self.assertEqual('0', sensor10020.state)
            self.assertEqual(10020, sensor10020.zone_id)
            self.assertEqual(1, sensor10020.zone_physical_type)
            self.assertEqual(0, sensor10020.zone_alarm_type)
            self.assertEqual(116, sensor10020.zone_type)
            self.assertEqual(0, sensor10020.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_glass_break',
                sensor_unique_id='001_0020',
                sensor_state=sensor10020,
                expected_device_class='vibration',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 10021 is properly configured'):
            sensor10021 = partition0.zone(10021)
            self.assertEqual(QolsysSensorPanelGlassBreak, sensor10021.__class__)
            self.assertEqual('001-0021', sensor10021.id)
            self.assertEqual('Panel Glass Break', sensor10021.name)
            self.assertEqual('glassbreakawayonly', sensor10021.group)
            self.assertEqual('Closed', sensor10021.status)
            self.assertEqual('0', sensor10021.state)
            self.assertEqual(10021, sensor10021.zone_id)
            self.assertEqual(1, sensor10021.zone_physical_type)
            self.assertEqual(0, sensor10021.zone_alarm_type)
            self.assertEqual(116, sensor10021.zone_type)
            self.assertEqual(0, sensor10021.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='panel_glass_break',
                sensor_unique_id='001_0021',
                sensor_state=sensor10021,
                expected_device_class='vibration',
                expected_enabled_by_default=False,
            )

        with self.subTest(msg='Sensor 10030 is properly configured'):
            sensor10030 = partition0.zone(10030)
            self.assertEqual(QolsysSensorBluetooth, sensor10030.__class__)
            self.assertEqual('001-0030', sensor10030.id)
            self.assertEqual('My Phone', sensor10030.name)
            self.assertEqual('mobileintrusion', sensor10030.group)
            self.assertEqual('Closed', sensor10030.status)
            self.assertEqual('0', sensor10030.state)
            self.assertEqual(10030, sensor10030.zone_id)
            self.assertEqual(1, sensor10030.zone_physical_type)
            self.assertEqual(1, sensor10030.zone_alarm_type)
            self.assertEqual(115, sensor10030.zone_type)
            self.assertEqual(0, sensor10030.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_phone',
                sensor_unique_id='001_0030',
                sensor_state=sensor10030,
                expected_device_class='presence',
                expected_enabled_by_default=False,
            )

        with self.subTest(msg='Sensor 10040 is properly configured'):
            sensor10040 = partition0.zone(10040)
            self.assertEqual(QolsysSensorSmokeDetector, sensor10040.__class__)
            self.assertEqual('001-0040', sensor10040.id)
            self.assertEqual('My Smoke Detector', sensor10040.name)
            self.assertEqual('smoke_heat', sensor10040.group)
            self.assertEqual('Closed', sensor10040.status)
            self.assertEqual('0', sensor10040.state)
            self.assertEqual(10040, sensor10040.zone_id)
            self.assertEqual(9, sensor10040.zone_physical_type)
            self.assertEqual(9, sensor10040.zone_alarm_type)
            self.assertEqual(5, sensor10040.zone_type)
            self.assertEqual(0, sensor10040.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_smoke_detector',
                sensor_unique_id='001_0040',
                sensor_state=sensor10040,
                expected_device_class='smoke',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 10041 is properly configured'):
            sensor10041 = partition0.zone(10041)
            self.assertEqual(QolsysSensorCODetector, sensor10041.__class__)
            self.assertEqual('001-0041', sensor10041.id)
            self.assertEqual('My CO Detector', sensor10041.name)
            self.assertEqual('entryexitdelay', sensor10041.group)
            self.assertEqual('Closed', sensor10041.status)
            self.assertEqual('0', sensor10041.state)
            self.assertEqual(10041, sensor10041.zone_id)
            self.assertEqual(1, sensor10041.zone_physical_type)
            self.assertEqual(3, sensor10041.zone_alarm_type)
            self.assertEqual(1, sensor10041.zone_type)
            self.assertEqual(0, sensor10041.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_co_detector',
                sensor_unique_id='001_0041',
                sensor_state=sensor10041,
                expected_device_class='gas',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 10050 is properly configured'):
            sensor10050 = partition0.zone(10050)
            self.assertEqual(QolsysSensorWater, sensor10050.__class__)
            self.assertEqual('001-0050', sensor10050.id)
            self.assertEqual('My Water Detector', sensor10050.name)
            self.assertEqual('WaterSensor', sensor10050.group)
            self.assertEqual('Closed', sensor10050.status)
            self.assertEqual('0', sensor10050.state)
            self.assertEqual(10050, sensor10050.zone_id)
            self.assertEqual(8, sensor10050.zone_physical_type)
            self.assertEqual(0, sensor10050.zone_alarm_type)
            self.assertEqual(15, sensor10050.zone_type)
            self.assertEqual(0, sensor10050.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_water_detector',
                sensor_unique_id='001_0050',
                sensor_state=sensor10050,
                expected_device_class='moisture',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 20000 is properly configured'):
            sensor20000 = partition1.zone(20000)
            self.assertEqual(QolsysSensorDoorWindow, sensor20000.__class__)
            self.assertEqual('002-0000', sensor20000.id)
            self.assertEqual('My 2nd Door', sensor20000.name)
            self.assertEqual('instantperimeter', sensor20000.group)
            self.assertEqual('Closed', sensor20000.status)
            self.assertEqual('0', sensor20000.state)
            self.assertEqual(20000, sensor20000.zone_id)
            self.assertEqual(1, sensor20000.zone_physical_type)
            self.assertEqual(3, sensor20000.zone_alarm_type)
            self.assertEqual(1, sensor20000.zone_type)
            self.assertEqual(1, sensor20000.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_2nd_door',
                sensor_unique_id='002_0000',
                sensor_state=sensor20000,
                expected_device_class='door',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 20001 is properly configured'):
            sensor20001 = partition1.zone(20001)
            self.assertEqual(QolsysSensorDoorbell, sensor20001.__class__)
            self.assertEqual('002-0001', sensor20001.id)
            self.assertEqual('My Doorbell Sensor', sensor20001.name)
            self.assertEqual('localsafety', sensor20001.group)
            self.assertEqual('Closed', sensor20001.status)
            self.assertEqual('0', sensor20001.state)
            self.assertEqual(20001, sensor20001.zone_id)
            self.assertEqual(1, sensor20001.zone_physical_type)
            self.assertEqual(3, sensor20001.zone_alarm_type)
            self.assertEqual(109, sensor20001.zone_type)
            self.assertEqual(1, sensor20001.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_doorbell_sensor',
                sensor_unique_id='002_0001',
                sensor_state=sensor20001,
                expected_device_class='sound',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 20010 is properly configured'):
            sensor20010 = partition1.zone(20010)
            self.assertEqual(QolsysSensorFreeze, sensor20010.__class__)
            self.assertEqual('002-0010', sensor20010.id)
            self.assertEqual('My Freeze Sensor', sensor20010.name)
            self.assertEqual('freeze', sensor20010.group)
            self.assertEqual('Closed', sensor20010.status)
            self.assertEqual('0', sensor20010.state)
            self.assertEqual(20010, sensor20010.zone_id)
            self.assertEqual(6, sensor20010.zone_physical_type)
            self.assertEqual(0, sensor20010.zone_alarm_type)
            self.assertEqual(17, sensor20010.zone_type)
            self.assertEqual(1, sensor20010.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_freeze_sensor',
                sensor_unique_id='002_0010',
                sensor_state=sensor20010,
                expected_device_class='cold',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 20020 is properly configured'):
            sensor20020 = partition1.zone(20020)
            self.assertEqual(QolsysSensorHeat, sensor20020.__class__)
            self.assertEqual('002-0020', sensor20020.id)
            self.assertEqual('My Heat Sensor', sensor20020.name)
            self.assertEqual('smoke_heat', sensor20020.group)
            self.assertEqual('Closed', sensor20020.status)
            self.assertEqual('0', sensor20020.state)
            self.assertEqual(20020, sensor20020.zone_id)
            self.assertEqual(10, sensor20020.zone_physical_type)
            self.assertEqual(0, sensor20020.zone_alarm_type)
            self.assertEqual(8, sensor20020.zone_type)
            self.assertEqual(1, sensor20020.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_heat_sensor',
                sensor_unique_id='002_0020',
                sensor_state=sensor20020,
                expected_device_class='heat',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 20021 is properly configured'):
            sensor20021 = partition1.zone(20021)
            self.assertEqual(QolsysSensorTemperature, sensor20021.__class__)
            self.assertEqual('002-0021', sensor20021.id)
            self.assertEqual('My Temperature Sensor', sensor20021.name)
            self.assertEqual('Temperature', sensor20021.group)
            self.assertEqual('Closed', sensor20021.status)
            self.assertEqual('0', sensor20021.state)
            self.assertEqual(20021, sensor20021.zone_id)
            self.assertEqual(1, sensor20021.zone_physical_type)
            self.assertEqual(0, sensor20021.zone_alarm_type)
            self.assertEqual(8, sensor20021.zone_type)
            self.assertEqual(1, sensor20021.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_temperature_sensor',
                sensor_unique_id='002_0021',
                sensor_state=sensor20021,
                expected_device_class='heat',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 20030 is properly configured'):
            sensor20030 = partition1.zone(20030)
            self.assertEqual(QolsysSensorTilt, sensor20030.__class__)
            self.assertEqual('002-0030', sensor20030.id)
            self.assertEqual('My Tilt Sensor', sensor20030.name)
            self.assertEqual('garageTilt1', sensor20030.group)
            self.assertEqual('Closed', sensor20030.status)
            self.assertEqual('0', sensor20030.state)
            self.assertEqual(20030, sensor20030.zone_id)
            self.assertEqual(1, sensor20030.zone_physical_type)
            self.assertEqual(3, sensor20030.zone_alarm_type)
            self.assertEqual(16, sensor20030.zone_type)
            self.assertEqual(1, sensor20030.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_tilt_sensor',
                sensor_unique_id='002_0030',
                sensor_state=sensor20030,
                expected_device_class='garage_door',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 20040 is properly configured'):
            sensor20040 = partition1.zone(20040)
            self.assertEqual(QolsysSensorKeypad, sensor20040.__class__)
            self.assertEqual('002-0040', sensor20040.id)
            self.assertEqual('My Keypad Sensor', sensor20040.name)
            self.assertEqual('fixedintrusion', sensor20040.group)
            self.assertEqual('Closed', sensor20040.status)
            self.assertEqual('0', sensor20040.state)
            self.assertEqual(20040, sensor20040.zone_id)
            self.assertEqual(4, sensor20040.zone_physical_type)
            self.assertEqual(0, sensor20040.zone_alarm_type)
            self.assertEqual(104, sensor20040.zone_type)
            self.assertEqual(1, sensor20040.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_keypad_sensor',
                sensor_unique_id='002_0040',
                sensor_state=sensor20040,
                expected_device_class='safety',
                expected_enabled_by_default=False,
            )

        with self.subTest(msg='Sensor 20050 is properly configured'):
            sensor20050 = partition1.zone(20050)
            self.assertEqual(QolsysSensorAuxiliaryPendant, sensor20050.__class__)
            self.assertEqual('002-0050', sensor20050.id)
            self.assertEqual('My Auxiliary Pendant Sensor', sensor20050.name)
            self.assertEqual('fixedmedical', sensor20050.group)
            self.assertEqual('Closed', sensor20050.status)
            self.assertEqual('0', sensor20050.state)
            self.assertEqual(20050, sensor20050.zone_id)
            self.assertEqual(1, sensor20050.zone_physical_type)
            self.assertEqual(0, sensor20050.zone_alarm_type)
            self.assertEqual(21, sensor20050.zone_type)
            self.assertEqual(1, sensor20050.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_auxiliary_pendant_sensor',
                sensor_unique_id='002_0050',
                sensor_state=sensor20050,
                expected_device_class='safety',
                expected_enabled_by_default=False,
            )

        with self.subTest(msg='Sensor 20060 is properly configured'):
            sensor20060 = partition1.zone(20060)
            self.assertEqual(QolsysSensorSiren, sensor20060.__class__)
            self.assertEqual('002-0060', sensor20060.id)
            self.assertEqual('My Siren Sensor', sensor20060.name)
            self.assertEqual('Siren', sensor20060.group)
            self.assertEqual('Closed', sensor20060.status)
            self.assertEqual('0', sensor20060.state)
            self.assertEqual(20060, sensor20060.zone_id)
            self.assertEqual(1, sensor20060.zone_physical_type)
            self.assertEqual(3, sensor20060.zone_alarm_type)
            self.assertEqual(14, sensor20060.zone_type)
            self.assertEqual(1, sensor20060.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_siren_sensor',
                sensor_unique_id='002_0060',
                sensor_state=sensor20060,
                expected_device_class='safety',
                expected_enabled_by_default=False,
            )

        with self.subTest(msg='Sensor 20070 is properly configured'):
            sensor20070 = partition1.zone(20070)
            self.assertEqual(QolsysSensorKeyFob, sensor20070.__class__)
            self.assertEqual('002-0070', sensor20070.id)
            self.assertEqual('My KeyFob Sensor', sensor20070.name)
            self.assertEqual('mobileintrusion', sensor20070.group)
            self.assertEqual('Closed', sensor20070.status)
            self.assertEqual('0', sensor20070.state)
            self.assertEqual(20070, sensor20070.zone_id)
            self.assertEqual(3, sensor20070.zone_physical_type)
            self.assertEqual(0, sensor20070.zone_alarm_type)
            self.assertEqual(102, sensor20070.zone_type)
            self.assertEqual(1, sensor20070.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_keyfob_sensor',
                sensor_unique_id='002_0070',
                sensor_state=sensor20070,
                expected_device_class='safety',
                expected_enabled_by_default=False,
            )

        with self.subTest(msg='Sensor 20080 is properly configured'):
            sensor20080 = partition1.zone(20080)
            self.assertEqual(QolsysSensorTakeoverModule, sensor20080.__class__)
            self.assertEqual('002-0080', sensor20080.id)
            self.assertEqual('My TakeoverModule Sensor', sensor20080.name)
            self.assertEqual('takeovermodule', sensor20080.group)
            self.assertEqual('Closed', sensor20080.status)
            self.assertEqual('0', sensor20080.state)
            self.assertEqual(20080, sensor20080.zone_id)
            self.assertEqual(13, sensor20080.zone_physical_type)
            self.assertEqual(0, sensor20080.zone_alarm_type)
            self.assertEqual(18, sensor20080.zone_type)
            self.assertEqual(1, sensor20080.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_takeovermodule_sensor',
                sensor_unique_id='002_0080',
                sensor_state=sensor20080,
                expected_device_class='safety',
                expected_enabled_by_default=False,
            )

        with self.subTest(msg='Sensor 200802 is properly configured'):
            sensor200802 = partition1.zone(200802)
            self.assertEqual(QolsysSensorDoorWindow, sensor200802.__class__)
            self.assertEqual('002-0080', sensor200802.id)
            self.assertEqual('My TakeoverModule Door Sensor', sensor200802.name)
            self.assertEqual('entryexitlongdelay', sensor200802.group)
            self.assertEqual('Closed', sensor200802.status)
            self.assertEqual('0', sensor200802.state)
            self.assertEqual(200802, sensor200802.zone_id)
            self.assertEqual(1, sensor200802.zone_physical_type)
            self.assertEqual(3, sensor200802.zone_alarm_type)
            self.assertEqual(1, sensor200802.zone_type)
            self.assertEqual(1, sensor200802.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_takeovermodule_door_sensor',
                sensor_unique_id='002_0080_200802',
                sensor_state=sensor200802,
                expected_device_class='door',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 20081 is properly configured'):
            sensor20081 = partition1.zone(20081)
            self.assertEqual(QolsysSensorTranslator, sensor20081.__class__)
            self.assertEqual('002-0081', sensor20081.id)
            self.assertEqual('My Translator Sensor', sensor20081.name)
            self.assertEqual('translator', sensor20081.group)
            self.assertEqual('Closed', sensor20081.status)
            self.assertEqual('0', sensor20081.state)
            self.assertEqual(20081, sensor20081.zone_id)
            self.assertEqual(14, sensor20081.zone_physical_type)
            self.assertEqual(0, sensor20081.zone_alarm_type)
            self.assertEqual(20, sensor20081.zone_type)
            self.assertEqual(1, sensor20081.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_translator_sensor',
                sensor_unique_id='002_0081',
                sensor_state=sensor20081,
                expected_device_class='safety',
                expected_enabled_by_default=False,
            )

        with self.subTest(msg='Sensor 20090 is properly configured'):
            sensor20090 = partition1.zone(20090)
            self.assertEqual(QolsysSensorShock, sensor20090.__class__)
            self.assertEqual('002-0090', sensor20090.id)
            self.assertEqual('My Shock Sensor', sensor20090.name)
            self.assertEqual('shock', sensor20090.group)
            self.assertEqual('Closed', sensor20090.status)
            self.assertEqual('0', sensor20090.state)
            self.assertEqual(20090, sensor20090.zone_id)
            self.assertEqual(12, sensor20090.zone_physical_type)
            self.assertEqual(0, sensor20090.zone_alarm_type)
            self.assertEqual(107, sensor20090.zone_type)
            self.assertEqual(1, sensor20090.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='my_shock_sensor',
                sensor_unique_id='002_0090',
                sensor_state=sensor20090,
                expected_device_class='vibration',
                expected_enabled_by_default=True,
            )

        with self.subTest(msg='Sensor 20091 is properly configured'):
            sensor20091 = partition1.zone(20091)
            self.assertEqual(QolsysSensorTamperSensor, sensor20091.__class__)
            self.assertEqual('002-0091', sensor20091.id)
            self.assertEqual('Main Cabinet Tamper Sensor', sensor20091.name)
            self.assertEqual('tamperzone', sensor20091.group)
            self.assertEqual('Closed', sensor20091.status)
            self.assertEqual('0', sensor20091.state)
            self.assertEqual(20091, sensor20091.zone_id)
            self.assertEqual(1, sensor20091.zone_physical_type)
            self.assertEqual(3, sensor20091.zone_alarm_type)
            self.assertEqual(123, sensor20091.zone_type)
            self.assertEqual(1, sensor20091.partition_id)

            await self._check_sensor_mqtt_messages(
                gw=gw,
                sensor_flat_name='main_cabinet_tamper_sensor',
                sensor_unique_id='002_0091',
                sensor_state=sensor20091,
                expected_device_class='tamper',
                expected_enabled_by_default=True,
            )

    async def _test_integration_event_info_secure_arm(self, from_secure_arm,
                                                      to_secure_arm):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            secure_arm=from_secure_arm,
            partition_ids=[0],
            zone_ids=[10000],
        )

        event = {
            'event': 'INFO',
            'info_type': 'SECURE_ARM',
            'partition_id': 0,
            'value': to_secure_arm,
            'version': 1,
            'requestID': '<request_id>',
        }
        await panel.writeline(event)

        # Wait until the attributes publish is done
        attributes = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/alarm_control_panel/'
                              'qolsys_panel/partition0/attributes'},
        )

        if from_secure_arm != to_secure_arm:
            self.assertIsNotNone(attributes)
            self.assertJsonSubDictEqual({'secure_arm': to_secure_arm}, attributes['payload'])
        else:
            self.assertIsNone(attributes)

        self.assertEqual(to_secure_arm, gw._state.partition(0).secure_arm)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_event_info_secure_arm_true_if_false(self):
        await self._test_integration_event_info_secure_arm(
            from_secure_arm=False,
            to_secure_arm=True,
        )

    async def test_integration_event_info_secure_arm_true_if_true(self):
        await self._test_integration_event_info_secure_arm(
            from_secure_arm=True,
            to_secure_arm=True,
        )

    async def test_integration_event_info_secure_arm_false_if_true(self):
        await self._test_integration_event_info_secure_arm(
            from_secure_arm=True,
            to_secure_arm=False,
        )

    async def test_integration_event_info_secure_arm_false_if_false(self):
        await self._test_integration_event_info_secure_arm(
            from_secure_arm=False,
            to_secure_arm=False,
        )

    async def _test_integration_event_zone_event_zone_active_tampered_while_closed(self):
        # Using a sensor that's already closed
        zone_id = 10000
        entity_id = 'my_door'

        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[zone_id],
        )

        sensor = gw._state.partition(0).zone(zone_id)

        event_open = {
            'event': 'ZONE_EVENT',
            'zone_event_type': 'ZONE_ACTIVE',
            'version': 1,
            'zone': {
                'status': 'Open',
                'zone_id': zone_id,
            },
            'requestID': '<request_id>',
        }

        event_closed = deepcopy(event_open)
        event_closed['zone']['status'] = 'Closed'

        with self.subTest(msg='Sensor is open on first open message'):
            await panel.writeline(event_open)

            state = await gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': f'homeassistant/binary_sensor/'
                                  f'{entity_id}/state'},
                raise_on_timeout=True,
            )

            self.assertTrue(sensor.is_open)
            self.assertEqual('Open', state['payload'])

        with self.subTest(msg='Sensor is tampered on second open message'):
            await panel.writeline(event_open)

            attributes = await gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': f'homeassistant/binary_sensor/'
                                  f'{entity_id}/attributes'},
                raise_on_timeout=True,
            )

            self.assertTrue(sensor.tampered)
            self.assertJsonSubDictEqual({'tampered': True}, attributes['payload'])

        return SimpleNamespace(
            panel=panel,
            gw=gw,
            zone_id=zone_id,
            entity_id=entity_id,
            event_open=event_open,
            event_closed=event_closed,
            sensor=sensor,
        )

    async def test_integration_event_zone_event_zone_active_tampered_while_closed_to_closed(self):
        data = await self._test_integration_event_zone_event_zone_active_tampered_while_closed()

        with self.subTest(msg='Sensor is untampered on first closed message'):
            await data.panel.writeline(data.event_closed)

            attributes = await data.gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': f'homeassistant/binary_sensor/'
                                  f'{data.entity_id}/attributes'},
                raise_on_timeout=True,
            )

            self.assertFalse(data.sensor.tampered)
            self.assertJsonSubDictEqual({'tampered': False}, attributes['payload'])

        with self.subTest(msg='Sensor is closed on second closed message'):
            await data.panel.writeline(data.event_closed)

            state = await data.gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': f'homeassistant/binary_sensor/'
                                  f'{data.entity_id}/state'},
                raise_on_timeout=True,
            )

            self.assertTrue(data.sensor.is_closed)
            self.assertEqual('Closed', state['payload'])

    async def test_integration_event_zone_event_zone_active_tampered_while_closed_to_open(self):
        data = await self._test_integration_event_zone_event_zone_active_tampered_while_closed()

        with self.subTest(msg='Sensor is untampered when receiving open and close in the same second'):
            await data.panel.writeline(data.event_open)
            await data.panel.writeline(data.event_closed)

            attributes = await data.gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': f'homeassistant/binary_sensor/'
                                  f'{data.entity_id}/attributes'},
                raise_on_timeout=True,
            )

            self.assertFalse(data.sensor.tampered)
            self.assertJsonSubDictEqual({'tampered': False}, attributes['payload'])

        with self.subTest(msg='Sensor is not tampered when receiving open message next'):
            await data.panel.writeline(data.event_open)

            attributes = await data.gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': f'homeassistant/binary_sensor/'
                                  f'{data.entity_id}/attributes'},
            )

            self.assertTrue(data.sensor.is_open)
            self.assertIsNone(attributes)

    async def _test_integration_event_zone_event_zone_active_tampered_while_open(self):
        # Using a sensor that's already open
        zone_id = 10001
        entity_id = 'my_window'

        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[zone_id],
        )

        sensor = gw._state.partition(0).zone(zone_id)

        event_open = {
            'event': 'ZONE_EVENT',
            'zone_event_type': 'ZONE_ACTIVE',
            'version': 1,
            'zone': {
                'status': 'Open',
                'zone_id': zone_id,
            },
            'requestID': '<request_id>',
        }

        event_closed = deepcopy(event_open)
        event_closed['zone']['status'] = 'Closed'

        with self.subTest(msg='Sensor is tampered on second open message'):
            with mock.patch('time.time', mock.MagicMock(return_value=42)):
                await panel.writeline(event_open)

                attributes = await gw.wait_for_next_mqtt_publish(
                    timeout=self._TIMEOUT,
                    filters={'topic': f'homeassistant/binary_sensor/'
                                      f'{entity_id}/attributes'},
                    raise_on_timeout=True,
                )

            self.assertTrue(sensor.tampered)
            self.assertEqual(42, sensor._last_open_tampered_at)
            self.assertJsonSubDictEqual({'tampered': True}, attributes['payload'])

        with self.subTest(msg='Sensor is untampered when receiving open and close in the same second'):
            await panel.writeline(event_open)
            await panel.writeline(event_closed)

            attributes = await gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': f'homeassistant/binary_sensor/'
                                  f'{entity_id}/attributes'},
                raise_on_timeout=True,
            )

            self.assertFalse(sensor.tampered)
            self.assertJsonSubDictEqual({'tampered': False}, attributes['payload'])

        return SimpleNamespace(
            panel=panel,
            gw=gw,
            zone_id=zone_id,
            entity_id=entity_id,
            event_open=event_open,
            event_closed=event_closed,
            sensor=sensor,
        )

    async def test_integration_event_zone_event_zone_active_tampered_while_open_to_open(self):
        data = await self._test_integration_event_zone_event_zone_active_tampered_while_open()

        with self.subTest(msg='Sensor is not tampered when receiving open message next'):
            await data.panel.writeline(data.event_open)

            attributes = await data.gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': f'homeassistant/binary_sensor/'
                                  f'{data.entity_id}/attributes'},
            )

            self.assertFalse(data.sensor.tampered)
            self.assertTrue(data.sensor.is_open)
            self.assertIsNone(attributes)

    async def test_integration_event_zone_event_zone_active_tampered_while_open_to_closed(self):
        data = await self._test_integration_event_zone_event_zone_active_tampered_while_open()

        with self.subTest(msg='Sensor is closed when receiving closed message next'):
            await data.panel.writeline(data.event_closed)

            state = await data.gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': f'homeassistant/binary_sensor/'
                                  f'{data.entity_id}/state'},
                raise_on_timeout=True,
            )

            self.assertFalse(data.sensor.tampered)
            self.assertTrue(data.sensor.is_closed)
            self.assertEqual('Closed', state['payload'])

    async def _test_integration_event_zone_event_zone_active(self, from_status, to_status):
        if from_status == 'Closed':
            zone_id = 10000
            entity_id = 'my_door'
        else:
            zone_id = 10001
            entity_id = 'my_window'

        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[zone_id],
        )

        event = {
            'event': 'ZONE_EVENT',
            'zone_event_type': 'ZONE_ACTIVE',
            'version': 1,
            'zone': {
                'status': to_status,
                'zone_id': zone_id,
            },
            'requestID': '<request_id>',
        }
        await panel.writeline(event)

        state = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': f'homeassistant/binary_sensor/'
                              f'{entity_id}/state'},
        )

        if from_status != to_status:
            self.assertIsNotNone(state)
            self.assertEqual(to_status, state['payload'])
        else:
            self.assertIsNone(state)

        self.assertEqual(
            to_status,
            gw._state.partition(0).zone(zone_id).status,
        )

        self.assertTrue(panel.is_client_connected)

    async def test_integration_event_zone_event_zone_active_open_if_closed(self):
        await self._test_integration_event_zone_event_zone_active(
            from_status='Closed',
            to_status='Open',
        )

    async def test_integration_event_zone_event_zone_active_open_if_open(self):
        await self._test_integration_event_zone_event_zone_active(
            from_status='Open',
            to_status='Open',
        )

    async def test_integration_event_zone_event_zone_active_closed_if_open(self):
        await self._test_integration_event_zone_event_zone_active(
            from_status='Open',
            to_status='Closed',
        )

    async def test_integration_event_zone_event_zone_active_closed_if_closed(self):
        await self._test_integration_event_zone_event_zone_active(
            from_status='Closed',
            to_status='Closed',
        )

    async def test_integration_event_zone_event_zone_active_unknown_zone(self):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[10001],
        )

        event = {
            'event': 'ZONE_EVENT',
            'zone_event_type': 'ZONE_ACTIVE',
            'version': 1,
            'zone': {
                'status': 'Closed',
                'zone_id': 10000,
            },
            'requestID': '<request_id>',
        }
        await panel.writeline(event)

        state = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/binary_sensor/'
                              'my_door/state'},
        )

        self.assertIsNone(state)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_event_zone_event_zone_update_existing_zone(self):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0, 1],
            zone_ids=[10000, 20000],
        )

        event = {
            'event': 'ZONE_EVENT',
            'zone_event_type': 'ZONE_UPDATE',
            'zone': {
                'id': '001-0000',
                'type': 'Door_Window',
                'name': 'My Door',
                'group': 'entryexitdelay',
                'status': 'Open',
                'state': '1',
                'zone_id': 10000,
                'zone_physical_type': 60,
                'zone_alarm_type': 61,
                'zone_type': 62,
                'partition_id': 1,
            },
            'version': 1,
            'requestID': '<request_id>',
        }
        await panel.writeline(event)

        state = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/binary_sensor/'
                              'my_door/state'},
        )

        attributes = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/binary_sensor/'
                              'my_door/attributes'},
            continued=True,
        )

        self.assertIsNotNone(state)
        self.assertIsNotNone(attributes)

        self.assertEqual('Open', state['payload'])
        self.assertJsonDictEqual(
            {
                'group': 'entryexitdelay',
                'state': '1',
                'zone_physical_type': 60,
                'zone_alarm_type': 61,
                'zone_type': 62,
                'tampered': False,
            },
            attributes['payload'],
        )

        state = gw._state

        partition0 = state.partition(0)
        self.assertEqual(0, len(partition0.sensors))

        partition1 = state.partition(1)
        self.assertEqual(2, len(partition1.sensors))

        sensor = partition1.zone(10000)
        self.assertEqual('1', sensor.state)
        self.assertEqual(60, sensor.zone_physical_type)
        self.assertEqual(61, sensor.zone_alarm_type)
        self.assertEqual(62, sensor.zone_type)
        self.assertEqual(1, sensor.partition_id)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_event_zone_event_zone_update_unknown_zone(self):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[10001],
        )

        event = {
            'event': 'ZONE_EVENT',
            'zone_event_type': 'ZONE_UPDATE',
            'zone': {
                'id': '001-0000',
                'type': 'Door_Window',
                'name': 'My Door',
                'group': 'entryexitdelay',
                'status': 'Open',
                'state': '1',
                'zone_id': 10000,
                'zone_physical_type': 60,
                'zone_alarm_type': 61,
                'zone_type': 62,
                'partition_id': 0,
            },
            'version': 1,
            'requestID': '<request_id>',
        }
        await panel.writeline(event)

        error = await gw.wait_for_next_log(
            timeout=self._TIMEOUT,
            filters={'level': 'ERROR'},
            match='Exception: Zone not found for zone update',
        )

        self.assertIsNotNone(error)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_event_zone_event_zone_add(self):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[10000],
        )

        event = {
            'event': 'ZONE_EVENT',
            'zone_event_type': 'ZONE_ADD',
            'zone': {
                'id': '001-0010',
                'type': 'Motion',
                'name': 'My Motion',
                'group': 'awayinstantmotion',
                'status': 'Closed',
                'state': '0',
                'zone_id': 10010,
                'zone_physical_type': 2,
                'zone_alarm_type': 3,
                'zone_type': 2,
                'partition_id': 0,
            },
            'version': 1,
            'requestID': '<request_id>',
        }
        await panel.writeline(event)

        config = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/binary_sensor/'
                              'my_motion/config'},
        )

        availability = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/binary_sensor/'
                              'my_motion/availability'},
            continued=True,
        )

        state = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/binary_sensor/'
                              'my_motion/state'},
            continued=True,
        )

        attributes = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/binary_sensor/'
                              'my_motion/attributes'},
            continued=True,
        )

        with self.subTest(msg='Check MQTT config of new sensor'):
            self.assertIsNotNone(config)
            self.maxDiff = None
            self.assertJsonDictEqual(
                {
                    'name': 'My Motion',
                    'device_class': 'motion',
                    'enabled_by_default': True,
                    'state_topic': 'homeassistant/binary_sensor/'
                                   'my_motion/state',
                    'payload_on': 'Open',
                    'payload_off': 'Closed',
                    'availability_mode': 'all',
                    'availability': [
                        {
                            'topic': 'homeassistant/alarm_control_panel/'
                                     'qolsys_panel/availability',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                        {
                            'topic': 'homeassistant/binary_sensor/'
                                     'my_motion/availability',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                        {
                            'topic': 'appdaemon/birth_and_will',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                    ],
                    'json_attributes_topic': 'homeassistant/binary_sensor/'
                                             'my_motion/attributes',
                    'unique_id': 'qolsys_panel_s001_0010',
                    'device': mock.ANY,
                },
                config['payload'],
            )

        with self.subTest(msg='Check MQTT availability of new sensor'):
            self.assertIsNotNone(availability)
            self.assertEqual('online', availability['payload'])

        with self.subTest(msg='Check MQTT state of new sensor'):
            self.assertIsNotNone(state)
            self.assertEqual('Closed', state['payload'])

        with self.subTest(msg='Check MQTT attributes of new sensor'):
            self.assertIsNotNone(attributes)
            self.assertJsonDictEqual(
                {
                    'group': 'awayinstantmotion',
                    'state': '0',
                    'zone_physical_type': 2,
                    'zone_alarm_type': 3,
                    'zone_type': 2,
                    'tampered': False,
                },
                attributes['payload'],
            )

        state = gw._state

        with self.subTest(msg='Partition 0 has the new sensor'):
            partition0 = state.partition(0)
            self.assertEqual(2, len(partition0.sensors))

        with self.subTest(msg='Sensor 10010 is properly configured'):
            sensor10010 = partition0.zone(10010)
            self.assertEqual(QolsysSensorMotion, sensor10010.__class__)
            self.assertEqual('001-0010', sensor10010.id)
            self.assertEqual('My Motion', sensor10010.name)
            self.assertEqual('awayinstantmotion', sensor10010.group)
            self.assertEqual('Closed', sensor10010.status)
            self.assertEqual('0', sensor10010.state)
            self.assertEqual(10010, sensor10010.zone_id)
            self.assertEqual(2, sensor10010.zone_physical_type)
            self.assertEqual(3, sensor10010.zone_alarm_type)
            self.assertEqual(2, sensor10010.zone_type)
            self.assertEqual(0, sensor10010.partition_id)

        self.assertTrue(panel.is_client_connected)

    async def _test_integration_event_arming(self, from_status, to_status, ha_status=None):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[10000],
            partition_status={
                0: from_status,
            },
        )

        event = {
            'event': 'ARMING',
            'arming_type': to_status,
            'partition_id': 0,
            'version': 1,
            'requestID': '<request_id>',
        }
        await panel.writeline(event)

        published_state = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/alarm_control_panel/'
                              'qolsys_panel/partition0/state'},
        )

        if from_status != to_status:
            self.assertIsNotNone(published_state)
            self.assertEqual(ha_status, published_state['payload'])
        else:
            self.assertIsNone(published_state)

        partition = gw._state.partition(0)
        self.assertEqual(to_status, partition.status)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_event_arming_disarm_if_disarm(self):
        await self._test_integration_event_arming(
            from_status='DISARM',
            to_status='DISARM',
        )

    async def test_integration_event_arming_disarm_if_arm_stay(self):
        await self._test_integration_event_arming(
            from_status='ARM_STAY',
            to_status='DISARM',
            ha_status='disarmed',
        )

    async def test_integration_event_arming_disarm_if_arm_away(self):
        await self._test_integration_event_arming(
            from_status='ARM_AWAY',
            to_status='DISARM',
            ha_status='disarmed',
        )

    async def test_integration_event_arming_disarm_if_entry_delay(self):
        await self._test_integration_event_arming(
            from_status='ARM_AWAY',
            to_status='DISARM',
            ha_status='disarmed',
        )

    async def test_integration_event_arming_arm_stay_if_arm_stay(self):
        await self._test_integration_event_arming(
            from_status='ARM_STAY',
            to_status='ARM_STAY',
        )

    async def test_integration_event_arming_arm_stay_if_exit_delay(self):
        await self._test_integration_event_arming(
            from_status='EXIT_DELAY',
            to_status='ARM_STAY',
            ha_status='armed_home',
        )

    async def test_integration_event_arming_arm_stay_if_disarm(self):
        await self._test_integration_event_arming(
            from_status='DISARM',
            to_status='ARM_STAY',
            ha_status='armed_home',
        )

    async def test_integration_event_arming_arm_away_if_arm_away(self):
        await self._test_integration_event_arming(
            from_status='ARM_AWAY',
            to_status='ARM_AWAY',
        )

    async def test_integration_event_arming_arm_away_if_exit_delay(self):
        await self._test_integration_event_arming(
            from_status='EXIT_DELAY',
            to_status='ARM_AWAY',
            ha_status='armed_away',
        )

    async def test_integration_event_arming_arm_away_if_disarm(self):
        await self._test_integration_event_arming(
            from_status='DISARM',
            to_status='ARM_AWAY',
            ha_status='armed_away',
        )

    async def test_integration_event_arming_entry_delay_if_entry_delay(self):
        await self._test_integration_event_arming(
            from_status='ENTRY_DELAY',
            to_status='ENTRY_DELAY',
        )

    async def test_integration_event_arming_entry_delay_if_arm_away(self):
        await self._test_integration_event_arming(
            from_status='ARM_AWAY',
            to_status='ENTRY_DELAY',
            ha_status='pending',
        )

    async def test_integration_event_arming_entry_delay_if_arm_stay(self):
        await self._test_integration_event_arming(
            from_status='ARM_STAY',
            to_status='ENTRY_DELAY',
            ha_status='pending',
        )

    async def test_integration_event_arming_exit_delay_if_exit_delay(self):
        await self._test_integration_event_arming(
            from_status='EXIT_DELAY',
            to_status='EXIT_DELAY',
        )

    async def test_integration_event_arming_exit_delay_if_disarm(self):
        await self._test_integration_event_arming(
            from_status='DISARM',
            to_status='EXIT_DELAY',
            ha_status='arming',
        )

    async def test_integration_event_arming_arm_away_exit_delay_if_disarm(self):
        await self._test_integration_event_arming(
            from_status='DISARM',
            to_status='ARM-AWAY-EXIT-DELAY',
            ha_status='arming',
        )

    async def test_integration_event_arming_arm_stay_exit_delay_if_disarm(self):
        await self._test_integration_event_arming(
            from_status='DISARM',
            to_status='ARM-STAY-EXIT-DELAY',
            ha_status='arming',
        )

    async def _test_integration_event_alarm(self, alarm_type=''):
        panel, gw, _, _ = await self._ready_panel_and_gw()

        event = {
            'event': 'ALARM',
            'alarm_type': alarm_type,
            'partition_id': 0,
            'version': 1,
            'requestID': '<request_id>',
        }
        await panel.writeline(event)

        published_state = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/alarm_control_panel/'
                              'qolsys_panel/partition0/state'},
        )

        published_attrs = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/alarm_control_panel/'
                              'qolsys_panel/partition0/attributes'},
            continued=True,
        )

        self.assertIsNotNone(published_state)
        self.assertEqual('triggered', published_state['payload'])

        partition = gw._state.partition(0)
        self.assertEqual('ALARM', partition.status)

        if alarm_type:
            self.assertIsNotNone(published_attrs)
            self.assertJsonSubDictEqual(
                {'alarm_type': alarm_type},
                published_attrs['payload'],
            )

            self.assertEqual(alarm_type, partition.alarm_type)
        else:
            self.assertIsNone(published_attrs)
            self.assertIsNone(partition.alarm_type)

        self.assertTrue(panel.is_client_connected)

    async def test_integration_event_alarm_default(self):
        await self._test_integration_event_alarm(
            alarm_type='',
        )

    async def test_integration_event_alarm_police(self):
        await self._test_integration_event_alarm(
            alarm_type='POLICE',
        )

    async def test_integration_event_alarm_fire(self):
        await self._test_integration_event_alarm(
            alarm_type='FIRE',
        )

    async def test_integration_event_alarm_auxiliary(self):
        await self._test_integration_event_alarm(
            alarm_type='AUXILIARY',
        )

    async def _test_integration_event_error(self, error_type, error_desc,
                                            extra_expect=None, init_data=None):
        if init_data:
            panel = init_data.panel
            gw = init_data.gw
        else:
            panel, gw, _, _ = await self._ready_panel_and_gw(
                partition_ids=[0],
                zone_ids=[10000],
                partition_status={
                    0: 'ARM_STAY',
                },
            )

        event = {
            'event': 'ERROR',
            'error_type': error_type,
            'partition_id': 0,
            'description': error_desc,
            'nonce': 'qolsys',
            'version': 1,
            'requestID': '<request_id>',
        }
        await panel.writeline(event)

        attributes = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': 'homeassistant/alarm_control_panel/'
                              'qolsys_panel/partition0/attributes'},
        )

        self.assertIsNotNone(attributes)

        expected = {
            'last_error_type': error_type,
            'last_error_desc': error_desc,
            'last_error_at': ISODATE,
        }
        if extra_expect:
            expected.update(extra_expect)
        self.assertJsonSubDictEqual(expected, attributes['payload'])

        return SimpleNamespace(
            panel=panel,
            gw=gw,
        )

    async def test_integration_event_error_usercode(self):
        await self._test_integration_event_error(
            error_type='usercode',
            error_desc='Please Enable Six Digit User Code or '
                       'KeyPad is already Locked',
        )

    async def test_integration_event_error_disarm_failed(self):
        with self.subTest(msg='Disarm failed error is handled properly'):
            init_data = await self._test_integration_event_error(
                error_type='DISARM_FAILED',
                error_desc='Invalid usercode',
                extra_expect={
                    'disarm_failed': 1,
                },
            )

        with self.subTest(msg='Other disarm failed error keeps raising the counter'):
            await self._test_integration_event_error(
                error_type='DISARM_FAILED',
                error_desc='Invalid usercode',
                extra_expect={
                    'disarm_failed': 2,
                },
                init_data=init_data,
            )

        with self.subTest(msg='Disarming the panel resets the counter'):
            panel = init_data.panel
            gw = init_data.gw

            self.assertEqual(2, gw._state.partition(0).disarm_failed)

            event = {
                'event': 'ARMING',
                'arming_type': 'DISARM',
                'partition_id': 0,
                'version': 1,
                'requestID': '<request_id>',
            }
            await panel.writeline(event)

            attributes = await gw.wait_for_next_mqtt_publish(
                timeout=self._TIMEOUT,
                filters={'topic': 'homeassistant/alarm_control_panel/'
                                  'qolsys_panel/partition0/attributes'},
            )

            self.assertIsNotNone(attributes)

            self.assertJsonSubDictEqual({'disarm_failed': 0}, attributes['payload'])
            self.assertEqual(0, gw._state.partition(0).disarm_failed)
