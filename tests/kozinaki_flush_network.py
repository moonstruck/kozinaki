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
Manual test for network management
"""

import unittest
from libcloud.compute.types import NodeState
from base import KozinakiTestBase
from nova.db.sqlalchemy import api
from nova.db.sqlalchemy.models import FixedIp
from nova.openstack.common.timeutils import utcnow
import nova.context


class KozinakiNetworkTestCase(KozinakiTestBase):

    def test_list_ok(self):
        admin_context = nova.context.get_admin_context()
#         self.log.info('List all networks cidr')
#         self.driver._get_local_network(admin_context, ' 54.176.240.0')

#         delete all vifs
        for vif in api.virtual_interface_get_all(admin_context):
            api.virtual_interface_delete_by_instance(admin_context, vif.instance_uuid)

        # delete all fips from networks
#         for fixed_ip in api.fixed_ip_get_all(admin_context):
#             self.log.info("Disassociating FixedIP with address: %s instance_uuid: %s" % (fixed_ip['address'], fixed_ip['instance_uuid']))
#             fixed_ip['instance_uuid'] = None
#             fixed_ip['network_id' ] = None
#             fixed_ip['allocated' ] = False
#             fixed_ip['leased'] = False
#             fixed_ip['reserved'] = False
#             fixed_ip['host'] = None
#             fixed_ip['updated_at'] = utcnow()
#             fixed_ip.save()
 
        # delete all networks
        for net in api.network_get_all(admin_context, project_only='allow_none'):
            api.network_delete_safe(admin_context, net.id)

        # check it
#         print api.fixed_ip_get_all(admin_context)
#         print api.network_get_all(admin_context, 'allow_none')
        vifs = api.virtual_interface_get_all(admin_context)
        for vif in vifs:
            print "Vif: instance_uuid: %s network_id: %s" % (vif['instance_uuid'], vif['network_id'])



if __name__ == '__main__':
    unittest.main()
