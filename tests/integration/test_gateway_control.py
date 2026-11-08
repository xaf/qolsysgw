import json

import testenv  # noqa: F401
from testbase import TestQolsysGatewayBase


class TestIntegrationQolsysGatewayControl(TestQolsysGatewayBase):

    async def test_integration_control_with_wrong_session_token(self):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[10000],
        )

        control = {
            'action': 'DISARM',
            'partition_id': 0,
            'session_token': 'this is not the session token',
        }

        gw.mqtt_publish(
            'homeassistant/alarm_control_panel/qolsys_panel/set',
            json.dumps(control),
            namespace='mqtt',
        )

        error = await gw.wait_for_next_log(
            timeout=self._TIMEOUT,
            filters={'level': 'ERROR'},
            match='^invalid session token',
        )

        self.assertIsNotNone(error)


    async def test_integration_control_stale_session_refreshes_discovery_once(self):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[10000],
        )

        config_topic = (
            'homeassistant/alarm_control_panel/'
            'qolsys_panel/partition0/config'
        )
        command_topic = 'homeassistant/alarm_control_panel/qolsys_panel/set'
        stale_command = json.dumps({
            'action': 'ARM_HOME',
            'partition_id': 0,
            'session_token': 'expired token',
        })
        startpos = len(gw.PUBLISHED.MESSAGES)

        gw.mqtt_publish(command_topic, stale_command, namespace='mqtt')

        error = await gw.wait_for_next_log(
            timeout=self._TIMEOUT,
            filters={'level': 'ERROR'},
            match='^invalid session token',
        )
        self.assertIsNotNone(error)

        refresh = await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            startpos=startpos,
            filters={'topic': config_topic},
        )
        self.assertIsNotNone(refresh)
        self.assertTrue(refresh['retain'])

        config = json.loads(refresh['payload'])
        template = json.loads(config['command_template'])
        self.assertEqual(gw._session_token, template['session_token'])

        # A second stale command within the two-minute cooldown must not
        # produce another discovery config update.
        gw.mqtt_publish(command_topic, stale_command, namespace='mqtt')
        error = await gw.wait_for_next_log(
            timeout=self._TIMEOUT,
            filters={'level': 'ERROR'},
            match='^invalid session token',
        )
        self.assertIsNotNone(error)

        config_publishes = [
            msg for msg in gw.PUBLISHED.MESSAGES[startpos:]
            if msg['topic'] == config_topic
        ]
        self.assertEqual(1, len(config_publishes))

    async def _test_control_arming(self, control_action, partition_status,
                                   arming_type, send_code=False,
                                   expect_error=None, expect_delay=None,
                                   secure_arm=False, panel_user_code=None,
                                   user_control_token=None, expect_bypass=None,
                                   send_delay=None, send_bypass=None,
                                   **kwargs):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[10000],
            partition_status={
                0: partition_status,
            },
            secure_arm=secure_arm,
            panel_user_code=panel_user_code,
            user_control_token=user_control_token,
            **kwargs,
        )

        session_token = user_control_token or gw._session_token

        control = {
            'action': control_action,
            'partition_id': 0,
            'session_token': session_token,
        }
        if send_code:
            control['code'] = '4242'
        if send_delay is not None:
            control['delay'] = send_delay
        if send_bypass is not None:
            control['bypass'] = send_bypass

        gw.mqtt_publish(
            'homeassistant/alarm_control_panel/qolsys_panel/set',
            json.dumps(control),
            namespace='mqtt',
        )

        if expect_error:
            error = await gw.wait_for_next_log(
                timeout=self._TIMEOUT,
                filters={'level': 'ERROR'},
                match=expect_error,
            )

            self.assertIsNotNone(error)
        else:
            action = await panel.wait_for_next_message(
                timeout=self._TIMEOUT,
                filters={'action': 'ARMING'},
            )

            self.assertIsNotNone(action)
            self.assertEqual(arming_type, action['arming_type'])
            self.assertEqual(0, action['partition_id'])
            self.assertEqual(gw.args['panel_token'], action['token'])

            if expect_delay is not None:
                self.assertEqual(expect_delay, action.get('delay'))
            else:
                assert 'delay' not in action

            if expect_bypass is not None:
                self.assertEqual(expect_bypass, action.get('bypass'))
            else:
                assert 'bypass' not in action

            if send_code:
                self.assertEqual('4242', action['usercode'])
            elif panel_user_code:
                self.assertEqual(panel_user_code, action['usercode'])

    async def test_integration_control_disarm(self):
        await self._test_control_arming(
            control_action='DISARM',
            partition_status='ARM_AWAY',
            arming_type='DISARM',
            send_code=True,
        )

    async def test_integration_control_disarm_without_code(self):
        await self._test_control_arming(
            control_action='DISARM',
            partition_status='ARM_AWAY',
            arming_type='DISARM',
            expect_error='^Cannot perform action without '
                         'a configured panel code',
        )

    async def test_integration_control_disarm_with_panel_code(self):
        await self._test_control_arming(
            control_action='DISARM',
            partition_status='ARM_AWAY',
            arming_type='DISARM',
            panel_user_code='1337',
        )

    async def test_integration_control_disarm_with_panel_code_no_disarm_code_required_no_ha_check_user_code(self):
        await self._test_control_arming(
            control_action='DISARM',
            partition_status='ARM_AWAY',
            arming_type='DISARM',
            panel_user_code='1337',
            code_disarm_required=False,
            ha_check_user_code=False,
        )

    async def test_integration_control_disarm_with_panel_code_and_user_control_token(self):
        await self._test_control_arming(
            control_action='DISARM',
            partition_status='ARM_AWAY',
            arming_type='DISARM',
            panel_user_code='1337',
            user_control_token='My$ecr3tT0k3n!',
        )

    async def test_integration_control_disarm_if_code_disarm_required_and_ha_check_code(self):
        await self._test_control_arming(
            control_action='DISARM',
            partition_status='ARM_AWAY',
            arming_type='DISARM',
            panel_user_code='1337',
            code_disarm_required=True,
            ha_check_user_code=True,
        )

    async def test_integration_control_disarm_with_wrong_code_if_code_disarm_required(self):
        await self._test_control_arming(
            control_action='DISARM',
            partition_status='ARM_AWAY',
            arming_type='DISARM',
            panel_user_code='1337',
            code_disarm_required=True,
            ha_check_user_code=False,
            send_code=True,
            expect_error='^Code received in the control command invalid',
        )

    async def test_integration_control_arm_away(self):
        await self._test_control_arming(
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
        )

    async def test_integration_control_arm_away_with_exit_delay_if_configured(self):
        await self._test_control_arming(
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            arm_away_exit_delay=30,
            expect_delay=30,
        )

    async def test_integration_control_arm_away_with_exit_delay_if_sent(self):
        await self._test_control_arming(
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            send_delay=30,
            expect_delay=30,
        )

    async def test_integration_control_arm_away_secure_arm_with_code(self):
        await self._test_control_arming(
            secure_arm=True,
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            send_code=True,
        )

    async def test_integration_control_arm_away_secure_arm_with_panel_code(self):
        await self._test_control_arming(
            secure_arm=True,
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            panel_user_code='1337',
        )

    async def test_integration_control_arm_away_with_panel_code_if_code_arm_required_and_ha_check_code(self):
        await self._test_control_arming(
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            panel_user_code='1337',
            code_arm_required=True,
            ha_check_user_code=True,
        )

    async def test_integration_control_arm_away_with_panel_code_and_wrong_code_if_code_arm_required(self):
        await self._test_control_arming(
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            panel_user_code='1337',
            code_arm_required=True,
            ha_check_user_code=False,
            send_code=True,
            expect_error='^Code received in the control command invalid',
        )

    async def test_integration_control_arm_away_secure_arm_without_code(self):
        await self._test_control_arming(
            secure_arm=True,
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            expect_error='^Cannot perform action without '
                         'a configured panel code',
        )

    async def test_integration_control_arm_away_bypass_true_if_configured(self):
        await self._test_control_arming(
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            arm_away_bypass=True,
            expect_bypass='true',
        )

    async def test_integration_control_arm_away_bypass_false_if_configured(self):
        await self._test_control_arming(
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            arm_away_bypass=False,
            expect_bypass='false',
        )

    async def test_integration_control_arm_away_bypass_true_if_sent(self):
        await self._test_control_arming(
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            send_bypass=True,
            expect_bypass='true',
        )

    async def test_integration_control_arm_away_bypass_false_if_sent(self):
        await self._test_control_arming(
            control_action='ARM_AWAY',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            send_bypass=False,
            expect_bypass='false',
        )

    async def test_integration_control_arm_vacation(self):
        await self._test_control_arming(
            control_action='ARM_VACATION',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
        )

    async def test_integration_control_arm_home(self):
        await self._test_control_arming(
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
        )

    async def test_integration_control_arm_home_with_exit_delay_if_configured(self):
        await self._test_control_arming(
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            arm_stay_exit_delay=42,
            expect_delay=42,
        )

    async def test_integration_control_arm_home_with_exit_delay_if_sent(self):
        await self._test_control_arming(
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            send_delay=42,
            expect_delay=42,
        )

    async def test_integration_control_arm_home_secure_arm_with_code(self):
        await self._test_control_arming(
            secure_arm=True,
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            send_code=True,
        )

    async def test_integration_control_arm_home_secure_arm_with_panel_code(self):
        await self._test_control_arming(
            secure_arm=True,
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            panel_user_code='1337',
        )

    async def test_integration_control_arm_home_secure_arm_without_code(self):
        await self._test_control_arming(
            secure_arm=True,
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            expect_error='^Cannot perform action without '
                         'a configured panel code',
        )

    async def test_integration_control_arm_home_bypass_true_if_configured(self):
        await self._test_control_arming(
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            arm_stay_bypass=True,
            expect_bypass='true',
        )

    async def test_integration_control_arm_home_bypass_false_if_configured(self):
        await self._test_control_arming(
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            arm_stay_bypass=False,
            expect_bypass='false',
        )

    async def test_integration_control_arm_home_bypass_true_if_sent(self):
        await self._test_control_arming(
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            send_bypass=True,
            expect_bypass='true',
        )

    async def test_integration_control_arm_home_bypass_false_if_sent(self):
        await self._test_control_arming(
            control_action='ARM_HOME',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            send_bypass=False,
            expect_bypass='false',
        )

    async def test_integration_control_arm_night(self):
        await self._test_control_arming(
            control_action='ARM_NIGHT',
            partition_status='DISARM',
            arming_type='ARM_STAY',
        )

    async def test_integration_control_arm_custom_bypass_arms_away_with_bypass(self):
        await self._test_control_arming(
            control_action='ARM_CUSTOM_BYPASS',
            partition_status='DISARM',
            arming_type='ARM_AWAY',
            expect_bypass='true',
        )

    async def test_integration_control_arm_custom_bypass_arms_stay_with_bypass(self):
        await self._test_control_arming(
            control_action='ARM_CUSTOM_BYPASS',
            partition_status='DISARM',
            arming_type='ARM_STAY',
            arm_type_custom_bypass='arm_stay',
            expect_bypass='true',
        )

    async def _test_control_trigger(self, control_action, alarm_type,
                                    send_code=False, expect_error=None,
                                    **kwargs):
        panel, gw, _, _ = await self._ready_panel_and_gw(
            partition_ids=[0],
            zone_ids=[10000],
            **kwargs,
        )

        session_token = gw._session_token

        control = {
            'action': control_action,
            'partition_id': 0,
            'session_token': session_token,
        }
        if send_code:
            control['code'] = '4242'

        gw.mqtt_publish(
            'homeassistant/alarm_control_panel/qolsys_panel/set',
            json.dumps(control),
            namespace='mqtt',
        )

        if expect_error:
            error = await gw.wait_for_next_log(
                timeout=self._TIMEOUT,
                filters={'level': 'ERROR'},
                match=expect_error,
            )

            self.assertIsNotNone(error)
        else:
            action = await panel.wait_for_next_message(
                timeout=self._TIMEOUT,
                filters={'action': 'ALARM'},
            )

            self.assertIsNotNone(action)
            self.assertEqual(alarm_type, action['alarm_type'])
            self.assertEqual(0, action['partition_id'])
            self.assertEqual(gw.args['panel_token'], action['token'])

    async def test_integration_control_trigger_default(self):
        await self._test_control_trigger(
            control_action='TRIGGER',
            alarm_type='POLICE',
        )

    async def test_integration_control_trigger_if_code_trigger_required_and_ha_check_code(self):
        await self._test_control_trigger(
            control_action='TRIGGER',
            alarm_type='POLICE',
            code_trigger_required=True,
            ha_check_user_code=True,
            panel_user_code='1337',
        )

    async def test_integration_control_trigger_with_wrong_code_if_code_trigger_required(self):
        await self._test_control_trigger(
            control_action='TRIGGER',
            alarm_type='POLICE',
            code_trigger_required=True,
            ha_check_user_code=False,
            panel_user_code='1337',
            send_code=True,
            expect_error='^Code received in the control command invalid'
        )

    async def test_integration_control_trigger_police(self):
        await self._test_control_trigger(
            control_action='TRIGGER_POLICE',
            alarm_type='POLICE',
        )

    async def test_integration_control_trigger_fire(self):
        await self._test_control_trigger(
            control_action='TRIGGER_FIRE',
            alarm_type='FIRE',
        )

    async def test_integration_control_trigger_auxiliary(self):
        await self._test_control_trigger(
            control_action='TRIGGER_AUXILIARY',
            alarm_type='AUXILIARY',
        )
