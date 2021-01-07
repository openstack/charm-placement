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

import collections
import subprocess

import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.host as host
import charms_openstack.charm
import charms_openstack.ip as os_ip

PLACEMENT_CONF = '/etc/placement/placement.conf'
PLACEMENT_WSGI_CONF = '/etc/apache2/sites-available/placement-api.conf'
PLACEMENT_MIGRATE_DB_CONF = '/etc/placement/migrate-db.rc'

charms_openstack.charm.use_defaults('charm.default-select-release')


class PlacementCharm(charms_openstack.charm.HAOpenStackCharm):
    service_name = name = 'placement'

    release = 'train'

    packages = ['placement-api', 'python3-pymysql', 'mysql-client']

    # Python version used to execute installed workload
    python_version = 3

    api_ports = {
        'placement-api': {
            os_ip.PUBLIC: 8778,
            os_ip.ADMIN: 8778,
            os_ip.INTERNAL: 8778,
        }
    }

    group = 'placement'
    service_type = 'placement'
    default_service = 'placement-api'
    services = ['apache2', 'haproxy']

    required_relations = ['shared-db', 'identity-service', 'placement']

    restart_map = {
        PLACEMENT_CONF: services,
        PLACEMENT_WSGI_CONF: services,
        PLACEMENT_MIGRATE_DB_CONF: services,
    }

    ha_resources = ['vips', 'haproxy', 'dnsha']

    release_pkg = 'placement-common'

    package_codenames = {
        'placement-common': collections.OrderedDict([
            ('2', 'train'),
            ('3', 'ussuri'),
            ('4', 'victoria'),
        ]),
    }

    mysql_migrate_db = '/usr/share/placement/mysql-migrate-db.sh'

    migrate_cmd = [mysql_migrate_db, '--migrate', '--skip-locks',
                   PLACEMENT_MIGRATE_DB_CONF]

    sync_cmd = ['placement-manage', 'db', 'sync']

    def get_database_setup(self):
        return [
            dict(database='placement',
                 username='placement',
                 prefix='placement'),
            dict(database='nova_api',
                 username='nova',
                 prefix='novaapi')]

    def db_migrate(self):
        if not self.db_sync_done() and hookenv.is_leader():
            try:
                subprocess.check_call(self.migrate_cmd)
            except subprocess.CalledProcessError as error:
                hookenv.log('{} returncode={} output={}'.format(
                    self.migrate_cmd, error.returncode, error.output),
                    level=hookenv.DEBUG)
                if error.returncode == 4 or error.returncode == 3:
                    # 4: No data present in nova database (nothing to migrate)
                    # 3: Migration has already completed
                    return False
                raise
        return True

    def db_sync(self):
        if not self.db_sync_done() and hookenv.is_leader():
            subprocess.check_call(self.sync_cmd)
            hookenv.leader_set({'db-sync-done': True})
            self.restart_all()

    def disable_services(self):
        for svc in self.services:
            host.service_pause(svc)

    def enable_services(self):
        for svc in self.services:
            host.service_resume(svc)
