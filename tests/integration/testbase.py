import json
import unittest

import testenv  # noqa: F401
from testutils.mock_panel import PanelServer
from testutils.fixtures_data import get_summary

from gateway import QolsysGateway
from qolsys.config import QolsysGatewayConfig


class TestQolsysGatewayBase(unittest.IsolatedAsyncioTestCase):

    _TIMEOUT = .1

    def assertJsonDictEqual(self, expected, actual):
        if not isinstance(actual, dict):
            actual = json.loads(actual)

        self.assertDictEqual(expected, actual)

    def assertJsonSubDictEqual(self, expected, actual):
        if not isinstance(actual, dict):
            actual = json.loads(actual)

        actual_subset = {k: v for k, v in actual.items() if k in expected}
        self.assertDictEqual(expected, actual_subset)

    async def _init_panel_and_gw(self, **kwargs):
        # Start a panel panel
        panel = PanelServer()
        await panel.start()

        # Initialize a gateway instance to connect to that panel
        gw = QolsysGateway()
        gw.args = {
            'panel_host': 'localhost',
            'panel_port': panel.port,
        }

        for k, v in kwargs.items():
            if k in QolsysGatewayConfig._DEFAULT_CONFIG:
                if k not in gw.args:
                    gw.args[k] = v
                else:
                    raise AttributeError(f"Cannot redefine '{k}'")
            else:
                raise AttributeError(f"Unknown attribute '{k}'")

        if 'panel_token' not in gw.args:
            gw.args['panel_token'] = '<panel_token>'

        await gw.initialize()

        return panel, gw

    async def _init_panel_and_gw_and_wait(self, return_info=False, **kwargs):
        panel, gw = await self._init_panel_and_gw(**kwargs)

        if return_info:
            # Wait until the INFO message is received
            info = await panel.wait_for_next_message(
                timeout=self._TIMEOUT,
                filters={'action': 'INFO'},
                startpos=0,
            )

            return panel, gw, info

        # If we didn't want to return the info message, just
        # wait for the next message and raise on timeout
        await panel.wait_for_next_message(
            timeout=self._TIMEOUT,
            raise_on_timeout=True,
            startpos=0,
        )

        return panel, gw

    async def _ready_panel_and_gw(self, secure_arm=False, partition_ids=None,
                                  zone_ids=None, partition_status=None,
                                  **kwargs):
        panel, gw = await self._init_panel_and_gw_and_wait(**kwargs)

        summary = get_summary(
            secure_arm=secure_arm,
            partition_ids=partition_ids,
            zone_ids=zone_ids,
            partition_status=partition_status,
        )

        await panel.writeline(summary.event)

        # We need to wait for the whole side effects to finish happening,
        # before we can check the final result; we check that by waiting
        # for the last entity's last topic to be published
        await gw.wait_for_next_mqtt_publish(
            timeout=self._TIMEOUT,
            filters={'topic': summary.last_topic},
        )

        # Strip 'qolsys_panel_' prefix from all entity ids
        summary.entity_ids = [
            eid.removeprefix('qolsys_panel_')
            for eid in summary.entity_ids
        ]

        return panel, gw, summary.entity_ids, summary.topics
