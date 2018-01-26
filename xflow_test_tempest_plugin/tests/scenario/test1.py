import logging as logger
from tempest import test
from xflow_test_tempest_plugin.tests.scenario import manager

class SampleClass(manager.ScenarioTest):

	def sample(self):
		assertEqual('ello', 'ello')

