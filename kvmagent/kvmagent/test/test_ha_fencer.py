import unittest
import mock
from kvmagent.plugins.ha_plugin import AbstractStorageFencer


class FakeStorageFencer(AbstractStorageFencer):
    def __init__(self):
        super(FakeStorageFencer, self).__init__(5, 5, "test", [])

    def get_ha_fencer_name(self):
        return "FakeStorageFencer"


class TestAbstractStorageFencer(unittest.TestCase):
    @mock.patch('kvmagent.plugins.ha_plugin.AbstractStorageFencer.read_fencer_hearbeat')
    def test_check_fencer_heartbeat_raises_exception(self, mock_read_fencer_heartbeat):
        # Arrange
        fencer = FakeStorageFencer()

        # Mock read_fencer_heartbeat to raise an exception
        mock_read_fencer_heartbeat.side_effect = Exception("Heartbeat read error")

        # Act & Assert
        with self.assertRaises(Exception) as context:
            fencer.check_fencer_heartbeat("fakeHostUuid", 5, 5, 5, "fakePrimaryStorageUuid")
        self.assertEqual("Heartbeat read error", str(context.exception))

    @mock.patch('kvmagent.plugins.ha_plugin.AbstractStorageFencer.read_fencer_hearbeat')
    def test_check_fencer_heartbeat_returns_nothing(self, mock_read_fencer_heartbeat):
        # Arrange
        fencer = FakeStorageFencer()

        # Mock read_fencer_heartbeat to return nothing
        mock_read_fencer_heartbeat.return_value = (None, None)

        # Act & Assert
        with self.assertRaises(Exception) as context:
            fencer.check_fencer_heartbeat("fakeHostUuid", 5, 5, 5, "fakePrimaryStorageUuid")
        self.assertIn("cannot read content from hb", str(context.exception))

if __name__ == '__main__':
    unittest.main()