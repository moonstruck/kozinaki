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
Boot test for Kozinaki Network management
"""

import unittest
from libcloud.compute.types import NodeState
from base import KozinakiTestBase
from nova.db.sqlalchemy import api
from nova.openstack.common.timeutils import utcnow
import nova.context
import datetime


class KozinakiNetworkTestCase(KozinakiTestBase):

    def test_list_ok(self):
        admin_context = nova.context.get_admin_context()
#         self.log.info('List all networks cidr')
#         self.driver._get_local_network(admin_context, ' 54.176.240.0')
        for fixed_ip in api.fixed_ip_get_all(admin_context):
            fixed_ip.network_id = 0
            fixed_ip.allocated = False
#             print fixed_ip.network_id
            fixed_ip.save()
        api.fixed_ip_disassociate_all_by_timeout(admin_context, 'node-8', datetime.datetime(2014, 10, 1))
        for vif in api.virtual_interface_get_all(admin_context):
            api.virtual_interface_delete_by_instance(admin_context, vif.instance_uuid)

#         print api.fixed_ip_get_all(admin_context)
#         print api.virtual_interface_get_all(admin_context)
#         print api.network_get_all(admin_context, 'allow_none')
#         net = api.network_get_all(admin_context, 'allow_none')[0]
#         print api.network_get_associated_fixed_ips(admin_context, net.id)


if __name__ == '__main__':
    unittest.main()
