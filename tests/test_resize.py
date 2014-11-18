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

    def test_resize_ok(self):
        # this is for waiting until node is present
        self.get_node(self.test_dict['instance'], self.driver)
        self.driver.finish_migration(**self.test_dict['resize_params'])
        node = self.get_node(self.test_dict['instance'], self.driver)
        exp_state = types.NodeState.RUNNING
        try:
            real_state = self.get_node_state(
                self.test_dict['instance'],
                self.driver,
                expected=exp_state)
        except:
            real_state = node.state
        self.assertEqual(real_state, exp_state)
#         self.assertEqual(node.size, exp_size)


if __name__ == '__main__':
    objects.register_all()
    rpc.set_defaults(control_exchange='nova')
    cfg.CONF(['--config-file=/root/Envs/conf/nova-compute.conf'],
             project='nova',
             version='0.1')
    rpc.init(cfg.CONF)
    unittest.main()
