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
Kozinaki cloud Nova compute driver

"""

import sys
import eventlet
import time
import pprint

from nova import conductor
from nova import db
from nova import exception
from nova import compute
from nova import block_device
from nova import context as ctxt2

from oslo.config import cfg

from nova.compute import flavors
from nova.compute import power_state
from nova.compute import task_states

from nova.objects import network as network_obj
from nova.objects import virtual_interface as vif_obj
from nova.objects import instance as instance_obj
from nova.objects import fixed_ip as fixed_ip_obj
from nova.objects import instance_info_cache as info_cache_obj

from nova.openstack.common import log as logging
from nova.openstack.common.gettextutils import _

from nova.virt import driver
from nova.virt import virtapi

from nova.network.manager import NetworkManager

from functools import wraps

from libcloud.compute.providers import get_driver
from libcloud.compute.base import NodeImage
from libcloud.compute.base import NodeState
from libcloud.compute.base import NodeAuthPassword
from libcloud.compute.types import Provider as provider_obj

from netaddr import IPAddress, IPNetwork

LOG = logging.getLogger(__name__)
_LOG = "\n\n### {} ###\n\n"

kozinaki_opts = [
    cfg.StrOpt('prefix',
               help='Provider instance name prefix')
    ]

CONF = cfg.CONF
CONF.register_opts(kozinaki_opts, 'kozinaki')
CONF.import_opt('my_ip', 'nova.netconf')

## Mapping of libcloud instance power states to the OpenStack power states
## Each libcloud driver has provider specific power states in NODE_STATE_MAP within each driver
## which map to generic libclou power states defined in libcloud.compute.types.NodeState
## OpenStack power states are defined in nova/compute/power_state.py STATE_MAP variable

provider_to_local_nodestates = {
                                    # libcloud             OpenStack
    0: power_state.RUNNING,         # 0: RUNNING       :  2: RUNNING: running
    1: power_state.NOSTATE,         # 1: REBOOTING     :  1: NOSTATE: pending
    2: power_state.SHUTDOWN,        # 2: TERMINATED    :  4: SHUTDOWN: shutdown
    3: power_state.NOSTATE,         # 3: PENDING       :  1: NOSTATE: pending
    4: power_state.NOSTATE,         # 4: UNKNOWN       :  1: NOSTATE: pending
    5: power_state.SHUTDOWN         # 5: SHUTDOWN      :  4: SHUTDOWN: shutdown
}

class KozinakiDriver(driver.ComputeDriver):

    ## TODO: What are these capabiities and how are they set?
    capabilities = {
        "has_imagecache": True,
        "supports_recreate": True,
        }

    def __init__(self, virtapi, read_only=False):

        super(KozinakiDriver, self).__init__(virtapi)

        self.instances = {}

        self._conn = None
        self._prefix = CONF.kozinaki.prefix
        self._providers = {}

        self._mounts = {}
        self._version = '0.1'
        self._interfaces = {}
        self.conductor_api = conductor.API()

    # TODO (rnl): figure out why there was a @property decorator
    def conn(self, provider_name, provider_region=None):
        """
        Establish connection to the cloud provider. Cloud provider
        data is kept in dict including user, key and connection handle.
        This approach enables having one nova-compute handle all kozinaki cloud
        connections.

        :return: connection object handle
        """

        conf_provider = "kozinaki_" + provider_name

        # TODO (rnl): add parameter checking

        if (provider_name == 'EC2' or provider_name == 'ELASTICHOSTS') and provider_region != None:
            provider_name = provider_name + "_" + provider_region

        if self._providers.get(provider_name) is None:

            provider_opts = [
                cfg.StrOpt('user',
                    help='Username to connect to the cloud provider '),
                cfg.StrOpt('key',
                    help='API key to work with the cloud provider',
                    secret=True),
                cfg.StrOpt('cloud_service_name',
                    help='Azure: cloud service name'),
                cfg.StrOpt('storage_service_name',
                    help='Azure: storage service name'),
                cfg.StrOpt('default_password',
                    help='Azure: default instance password'),
                cfg.StrOpt('admin_user_id',
                    help='Azure: default username'),
            ]

            CONF.register_opts(provider_opts, conf_provider)
            _driver = get_driver(getattr(provider_obj, provider_name))

            self._providers[provider_name] = {}

            if provider_name == 'AZURE':
                self._providers[provider_name]['cloud_service_name'] = CONF[conf_provider]['cloud_service_name']
                self._providers[provider_name]['storage_service_name'] = CONF[conf_provider]['storage_service_name']
                self._providers[provider_name]['default_password'] = CONF[conf_provider]['default_password']

            self._providers[provider_name]['driver'] = _driver(CONF[conf_provider]['user'], CONF[conf_provider]['key'])

        return self._providers[provider_name]['driver']

    def init_host(self, host):
        """Initialize anything that is necessary for the driver to function,
        including catching up with currently running VM's on the given host.
        """
        return

    def list_instances(self):
        """Return the names of all the instances known to the virtualization
        layer, as a list.
        """
        return self.instances.keys()

    def _prefix_instance_name(self, instance):
        """ Creates instance name with the prefix """
        return "%s-%s" % (self._prefix, instance['uuid'])

    def _validate_image(self, instance, image_meta):
        """ Check that the image used is of supported container type """

        ## TODO: configm that the image containes provider and region flags
        fmt = image_meta['container_format']

        if fmt != 'kozinaki':
            msg = _('Image container format not supported ({0})')
            raise exception.InstanceDeployFailure(msg.format(fmt),
                                                  instance_id=instance['name'])

    def _create_instance_name(self, uuid):
        """
        Instance length limitation in Azure is 15 chars

        :param uuid: local instance uuid
        :param instance_prefix: instance prefix configuration parameter
        :return: last chunk 12 chars of the local instance uuid
        """
        return self._prefix + "-" + uuid.split('-')[4]

    def _get_local_image_prop(self, metadata, key):

        """
        :param metadata: image metadata
        :param key: key to look up in the metadata dict
        :return: key value
        """

        properties = metadata.get('properties')

        if properties:
            if properties.get(key):
                return properties.get(key)
            else:
                return None
        return None

    def _get_local_instance_prop(self, instance, key):

        """
        :param metadata: local instance
        :param key: key to look up in the metadata dict
        :return: key value
        """

        metadata = instance.get('metadata')

        if metadata:
            if metadata.get(key):
                return metadata.get(key)
            else:
                return None
        else:
            return None

    def _update_local_instance_meta(self, context, local_instance, provider_name, provider_region, provider_instance_name):

        ## TODO: move metadata update to a separate function place
        ## TODO: this will be needed as a function to set prices into glance images
        ## separate library to work with local and remote instances outside the driver is needed
        ## TODO: add image_meta to the instance describing the OS

        metadata = {}
        metadata['provider_name'] = provider_name

        if (provider_region):
            metadata['provider_region'] = provider_region
        metadata['provider_instance_name'] = provider_instance_name

        if provider_name == 'AZURE':
            metadata['cloud_service_name'] = self._providers['AZURE']['cloud_service_name']
            metadata['storage_service_name'] = self._providers['AZURE']['cloud_service_name']

        compute_api = compute.API()
        compute_api.update_instance_metadata(context, local_instance, metadata)

    def _get_local_instance_conn(self, instance):
        """

        :param instance: local instance
        :return: libcloud provider driver corresponding to the local instance'
        """

        provider_name = self._get_local_instance_prop(instance, 'provider_name')
        provider_region = self._get_local_instance_prop(instance, 'provider_region')

        return self.conn(provider_name, provider_region)

    def _get_provider_instance(self, instance):
        """
        :param instance: local instance
        :return: provider instance that corresponds to the local instance
        """

        provider_instance_name = self._get_local_instance_prop(instance, 'provider_instance_name')
        provider_name = self._get_local_instance_prop(instance, 'provider_name')
        provider_region = self._get_local_instance_prop(instance, 'provider_region')

        try:
            for provider_instance_list_item in self._list_provider_instances(provider_name, provider_region):
                if provider_instance_list_item.state != NodeState.TERMINATED and provider_instance_list_item.name == provider_instance_name:
                    return provider_instance_list_item
                ## TODO: raise no instance error
            return None
        except:
            return None

    def _list_provider_instances(self, provider_name, provider_region):

        if provider_name == 'AZURE':
            return self.conn(provider_name, provider_region).list_nodes(ex_cloud_service_name = self._providers['AZURE']['cloud_service_name'])
        else:
            return self.conn(provider_name, provider_region).list_nodes()

    @classmethod
    def _timeout_call(wait_period, timeout):
        """
        This decorator calls given method repeatedly
        until it throws exception. Loop ends when method
        returns.
        """
        def _inner(f):
            @wraps(f)
            def _wrapped(*args, **kwargs):
                start = time.time()
                end = start + timeout
                exc = None
                while(time.time() < end):
                    try:
                        return f(*args, **kwargs)
                    except Exception as exc:
                        time.sleep(wait_period)
                raise exc
            return _wrapped
        return _inner

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info=None, block_device_info=None):

        """Create a new instance/VM/domain on the virtualization platform.

        Once this successfully completes, the instance should be
        running (power_state.RUNNING).

        If this fails, any partial instance should be completely
        cleaned up, and the virtualization platform should be in the state
        that it was before this call began.

        :param context: security context
        :param instance: nova.objects.instance.Instance
                         This function should use the data there to guide
                         the creation of the new instance.
        :param image_meta: image object returned by nova.image.glance that
                           defines the image from which to boot this instance
        :param injected_files: User files to inject into instance.
        :param admin_password: Administrator password to set in instance.
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param block_device_info: Information about block devices to be
                                  attached to the instance.
        """

        """ Extractin provider info from meta """
        provider_name = self._get_local_image_prop(image_meta, 'provider_name')
        provider_region = self._get_local_image_prop(image_meta, 'provider_region')
        provider_image = self._get_local_image_prop(image_meta, 'provider_image')

        name = self._create_instance_name(instance['uuid'])

        flavor = flavors.extract_flavor(instance)

        # TODO: move to separate function _get_provider_size_from_flavor
        sizes = self.conn(provider_name, provider_region).list_sizes()
        size = [s for s in sizes if s.id == flavor['name']][0]

        provider_image = NodeImage(id=provider_image, name=None, driver=self.conn(provider_name, provider_region))

        try:
            if provider_name == 'AZURE':
                # TODO: add handling of ex_admin_user_id
                provider_instance = self.conn(provider_name, provider_region).create_node(name=name, image=provider_image, size=size,
                                                                                          auth=NodeAuthPassword(self._providers[provider_name]['default_password']),
                                                                                          ex_cloud_service_name=self._providers[provider_name]['cloud_service_name'],
                                                                                          ex_storage_service_name=self._providers[provider_name]['storage_service_name'])
            else:
                if instance.get('key_data'):
                    provider_instance = self.conn(provider_name, provider_region).create_node(name=name, image=provider_image, size=size, ex_keyname=instance.get('key_data'))
                else:
                    provider_instance = self.conn(provider_name, provider_region).create_node(name=name, image=provider_image, size=size)
        except:
            ## TODO: get rid of the debug prints
            print sys.exc_info()

            raise exception.InstanceDeployFailure(
                _('Cannot create new instance'),
                instance_id = instance['name'])
        else:
            eventlet.spawn(self._setup_local_instance, context, instance, provider_instance, provider_name, provider_region)

    def _setup_local_instance(self, context, local_instance, create_node_provider_instance, provider_name, provider_region):
        """
        Setup local instance with IP address and instance's properties in metadata, such as provider_name, provider_region,
        provider_instance_name
        """

        provider_instance_ip = self._get_provider_instance_ip(context, local_instance, create_node_provider_instance, provider_name, provider_region)
        self._bind_ip_to_instance(context, local_instance, provider_instance_ip)
        self._update_local_instance_meta(context, local_instance, provider_name, provider_region, create_node_provider_instance.name)

    def _get_provider_instance_ip(self, context, local_instance, create_node_provider_instance, provider_name, provider_region):
        """
        Spawning a provider instance is different than spawning a local one.
        IP addresses are assigned to the instances by the providers, and we
        need to bind the provider IP to the new instance.

        Function scans the list of the instances in provider and matches the
        name to the UUID of the local instance
        """

        """ provider_instance_* refers to the instance created within cloud provider """
        list_item_provider_instance_ip = None

        while not list_item_provider_instance_ip:

            for list_item_provider_instance in self._list_provider_instances(provider_name, provider_region):
                if list_item_provider_instance.name == create_node_provider_instance.name:
                    if list_item_provider_instance.public_ips:
                        list_item_provider_instance_ip = list_item_provider_instance.public_ips[0]
                        break
            if list_item_provider_instance_ip:
                return list_item_provider_instance_ip
                break
        return

    def _bind_ip_to_instance(self, context, local_instance, provider_instance_ip):
        """
        Binds provider instance IP address to the local instance

        :param context:
        :param local_instance:
        :param provider_instance_ip:
        :return:
        """

        admin_context = ctxt2.get_admin_context()
        network_manager = NetworkManager()

        """ This loop checks whether the nova network exists for the IP address that we received to be bound to the local instance
            If network doesn't exist, it is created with /24 mask and named 'test'.
            All networks had to be named the same due to their display in Horizon.
            displayed as multiple networks, this has to do with multi-AZ setup and network-to-host association
        """

        for net in network_obj.NetworkList.get_all(admin_context):
            if IPAddress(provider_instance_ip) in net._cidr:
                break
        else:
            a = provider_instance_ip.split('.')
            cidr = '.'.join(a[:3])+".0/24"
            network_manager.create_networks(admin_context, "test", cidr=cidr, bridge_interface="eth0", bridge="br100")

        ## TODO: Figure out how --nic option enables to bind only one network to th local instance
        ## TODO: FixedIpAlreadyInUse_Remote: Fixed IP address 137.116.234.178 is already in use on instance 934798a3-bde0-42e3-9843-40f3539a6acd.

        for net in network_obj.NetworkList.get_all(admin_context):
            if IPAddress(provider_instance_ip) in net._cidr:
                """ fip (fixed IP) and we create this object """
                fip = fixed_ip_obj.FixedIP.associate(admin_context, IPAddress(provider_instance_ip), local_instance['uuid'], network_id=net.id, reserved=False)
                fip.allocated = True
                """ vif (virtual interface) that we create based on the network that either existed or the one that we created """
                vif = vif_obj.VirtualInterface.get_by_instance_and_network(admin_context, local_instance['uuid'], net.id)
                """ we set the vif of the fip """
                if vif:
                    fip.virtual_interface_id = vif.id
                """ saving it writes it into the table """
                fip.save()

                """ After that we extract the network information from the network-related tables """
                nw_info = network_manager.get_instance_nw_info(admin_context, local_instance['uuid'], None, None)
                """ Create a cache object """
                ic = info_cache_obj.InstanceInfoCache.new(admin_context, local_instance['uuid'])
                """ we now update and save the cache object with the network information """
                ic.network_info = nw_info
                ic.save(update_cells=False)
                break

    def live_snapshot(self, context, instance, name, update_task_state):
        """Snapshot an instance without downtime."""
        pass

    def snapshot(self, context, instance, name, update_task_state):
        """Snapshots the specified instance.

        :param context: security context
        :param instance: nova.objects.instance.Instance
        :param image_id: Reference to a pre-created image that will
                         hold the snapshot.
        """
        pass

    def get_host_ip_addr(self):
        """Retrieves the IP address of this local nova compute instance
        """
        return CONF.my_ip

    def set_admin_password(self, instance, new_pass):
        """Set the root password on the specified instance.

        :param instance: nova.objects.instance.Instance
        :param new_password: the new password
        """
        pass

    def inject_file(self, instance, b64_path, b64_contents):
        """Writes a file on the specified instance.

        The first parameter is an instance of nova.compute.service.Instance,
        and so the instance is being specified as instance.name. The second
        parameter is the base64-encoded path to which the file is to be
        written on the instance; the third is the contents of the file, also
        base64-encoded.

        NOTE(russellb) This method is deprecated and will be removed once it
        can be removed from nova.compute.manager.
        """
        pass

    def resume_state_on_host_boot(self, context, instance, network_info,
                                  block_device_info=None):
        """resume guest state when a host is booted.

        :param instance: nova.objects.instance.Instance
        """
        pass

    def rescue(self, context, instance, network_info, image_meta,
               rescue_password):
        """Rescue the specified instance.

        :param instance: nova.objects.instance.Instance
        """
        pass

    def unrescue(self, instance, network_info):
        """Unrescue the specified instance.

        :param instance: nova.objects.instance.Instance
        """
        pass

    def poll_rebooting_instances(self, timeout, instances):
        pass

    def migrate_disk_and_power_off(self, context, instance, dest,
                                   instance_type, network_info,
                                   block_device_info=None):
        pass

    def post_live_migration_at_destination(self, context, instance,
                                           network_info,
                                           block_migration=False,
                                           block_device_info=None):
        pass

    def _do_provider_node(self, action, instance, new_size=None):
        """
        Perform different actions with provider specific parameters where required

        :param instance:
        :return:
        """

        provider_instance = self._get_provider_instance(instance)

        ## TODO: replace with try/catch block inside the get function, False=True
        if provider_instance is None:
            return

        provider_name = self._get_local_instance_prop(instance, 'provider_name')

        if action == 'start':
            ## TODO: address the case that after StoppedUnallocated instance stops it doesn't have an IP address so after start
            ## TODO: need to add the address to the instance
            if provider_name == 'AZURE':
                provider_cloud_service_name = self._get_local_instance_prop(instance, 'cloud_service_name')
                self._get_local_instance_conn(instance).ex_start_node(provider_instance, ex_cloud_service_name=provider_cloud_service_name)
            else:
                self._get_local_instance_conn(instance).ex_start_node(provider_instance)

        elif action == 'stop':
            ## TODO: after the instance is stopped the IP address needs to be deallocated from the local instance
            ## TODO: also the network needs be deleted
            if provider_name == 'AZURE':
                provider_cloud_service_name = self._get_local_instance_prop(instance, 'cloud_service_name')
                self._get_local_instance_conn(instance).ex_stop_node(provider_instance, ex_cloud_service_name=provider_cloud_service_name)
            else:
                self._get_local_instance_conn(instance).ex_stop_node(provider_instance)

        elif action == 'reboot':
            if provider_name == 'AZURE':
                provider_cloud_service_name = self._get_local_instance_prop(instance, 'cloud_service_name')
                self._get_local_instance_conn(instance).reboot_node(provider_instance, ex_cloud_service_name=provider_cloud_service_name)
            else:
                self._get_local_instance_conn(instance).reboot_node(provider_instance)

        elif action == 'resize':
            if not new_size:
                return

            conn = self._get_local_instance_conn(instance)
            if provider_name == 'AZURE':
                provider_cloud_service_name = self._get_local_instance_prop(instance, 'cloud_service_name')
                self._resize_provider_instance(conn, provider_instance, new_size, ex_cloud_service_name=provider_cloud_service_name)
            else:
                self._resize_provider_instance(conn, provider_instance, new_size)

    @_timeout_call(wait_period=3, timeout=600)
    def _resize_provider_instance(self, local_instance_conn, provider_instance, new_size, **kwargs):
        """
        Performs ex_change_node_size on provider_instance handling
        any exceptions and repeating call until timeout expires.
        This prevents from calling resize on still running instances.
        """
        return local_instance_conn.ex_change_node_size(provider_instance, new_size, **kwargs)

    ## TODO: after stop, powerstate is NOSTATE, need to address that
    def power_off(self, instance):
        """
        Looks up provider instance corresponding to the local instance,
        looks up the provider driver corresponding to the local instance,
        issues a provider specific commend to stop the provider instance

        :param instance: Local instance
        """

        ##TODO: check if node already stopped and do not do anything with it, just change the power_state
        self._do_provider_node('stop', instance)

    def power_on(self, context, instance, network_info, block_device_info):
        """
        Looks up provider instance corresponding to the local instance,
        looks up the provider driver corresponding to the local instance,
        issues a provider specific commend to start provider instance

        :param instance: Local instance
        """

        self._do_provider_node('start', instance)

    def reboot(self, context, instance, network_info, reboot_type,
               block_device_info=None, bad_volumes_callback=None):
        """Reboot a virtual machine, given an instance reference."""

        self._do_provider_node('reboot', instance)

    def soft_delete(self, instance):
        pass

    def restore(self, instance):
        pass

    def pause(self, instance):
        pass

    def unpause(self, instance):
        pass

    def suspend(self, instance):
        pass

    def resume(self, context, instance, network_info, block_device_info=None):
        pass

    def destroy(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True):
        """
        Looks up provider instance corresponding to the local instance,
        looks up the provider driver corresponding to the local instance,
        issues a provider specific commend to stop the provider instance

        :param instance: Local instance
        """

        provider_instance = self._get_provider_instance(instance)
        if not provider_instance:
            return
        self._get_local_instance_conn(instance).destroy_node(provider_instance)

    def attach_volume(self, context, connection_info, instance, mountpoint,
                      encryption=None):
        """Attach the disk to the instance at mountpoint using info."""
        instance_name = instance['name']
        if instance_name not in self._mounts:
            self._mounts[instance_name] = {}
        self._mounts[instance_name][mountpoint] = connection_info
        return True

    def detach_volume(self, connection_info, instance, mountpoint,
                      encryption=None):
        """Detach the disk attached to the instance."""
        try:
            del self._mounts[instance['name']][mountpoint]
        except KeyError:
            pass
        return True

    def swap_volume(self, old_connection_info, new_connection_info,
                    instance, mountpoint):
        """Replace the disk attached to the instance."""
        instance_name = instance['name']
        if instance_name not in self._mounts:
            self._mounts[instance_name] = {}
        self._mounts[instance_name][mountpoint] = new_connection_info
        return True

    def attach_interface(self, instance, image_meta, vif):
        if vif['id'] in self._interfaces:
            raise exception.InterfaceAttachFailed('duplicate')
        self._interfaces[vif['id']] = vif

    def detach_interface(self, instance, vif):
        try:
            del self._interfaces[vif['id']]
        except KeyError:
            raise exception.InterfaceDetachFailed('not attached')

    def get_info(self, instance):
        """Get the current status of an instance

        :param instance: local instance nova.objects.instance.Instance object

        Returns a dict containing:

        :state:           the running state, one of the power_state codes
        :max_mem:         (int) the maximum memory in KBytes allowed
        :mem:             (int) the memory in KBytes used by the domain
        :num_cpu:         (int) the number of virtual CPUs for the domain
        :cpu_time:        (int) the CPU time used in nanoseconds
        """

        provider_instance = self._get_provider_instance(instance)
        if not provider_instance:
            raise exception.InstanceNotFound(instance_id=instance['name'])

        return {'state': provider_to_local_nodestates[provider_instance.state],
                'max_mem': 0,
                'mem': 0,
                'num_cpu': 2,
                'cpu_time': 0}

    def get_diagnostics(self, instance_name):
        return {'cpu0_time': 17300000000,
                'memory': 524288,
                'vda_errors': -1,
                'vda_read': 262144,
                'vda_read_req': 112,
                'vda_write': 5778432,
                'vda_write_req': 488,
                'vnet1_rx': 2070139,
                'vnet1_rx_drop': 0,
                'vnet1_rx_errors': 0,
                'vnet1_rx_packets': 26701,
                'vnet1_tx': 140208,
                'vnet1_tx_drop': 0,
                'vnet1_tx_errors': 0,
                'vnet1_tx_packets': 662,
        }

    def get_all_bw_counters(self, instances):
        """Return bandwidth usage counters for each interface on each
           running VM.
        """
        bw = []
        return bw

    def get_all_volume_usage(self, context, compute_host_bdms):
        """Return usage info for volumes attached to vms on
           a given host.
        """
        volusage = []
        return volusage

    def block_stats(self, instance_name, disk_id):
        return [0L, 0L, 0L, 0L, None]

    def interface_stats(self, instance_name, iface_id):
        return [0L, 0L, 0L, 0L, 0L, 0L, 0L, 0L]

    ## Console operation functions
    def get_console_output(self, context, instance):
        pass

    def get_vnc_console(self, context, instance):
        pass

    def get_spice_console(self, context, instance):
        pass

    def get_console_pool_info(self, console_type):
        pass

    def refresh_security_group_rules(self, security_group_id):
        return True

    def refresh_security_group_members(self, security_group_id):
        return True

    def refresh_instance_security_rules(self, instance):
        return True

    def refresh_provider_fw_rules(self):
        pass

    ## TODO: since we have infinite resources we need to set them as either maximum available by data type or figure out what infinity means for them
    def get_available_resource(self, nodename):
        """Retrieve resource information.

        This method is called when nova-compute launches, and
        as part of a periodic task that records the results in the DB.

        :param nodename:
            node which the caller want to get resources from
            a driver that manages only one node can safely ignore this
        :returns: Dictionary describing resources
        """

        dic = {'vcpus': 999999,
               'memory_mb': 999999,
               'local_gb': 999999,
               'vcpus_used': 0,
               'memory_mb_used': 0,
               'local_gb_used': 0,
               'hypervisor_type': 'kozinaki',
               'hypervisor_version': '1.0',
               'hypervisor_hostname': nodename,
               'cpu_info': '?',                     ## TODO: see vmwareapi/host.py:HostState.update_status() and for the next one too

               ## TODO: figure out what the supported_instances should be
               # 'supported_instances': [('i686',   'kozinaki', 'hvm'),
               #                        ('x86_64', 'kozinaki', 'hvm')]

               # Hyper-V
               # data["supported_instances"] = [('i686', 'hyperv', 'hvm'),
               #                                ('x86_64', 'hyperv', 'hvm')]
        }
        return dic

    ## TODO: use hostname instead of IP address
    def get_host_stats(self, refresh=False):
        """Return currently known host stats."""
        return self.get_available_resource(CONF.my_ip)

    def ensure_filtering_rules_for_instance(self, instance_ref, network_info):
        return

    def get_instance_disk_info(self, instance_name):
        return

    def live_migration(self, context, instance_ref, dest,
                       post_method, recover_method, block_migration=False,
                       migrate_data=None):
        post_method(context, instance_ref, dest, block_migration,
                            migrate_data)
        return

    def check_can_live_migrate_destination_cleanup(self, ctxt,
                                                   dest_check_data):
        return

    def check_can_live_migrate_destination(self, ctxt, instance_ref,
                                           src_compute_info, dst_compute_info,
                                           block_migration=False,
                                           disk_over_commit=False):
        return {}

    def check_can_live_migrate_source(self, ctxt, instance_ref,
                                      dest_check_data):
        return

    def pre_live_migration(self, context, instance_ref, block_device_info,
                           network_info, disk, migrate_data=None):
        return

    def finish_migration(self, context, migration, instance, disk_info,
                         network_info, image_meta, resize_instance,
                         block_device_info=None, power_on=True):
        """Completes a resize.

        :param context: the context for the migration/resize
        :param migration: the migrate/resize information
        :param instance: nova.objects.instance.Instance being migrated/resized
        :param disk_info: the newly transferred disk information
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param image_meta: image object returned by nova.image.glance that
                           defines the image from which this instance
                           was created
        :param resize_instance: True if the instance is being resized,
                                False otherwise
        :param block_device_info: instance volume block device info
        :param power_on: True if the instance should be powered on, False
                         otherwise
        """

        if resize_instance:
            flavor = flavors.extract_flavor(instance)

            provider_name = self._get_local_instance_prop(image_meta, 'provider_name')
            provider_region = self._get_local_instance_prop(image_meta, 'provider_region')

            sizes = self.conn(provider_name, provider_region).list_sizes()
            new_provider_size = [s for s in sizes if s.id == flavor['name']][0]

            provider_instance = self._get_provider_instance(instance)
            if not provider_instance:
                return

            self._do_provider_node('stop', instance)

            self._do_provider_node('resize', provider_instance,
                                   new_size=new_provider_size)

        if power_on:
            self.power_on(context, instance, network_info, block_device_info)

        return

    def confirm_migration(self, migration, instance, network_info):
        """Confirms a resize, destroying the source VM.

        :param instance: nova.objects.instance.Instance
        """
        return

    def finish_revert_migration(self, instance, network_info,
                                block_device_info=None, power_on=True):
        """Finish reverting a resize.

        :param context: the context for the finish_revert_migration
        :param instance: nova.objects.instance.Instance being migrated/resized
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param block_device_info: instance volume block device info
        :param power_on: True if the instance should be powered on, False
                         otherwise
        """

        pass

    def unfilter_instance(self, instance_ref, network_info):
        return

    def test_remove_vm(self, instance_name):
        """Removes the named VM, as if it crashed. For testing."""
        self.instances.pop(instance_name)

    def host_power_action(self, host, action):
        """Reboots, shuts down or powers up the host."""
        return action

    def host_maintenance_mode(self, host, mode):
        """Start/Stop host maintenance window. On start, it triggers
        guest VMs evacuation.
        """
        if not mode:
            return 'off_maintenance'
        return 'on_maintenance'

    def set_host_enabled(self, host, enabled):
        """Sets the specified host's ability to accept new instances."""
        if enabled:
            return 'enabled'
        return 'disabled'

    def get_disk_available_least(self):
        pass

    def add_to_aggregate(self, context, aggregate, host, **kwargs):
        pass

    def remove_from_aggregate(self, context, aggregate, host, **kwargs):
        pass

    def get_volume_connector(self, instance):
        return {'ip': '127.0.0.1', 'initiator': 'fake', 'host': 'fakehost'}

    def instance_on_disk(self, instance):
        return False

    def list_instance_uuids(self):
        return []

    def plug_vifs(self, instance, network_info):
        """Plug VIFs into networks."""
        pass

    def unplug_vifs(self, instance, network_info):
        """Unplug VIFs from networks."""
        pass
