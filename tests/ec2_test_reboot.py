# Copyright (c) 2014 CompuNova Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Reboot test for Kozinaki EC2 provider
"""

import unittest
from libcloud.compute.types import NodeState
from base import KozinakiTestBase


class KozinakiEC2TestCase(KozinakiTestBase):

    def test_reboot_ok(self):

        instance, image, metadata = self.create_test_objects(
            name='test',
            size_id='t1.micro',
            image_id='ami-696e652c',
            provider_name='EC2',
            provider_region='US_WEST')

        self.spawn(instance, image)

        self.get_node(instance, state=NodeState.RUNNING)

        self.log.info('Reboot execution')
        self.driver.reboot(
            context=None,
            instance=instance,
            network_info=None,
            reboot_type=None,
            block_device_info=None)

        node = self.get_node(instance, state=NodeState.RUNNING)
        self.assertEqual(node.state, NodeState.RUNNING)

if __name__ == '__main__':
    unittest.main()
