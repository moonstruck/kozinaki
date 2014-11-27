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
Base class for Kozinaki unit testing.
"""

import unittest
import uuid
import logging
from nova import rpc
from nova import objects
from oslo.config import cfg
from nova.virt.fake import FakeVirtAPI
from virt.kozinaki.driver import KozinakiDriver
from virt.kozinaki.utils import timeout_call

NODE_INFO = 'Node: {} State: {} Size: {}'


class NodeSize(object):
    """ Fake node size class. """
    id = None


class KozinakiTestBase(unittest.TestCase):
    """
    Base class for Kozinaki Cloud Driver testing.
    """

    def setUp(self):
        """
        Provides initial setup of driver and class objects.
        """
        # nova environment setup
        objects.register_all()
        rpc.set_defaults(control_exchange='nova')
        cfg.CONF(['--config-file=/root/envs/conf/nova-compute.conf'],
                 project='nova',
                 version='0.1')
        rpc.init(cfg.CONF)
        # logger setup
        self.log = logging.getLogger(__name__)
        self.log.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        ch.setFormatter(fmt)
        self.log.addHandler(ch)
        # setup driver and test
        self.log.info("Creating driver handler")
        self.driver = KozinakiDriver(FakeVirtAPI())
        self.nodes = []

    def tearDown(self):
        """
        Executed after any test end.
        """
        for node in self.nodes:
            self.destroy(node)

    def create_test_objects(
            self, name, size_id, image_id,
            provider_name, provider_region):

        new_uuid = str(uuid.uuid4())
        instance_name = self.driver._create_instance_name(new_uuid)

        provider_metadata = self.create_provider_metadata_dict(
            instance_name, provider_name, provider_region, image_id)

        image = self.create_image_dict(image_id, provider_metadata)

        instance = self.create_instance_dict(
            name, new_uuid, size_id, provider_metadata)

        return instance, image, provider_metadata

    def create_instance_dict(self, name, new_uuid, size_id, provider_metadata):
        system_metadata = {
            'instance_type_id': 1,
            'instance_type_name': size_id,
            'instance_type_memory_mb': 512,
            'instance_type_vcpus': 1,
            'instance_type_root_gb': 1024,
            'instance_type_ephemeral_gb': 0,
            'instance_type_flavorid': 'id',
            'instance_type_swap': 0,
            'instance_type_rxtx_factor': 0,
            'instance_type_vcpu_weight': 0
        }
        instance = {
            'name': name,
            'uuid': new_uuid,
            'system_metadata': system_metadata,
            'metadata': provider_metadata
        }
        return instance

    def create_image_dict(self, image_id, provider_metadata):
        image = {
            'name': image_id,
            'container_format': 'kozinaki',
            'properties': provider_metadata
        }
        return image

    def create_provider_metadata_dict(self, instance_name,
                                      name, region, image_id):

        metadata = {
            'provider_instance_name': instance_name,
            'provider_name': name,
            'provider_region': region,
            'provider_image': image_id
        }
        return metadata

    @timeout_call(wait_period=3, timeout=600)
    def get_node(self, instance, state=None):
        self.log.info(
            'Get node: %s' % instance['metadata']['provider_instance_name'])
        node = self.driver._get_provider_instance(instance)
        if node:
            self.log.info(NODE_INFO.format(node.name, node.state, node.size))
            if state is None:
                return node
            elif node.state == state:
                return node
        self.log.warning('Still waiting for node...')
        raise Exception('Node not found or not in %s state' % state)

    def get_current_state(self, node):
        nodes = self.driver.driver.list_nodes()
        node = next((x for x in nodes if x.name == node.name), node)
        return node.state

    def spawn(self, instance, image):
        self.log.info('Spawning test node: %s' % instance['metadata']['provider_instance_name'])
        self.driver.spawn(
            context=None,
            instance=instance,
            image_meta=image,
            injected_files=None,
            admin_password=None,
            network_info=None,
            block_device_info=None)
        self.nodes.append(instance)

    def destroy(self, instance):
        self.log.info('Destroying test node')
        self.driver.destroy(
            context=None,
            instance=instance,
            network_info=None,
            block_device_info=None)
