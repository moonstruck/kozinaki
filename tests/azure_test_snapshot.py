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
Snapshot test for Kozinaki Azure provider
"""

import unittest
from libcloud.compute.types import NodeState
from base import KozinakiTestBase


class KozinakiAzureTestCase(KozinakiTestBase):

    def test_snapshot_ok(self):

        instance, image, metadata = self.create_test_objects(
            name='test',
            size_id='ExtraSmall',
            image_id='149f346a-1e9a-4e53-93d9-2a47a5b0b44d',
            provider_name='AZURE',
            provider_region='')

        self.spawn(instance, image)

        # wait until spawn finish
        self.get_node(instance, state=NodeState.RUNNING)

        self.driver.snapshot(
            context=None,
            instance=instance,
            name='test_snapshot',
            update_task_state=None)

        node = self.get_node(instance)
        self.assertEqual(node.state, NodeState.PENDING)

if __name__ == '__main__':
    unittest.main()
