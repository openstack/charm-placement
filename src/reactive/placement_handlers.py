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

import charms.reactive as reactive

import charms_openstack.bus
import charms_openstack.charm
import charmhelpers.core as ch_core

charms_openstack.bus.discover()


charms_openstack.charm.use_defaults(
    'charm.installed',
    'shared-db.connected',
    'identity-service.connected',
    'identity-service.available',
    'config.changed',
    'update-status',
    'upgrade-charm',
    'certificates.available',
    'cluster.available',
)


@reactive.when('shared-db.available')
@reactive.when('identity-service.available')
def render_config(*args):
    with charms_openstack.charm.provide_charm_instance() as placement_charm:
        pre_ssl_enabled = placement_charm.get_state('ssl.enabled')
        placement_charm.configure_tls(
            certificates_interface=reactive.endpoint_from_flag(
                'certificates.available'))
        ssl_enabled = placement_charm.get_state('ssl.enabled')
        if ssl_enabled != pre_ssl_enabled:
            ch_core.hookenv.log((
                "Detected switch to ssl.enabled: {}. "
                "Informing keystone.").format(ssl_enabled))
            keystone = reactive.endpoint_from_flag(
                'identity-service.available')
            keystone.register_endpoints(placement_charm.service_type,
                                        placement_charm.region,
                                        placement_charm.public_url,
                                        placement_charm.internal_url,
                                        placement_charm.admin_url)
        placement_charm.upgrade_if_available(args)
        placement_charm.render_with_interfaces(args)
        placement_charm.assess_status()
    reactive.set_state('config.rendered')


@reactive.when('config.rendered')
@reactive.when('placement.available')
@reactive.when_not('db.synced')
def init_db():
    with charms_openstack.charm.provide_charm_instance() as placement_charm:
        placement = reactive.endpoint_from_flag('placement.available')
        disabled = placement.get_nova_placement_disabled()
        if disabled:
            placement_charm.disable_services()
            placement_charm.db_migrate()
            placement_charm.db_sync()
            placement_charm.enable_services()
            placement_charm.assess_status()
            placement.set_placement_enabled()
            reactive.set_state('db.synced')


@reactive.when('ha.connected')
def cluster_connected(hacluster):
    """Configure HA resources in corosync"""
    with charms_openstack.charm.provide_charm_instance() as placement_charm:
        placement_charm.configure_ha_resources(hacluster)
        placement_charm.assess_status()
