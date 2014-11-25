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
Resize test for Kozinaki Rackspace provider
"""

import unittest
from libcloud.compute.types import NodeState
from base import KozinakiTestBase


class KozinakiRackspaceTestCase(KozinakiTestBase):

    def test_resize_ok(self):
        instance, image, metadata = self.create_test_objects(
            name='test',
            size_id='2',
            image_id='df924994-b686-449a-86e3-1876998022aa',
            provider_name='RACKSPACE',
            provider_region='')

        resized_instance, _, _ = self.create_test_objects(
            name='test',
            size_id='3',
            image_id='df924994-b686-449a-86e3-1876998022aa',
            provider_name='RACKSPACE',
            provider_region='')

        self.spawn(instance, image)

        # wait until spawn finish
        self.get_node(instance, state=NodeState.RUNNING)

        self.log.info('Resize execution')
        self.driver.finish_migration(
            context=None,
            migration=None,
            instance=resized_instance,
            disk_info=None,
            network_info=None,
            image_meta=None,
            resize_instance=True,
            block_device_info=None,
            power_on=True)

        node = self.get_node(instance, state=NodeState.PENDING)
        self.assertEqual(node.state, NodeState.RUNNING)


if __name__ == '__main__':
    unittest.main()
