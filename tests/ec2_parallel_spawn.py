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
Spawning 5 instances parallel.
"""

import unittest
import copy
import uuid
import threading
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
        for obj in objects:
            t = threading.Thread(target=self.spawn,
                                 args=(obj['instance'],
                                       obj['image']))
            t.start()

        main_thread = threading.currentThread()
        for t in threading.enumerate():
            if t is main_thread:
                continue
            t.join()

        for obj in copy.copy(objects):
            try:
                self.get_node(obj['instance'], state=NodeState.RUNNING)
            except:
                self.log.error('Failed to spawn instance')
                objects.remove(obj)

        self.log.info('Launched %d instances' % len(objects))
        self.assertEqual(len(objects), 5)


if __name__ == '__main__':
    unittest.main()
