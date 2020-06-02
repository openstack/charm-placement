# Copyright 2019 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import patch, call

import charms_openstack.test_utils as test_utils

import charm.openstack.placement as placement


class Helper(test_utils.PatchHelper):

    def setUp(self):
        super().setUp()
        self.patch_release(placement.PlacementCharm.release)


class TestPlacementCharm(Helper):

    def test_get_database_setup(self):
        c = placement.PlacementCharm()
        result = c.get_database_setup()
        self.assertEqual(result, [{'database': 'placement',
                                   'username': 'placement',
                                   'prefix': 'placement'},
                                  {'database': 'nova_api',
                                   'username': 'nova',
                                   'prefix': 'novaapi'}])

    @patch.object(placement.PlacementCharm, 'db_sync_done')
    @patch.object(placement.subprocess, 'check_call')
    @patch.object(placement.hookenv, 'is_leader')
    def test_db_migrate(self, is_leader, check_call, db_sync_done):
        c = placement.PlacementCharm()
        is_leader.return_value = True
        db_sync_done.return_value = False
        c.db_migrate()
        check_call.assert_called_with(
            ['/usr/share/placement/mysql-migrate-db.sh',
             '--migrate',
             '--skip-locks',
             '/etc/placement/migrate-db.rc'])

    @patch.object(placement.PlacementCharm, 'db_sync_done')
    @patch.object(placement.subprocess, 'check_call')
    @patch.object(placement.hookenv, 'is_leader')
    @patch.object(placement.hookenv, 'leader_set')
    def test_db_sync(self, leader_set, is_leader, check_call, db_sync_done):
        c = placement.PlacementCharm()
        is_leader.return_value = True
        db_sync_done.return_value = False
        c.db_sync()
        check_call.assert_called_with(['placement-manage', 'db', 'sync'])

    @patch.object(placement.host, 'service_pause')
    def test_disable_services(self, service_pause):
        c = placement.PlacementCharm()
        c.disable_services()
        service_pause.assert_has_calls([call('apache2'), call('haproxy')])

    @patch.object(placement.host, 'service_resume')
    def test_enable_services(self, service_resume):
        c = placement.PlacementCharm()
        c.enable_services()
        service_resume.assert_has_calls([call('apache2'), call('haproxy')])
