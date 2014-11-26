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
Combine test for Kozinaki EC2 provider
Spawning 5 instances and executing different action on each.
"""

import unittest
import copy
import uuid
from libcloud.compute.types import NodeState
from base import KozinakiTestBase


class KozinakiEC2TestCase(KozinakiTestBase):

    def test_combine(self):
        objects = []
        for x in range(5):
            instance, image, metadata = self.create_test_objects(
                name='test' + str(x),
                size_id='t1.micro',
                image_id='ami-696e652c',
                provider_name='EC2',
                provider_region='US_WEST')
            objects.append({
                'instance': instance,
                'image': image,
                'metadata': metadata})

        self.log.info('Spawn execution for 5 instances')
        for obj in copy.copy(objects):
            self.log.info('Spawn')
            self.driver.spawn(
                context=None,
                instance=obj['instance'],
                image_meta=obj['image'],
                injected_files=None,
                admin_password=None,
                network_info=None,
                block_device_info=None)
            try:
                self.get_node(obj['instance'], state=NodeState.RUNNING)
            except:
                self.log.error('Failed to spawn instance')
                objects.remove(obj)

        self.log.info('Launched %d instances' % len(objects))
        self.assertEqual(len(objects), 5)

        # Reboot
        self.log.info('Reboot execution')
        self.driver.reboot(
            context=None,
            instance=objects[0]['instance'],
            network_info=None,
            reboot_type=None,
            block_device_info=None)

        node = self.get_node(objects[0]['instance'], state=NodeState.REBOOTING)
        self.assertEqual(node.state, NodeState.REBOOTING)

        # Resize
        resized_instance = copy.copy(objects[1]['instance'])
        resized_instance['system_metadata']['instance_type_name'] = 'm1.small'

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

        node = self.get_node(objects[1]['instance'], state=NodeState.RUNNING)
        self.assertEqual(node.state, NodeState.RUNNING)

        # Snapshot
        self.log.info('Snapshot execution')
        # new unique name for snapshot
        new_name = "combine-" + str(uuid.uuid1()).split("-")[0]
        self.driver.snapshot(
            context=None,
            instance=objects[2]['instance'],
            name=new_name,
            update_task_state=None)

        node = self.get_node(objects[2]['instance'])
        self.assertEqual(node.state, NodeState.RUNNING)

        # Destroy
        self.log.info('Destroy execution')
        self.driver.destroy(
            context=None,
            instance=objects[3]['instance'],
            network_info=None,
            block_device_info=None)

        node = self.get_node(
            objects[3]['instance'], state=NodeState.TERMINATED)
        self.assertEqual(node.state, NodeState.TERMINATED)


if __name__ == '__main__':
    unittest.main()
