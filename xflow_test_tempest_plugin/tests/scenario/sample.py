import logging as logger
from tempest.lib import base

class SampleClass(base.BaseTestCase):

	def sample(self):
		self.assertEqual('ello', 'ello')

