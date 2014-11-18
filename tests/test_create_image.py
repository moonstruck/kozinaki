"""
Tests for EC2 cloud driver
"""
import unittest
from nova import rpc
from nova import objects
from nova.virt import fake
from oslo.config import cfg
from libcloud.compute import types
from virt.kozinaki import driver
from test_base import KozinakiEC2TestBase


class KozinakiEC2TestCase(KozinakiEC2TestBase):

    def setUp(self):
        self.driver = driver.KozinakiDriver(fake.FakeVirtAPI())
        self.test_dict = self._create_test_dict()
        self.driver.spawn(**self.test_dict['spawn_params'])

    def tearDown(self):
        return
#         self.driver.destroy(None, self.test_dict['instance'], None)

    def test_create_image_ok(self):
        # this is for waiting until node is present
        node = self.get_node(self.test_dict['instance'], self.driver)
        self.driver.snapshot(**self.test_dict['create_image_params'])
#         node = self.get_node(self.test_dict['instance'], self.driver)
        exp_state = types.NodeState.PENDING

        self.assertEqual(node.state, exp_state)


if __name__ == '__main__':
    objects.register_all()
    rpc.set_defaults(control_exchange='nova')
    cfg.CONF(['--config-file=/root/Envs/conf/nova-compute.conf'],
             project='nova',
             version='0.1')
    rpc.init(cfg.CONF)
    unittest.main()
