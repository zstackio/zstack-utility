'''

@author: frank
'''
import unittest
import os.path
from ..utils import plugin

class TestPlugin(unittest.TestCase):

    def test_plugin_start(self):
        plugin_rgty = plugin.PluginRegistry(os.path.abspath('zstacklib/test/plugin/plugins.cfg'))
        config = {'key':'value'}
        plugin_rgty.configure_plugins(config)
        plugin_rgty.start_plugins()
        plugin1 = plugin_rgty.get_plugin('Plugin1')
        self.assertTrue(plugin1.start_called)
        self.assertEqual(config['key'], plugin1.config['key'])
        
    def test_plugin_stop(self):
        plugin_rgty = plugin.PluginRegistry(os.path.abspath('zstacklib/test/plugin/plugins.cfg'))
        plugin_rgty.start_plugins()
        plugin_rgty.stop_plugins()
        plugin1 = plugin_rgty.get_plugin('Plugin1')
        self.assertTrue(plugin1.stop_called)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()