"""
Module contains base class for EC2 Cloud Driver test cases
"""

import unittest
import uuid
from copy import copy
from virt.kozinaki.utils import timeout_call


class NodeSize(object):
    """ Fake node size class """
    id = None


class KozinakiEC2TestBase(unittest.TestCase):
    """ Base class for EC2 Cloud Driver testing """

    def _create_test_dict(self):
        result = {}
        sys_meta = {
            'instance_type_id': 1,
            'instance_type_name': 't1.micro',
            'instance_type_memory_mb': 512,
            'instance_type_vcpus': 1,
            'instance_type_root_gb': 1024,
            'instance_type_ephemeral_gb': 0,
            'instance_type_flavorid': "id",
            'instance_type_swap': 0,
            'instance_type_rxtx_factor': 0,
            'instance_type_vcpu_weight': 0
            }
        self.size = NodeSize()
        self.size.id = 't1.micro'
        self.new_size = NodeSize()
        self.new_size.id = 'm1.small'

        new_uuid = str(uuid.uuid4())
        instance = {'name': 'ec2_test',
                    'uuid': new_uuid,
                    'system_metadata': sys_meta,
                    'metadata': {
                        'provider_instance_name': 'os-' + new_uuid.split('-')[4],
                        'provider_name': 'EC2',
                        'provider_region': 'US_WEST',
                        'provider_image': 'ami-696e652c'}
                    }
        instance['system_metadata']['instance_type_name'] = self.size.id

        resized_instance = copy(instance)
        new_sys_meta = copy(sys_meta)
        new_sys_meta['instance_type_name'] = self.new_size.id
        resized_instance['system_metadata'] = new_sys_meta
        image = {'name': 'ami-696e652c',
                 'container_format': 'ami_id',
                 'properties': {
                     'provider_name': 'EC2',
                     'provider_region': 'US_WEST',
                     'provider_image': 'ami-696e652c'}
                 }

        result['instance'] = instance
        result['resized_instance'] = resized_instance
        result['image'] = image
        result['spawn_params'] = dict(
            context=None,
            instance=instance,
            image_meta=image,
            injected_files=None,
            admin_password=None,
            network_info=None,
            block_device_info=None
            )
        result['reboot_params'] = dict(
            context=None,
            instance=instance,
            network_info=None,
            reboot_type=None,
            block_device_info=None
            )
        result['destroy_params'] = dict(
            context=None,
            instance=instance,
            network_info=None,
            block_device_info=None,
            )
        result['resize_params'] = dict(
            context=None,
            migration=None,
            instance=resized_instance,
            disk_info=None,
            network_info=None,
            image_meta=None,
            resize_instance=True,
            block_device_info=None,
            power_on=True
            )
        result['create_image_params'] = dict(
            context=None,
            instance=instance,
            name='test_snapshot',
            update_task_state=None)

        return result

    @timeout_call(wait_period=3, timeout=100)
    def get_node(self, instance, driver):
        node = driver._get_provider_instance(instance)
        if node and node.state == 0:
            return node
        raise Exception('Node not found or not running')

    def get_current_state(self, node, driver):
        nodes = driver.driver.list_nodes()
        node = next((x for x in nodes if x.name == node.name), node)
        return node.state
