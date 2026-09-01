import os
import subprocess
import unittest

from unittest import mock

from tests.unit.qolsysgw.qolsys.testenv import FIXTURES_DIR

from qolsys.utils import get_mac_from_host


class TestUnitGetMacFromHost(unittest.TestCase):

    def test_unit_returns_none_on_subprocess_error(self):
        with mock.patch('subprocess.run', side_effect=subprocess.SubprocessError):
            self.assertIsNone(get_mac_from_host('random_host'))

    def test_unit_returns_none_on_missing_arp_binary(self):
        with mock.patch('subprocess.run', side_effect=FileNotFoundError):
            self.assertIsNone(get_mac_from_host('random_host'))

    def test_unit_returns_none_on_mac_address_not_found(self):
        fixture = os.path.join(FIXTURES_DIR, 'subprocess_run_arp_unknown_host.txt')
        with open(fixture, 'rb') as f:
            output = f.read()

        with mock.patch('subprocess.run', return_value=mock.Mock(stdout=output)):
            self.assertIsNone(get_mac_from_host('random_host'))

    def test_unit_returns_mac_address_on_success(self):
        fixture = os.path.join(FIXTURES_DIR, 'subprocess_run_arp_known_host.txt')
        with open(fixture, 'rb') as f:
            output = f.read()

        with mock.patch('subprocess.run', return_value=mock.Mock(stdout=output)):
            self.assertEqual(get_mac_from_host('random_host'),
                             '01:12:76:ef:11:02')


if __name__ == '__main__':
    unittest.main()
