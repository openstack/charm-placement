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
import json
import os
import subprocess

import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.host as host
import charms_openstack.adapters as os_adapters
import charms_openstack.charm
import charms_openstack.ip as os_ip

PLACEMENT_CONF = '/etc/placement/placement.conf'
PLACEMENT_WSGI_CONF = '/etc/apache2/sites-available/placement-api.conf'

PLACEMENT_PACKAGE = 'python3-placement'
PROBE_TIMEOUT = 30

# Runs under the system python3 (the charm venv cannot import
# oslo.config or placement); resolves to <charm>/files/ in the built charm.
PROBE_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, os.pardir,
    'files', 'placement_capability_probe.py')

# Used when the probe cannot report the choices of the strategy option.
DEFAULT_STRATEGY_CHOICES = ('depth-first', 'breadth-first')

_PROBE_FAILED = {
    'optimize_for_wide_provider_trees': False,
    'allocation_candidates_generation_strategy': False,
    'strategy_choices': None,
    'failed': True,
}


def probe_placement_package():
    """Detect which tuning options the installed python3-placement supports.

    :returns: dict with boolean keys ``optimize_for_wide_provider_trees`` and
        ``allocation_candidates_generation_strategy``, ``strategy_choices``
        (list or None) and optionally ``failed`` (True when the probe itself
        failed, as opposed to the package simply lacking the options).
    """
    try:
        if not os.path.isfile(PROBE_SCRIPT_PATH):
            raise RuntimeError('probe script not found at {}'.format(
                PROBE_SCRIPT_PATH))
        status = subprocess.check_output(
            ['dpkg-query', '-W', '-f=${Status}', PLACEMENT_PACKAGE],
            stderr=subprocess.DEVNULL, universal_newlines=True)
        if status.strip() != 'install ok installed':
            return {
                'optimize_for_wide_provider_trees': False,
                'allocation_candidates_generation_strategy': False,
                'strategy_choices': None,
            }
        proc = subprocess.run(
            ['/usr/bin/python3', '-I', PROBE_SCRIPT_PATH],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=PROBE_TIMEOUT)
        if proc.returncode != 0:
            raise RuntimeError('probe exited with {}: {}'.format(
                proc.returncode, proc.stderr))
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        data = json.loads(lines[-1])
        choices = data.get('strategy_choices')
        return {
            'optimize_for_wide_provider_trees': (
                data.get('optimize_for_wide_provider_trees') is True),
            'allocation_candidates_generation_strategy': (
                data.get('allocation_candidates_generation_strategy')
                is True),
            'strategy_choices': (
                [str(c) for c in choices]
                if isinstance(choices, list) else None),
        }
    except Exception as e:
        hookenv.log('{} capability probe failed: {}'.format(
            PLACEMENT_PACKAGE, e), level=hookenv.WARNING)
        return dict(_PROBE_FAILED)


class PlacementConfigurationAdapter(
        os_adapters.APIConfigurationAdapter):
    """Configuration adapter gating the placement tuning options.

    Exposes ``render_wide_provider_trees`` and ``render_generation_strategy``
    to templates. Values are non-empty only when the operator set the option
    and the installed python3-placement supports it. The package probe runs
    lazily (only when an option is set) and is cached on the instance.
    """

    def __init__(self, port_map=None, service_name=None,
                 charm_instance=None):
        super().__init__(port_map=port_map, service_name=service_name,
                         charm_instance=charm_instance)
        self._probe_result = None

    @property
    def probe_result(self):
        if self._probe_result is None:
            self._probe_result = probe_placement_package()
        return self._probe_result

    @property
    def wide_provider_trees_requested(self):
        return bool(getattr(self, 'optimize_for_wide_provider_trees', False))

    @property
    def requested_generation_strategy(self):
        """Normalized strategy requested by the operator ('' if unset)."""
        value = getattr(self, 'allocation_candidates_generation_strategy', '')
        if value is None:
            return ''
        return str(value).strip().lower()

    @property
    def probe_failed(self):
        return bool(self.probe_result.get('failed'))

    @property
    def valid_strategies(self):
        return tuple(self.probe_result.get('strategy_choices') or
                     DEFAULT_STRATEGY_CHOICES)

    @property
    def strategy_is_valid(self):
        return self.requested_generation_strategy in self.valid_strategies

    @property
    def render_wide_provider_trees(self):
        if not self.wide_provider_trees_requested:
            return False
        return self.probe_result['optimize_for_wide_provider_trees']

    @property
    def render_generation_strategy(self):
        strategy = self.requested_generation_strategy
        if not strategy:
            return ''
        if not self.probe_result['allocation_candidates_generation_strategy']:
            return ''
        return strategy if self.strategy_is_valid else ''


charms_openstack.charm.use_defaults('charm.default-select-release')


class PlacementCharm(charms_openstack.charm.HAOpenStackCharm):
    service_name = name = 'placement'

    configuration_class = PlacementConfigurationAdapter

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
    }

    ha_resources = ['vips', 'haproxy', 'dnsha']

    release_pkg = 'placement-common'

    package_codenames = {
        'placement-common': collections.OrderedDict([
            ('2', 'train'),
            ('3', 'ussuri'),
            ('4', 'victoria'),
            ('5', 'wallaby'),
        ]),
    }

    sync_cmd = ['placement-manage', 'db', 'sync']

    def get_database_setup(self):
        return [
            dict(database='placement',
                 username='placement',
                 prefix='placement'),
            dict(database='nova_api',
                 username='nova',
                 prefix='novaapi')]

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

    def render_with_interfaces(self, interfaces, configs=None):
        self.log_tuning_option_warnings()
        return super().render_with_interfaces(interfaces, configs)

    def log_tuning_option_warnings(self):
        """Log WARNINGs when a set tuning option will not be rendered."""
        opts = self.options
        wide = opts.wide_provider_trees_requested
        strategy = opts.requested_generation_strategy
        if not (wide or strategy):
            return

        def warn(msg):
            hookenv.log(msg, level=hookenv.WARNING)

        if opts.probe_failed:
            warn('Cannot render tuning options: {} probe failed'.format(
                PLACEMENT_PACKAGE))
            return
        probe = opts.probe_result
        if wide and not probe['optimize_for_wide_provider_trees']:
            warn('optimize-for-wide-provider-trees is not supported by the '
                 'installed {}; option not rendered'.format(
                     PLACEMENT_PACKAGE))
        if strategy:
            if not probe['allocation_candidates_generation_strategy']:
                warn('allocation-candidates-generation-strategy is not '
                     'supported by the installed {}; option not '
                     'rendered'.format(PLACEMENT_PACKAGE))
            elif not opts.strategy_is_valid:
                warn('Invalid allocation-candidates-generation-strategy '
                     '{!r}; valid values: {}; option not rendered'.format(
                         strategy, ', '.join(opts.valid_strategies)))
