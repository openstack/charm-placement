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

import configparser
import json
import os
import subprocess
from unittest.mock import patch, call, MagicMock

import jinja2
import yaml

import charms_openstack.adapters as os_adapters
import charms_openstack.charm
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


SUPPORTED = {
    'optimize_for_wide_provider_trees': True,
    'allocation_candidates_generation_strategy': True,
    'strategy_choices': ['depth-first', 'breadth-first'],
}


def _dpkg(status='install ok installed'):
    return status


def _proc(payload, returncode=0, stderr=''):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = payload if isinstance(payload, str) else json.dumps(payload)
    proc.stderr = stderr
    return proc


class AdapterHelper(Helper):

    def make_adapter(self, wide=False, strategy=''):
        cfg = {
            'optimize-for-wide-provider-trees': wide,
            'allocation-candidates-generation-strategy': strategy,
        }
        with patch.object(os_adapters.hookenv, 'config', return_value=cfg):
            return placement.PlacementConfigurationAdapter()

    def make_charm(self, release, wide=False, strategy=''):
        cfg = {
            'optimize-for-wide-provider-trees': wide,
            'allocation-candidates-generation-strategy': strategy,
        }
        charm = placement.PlacementCharm(release=release)
        with patch.object(os_adapters.hookenv, 'config', return_value=cfg):
            charm.options  # force lazy construction while config patched
        return charm

    def start_log_patch(self):
        patcher = patch.object(placement.hookenv, 'log')
        self.addCleanup(patcher.stop)
        return patcher.start()

    def warnings(self, log):
        return [c.args[0] for c in log.call_args_list
                if c.kwargs.get('level') == placement.hookenv.WARNING]


class TestTuningAdapter(AdapterHelper):

    def setUp(self):
        super().setUp()
        self.log = self.start_log_patch()

    @patch.object(placement.subprocess, 'run')
    @patch.object(placement.subprocess, 'check_output')
    def test_supported_options_render(self, check_output, run):
        check_output.return_value = _dpkg()
        run.return_value = _proc(SUPPORTED)
        a = self.make_adapter(wide=True, strategy='breadth-first')
        self.assertTrue(a.render_wide_provider_trees)
        self.assertEqual(a.render_generation_strategy, 'breadth-first')
        self.assertEqual(run.call_count, 1)
        args, kwargs = run.call_args
        self.assertEqual(
            args[0], ['/usr/bin/python3', '-I',
                      placement.PROBE_SCRIPT_PATH])
        self.assertTrue(os.path.isfile(placement.PROBE_SCRIPT_PATH))
        self.assertEqual(kwargs['timeout'], 30)

    def test_probe_script_file_exists_and_compiles(self):
        with open(placement.PROBE_SCRIPT_PATH) as f:
            source = f.read()
        compile(source, placement.PROBE_SCRIPT_PATH, 'exec')

    @patch.object(placement.subprocess, 'run')
    @patch.object(placement.subprocess, 'check_output')
    def test_defaults_do_not_probe(self, check_output, run):
        a = self.make_adapter(wide=False, strategy='')
        self.assertFalse(a.render_wide_provider_trees)
        self.assertFalse(a.render_generation_strategy)
        check_output.assert_not_called()
        run.assert_not_called()

    @patch.object(placement.subprocess, 'run')
    @patch.object(placement.subprocess, 'check_output')
    def test_deinstalled_package_is_unsupported(self, check_output, run):
        check_output.return_value = _dpkg('deinstall ok config-files')
        a = self.make_adapter(wide=True, strategy='breadth-first')
        self.assertFalse(a.render_wide_provider_trees)
        self.assertFalse(a.render_generation_strategy)
        run.assert_not_called()

    def _assert_probe_failure(self, run_kwargs):
        with patch.object(placement.subprocess, 'check_output',
                          return_value=_dpkg()), \
                patch.object(placement.subprocess, 'run',
                             **run_kwargs):
            a = self.make_adapter(wide=True, strategy='breadth-first')
            self.assertFalse(a.render_wide_provider_trees)
            self.assertFalse(a.render_generation_strategy)
        self.assertTrue(
            any('probe failed' in w for w in self.warnings(self.log)))

    def test_probe_timeout(self):
        self._assert_probe_failure(
            {'side_effect': subprocess.TimeoutExpired('x', 30)})

    def test_probe_non_json(self):
        self._assert_probe_failure({'return_value': _proc('not json')})

    def test_probe_nonzero_exit(self):
        self._assert_probe_failure(
            {'return_value': _proc('', returncode=1, stderr='boom')})

    @patch.object(placement.subprocess, 'run')
    @patch.object(placement.subprocess, 'check_output')
    def test_workarounds_supported_strategy_not(self, check_output, run):
        check_output.return_value = _dpkg()
        run.return_value = _proc({
            'optimize_for_wide_provider_trees': True,
            'allocation_candidates_generation_strategy': False,
            'strategy_choices': None})
        a = self.make_adapter(wide=True, strategy='breadth-first')
        self.assertTrue(a.render_wide_provider_trees)
        self.assertEqual(a.render_generation_strategy, '')

    @patch.object(placement.subprocess, 'run')
    @patch.object(placement.subprocess, 'check_output')
    def test_strategy_supported_workarounds_not(self, check_output, run):
        check_output.return_value = _dpkg()
        run.return_value = _proc({
            'optimize_for_wide_provider_trees': False,
            'allocation_candidates_generation_strategy': True,
            'strategy_choices': ['depth-first', 'breadth-first']})
        a = self.make_adapter(wide=True, strategy='breadth-first')
        self.assertFalse(a.render_wide_provider_trees)
        self.assertEqual(a.render_generation_strategy, 'breadth-first')

    @patch.object(placement.subprocess, 'run')
    @patch.object(placement.subprocess, 'check_output')
    def test_invalid_strategy_ignored_with_warning(self, check_output, run):
        check_output.return_value = _dpkg()
        run.return_value = _proc(SUPPORTED)
        charm = self.make_charm('caracal', strategy='foo')
        self.assertEqual(charm.options.render_generation_strategy, '')
        charm.log_tuning_option_warnings()
        self.assertTrue(any('foo' in w for w in self.warnings(self.log)))

    @patch.object(placement.subprocess, 'run')
    @patch.object(placement.subprocess, 'check_output')
    def test_strategy_is_normalized(self, check_output, run):
        check_output.return_value = _dpkg()
        run.return_value = _proc(SUPPORTED)
        a = self.make_adapter(strategy=' Breadth-First ')
        self.assertEqual(a.render_generation_strategy, 'breadth-first')

    def test_adapter_keeps_api_adapter_interface(self):
        cls = placement.PlacementConfigurationAdapter
        self.assertTrue(issubclass(cls, os_adapters.APIConfigurationAdapter))
        self.assertTrue(hasattr(cls, 'service_listen_info'))
        self.assertTrue(hasattr(cls, 'wsgi_worker_context'))


class TestTuningWarnings(AdapterHelper):

    def setUp(self):
        super().setUp()
        self.log = self.start_log_patch()

    @patch.object(placement.subprocess, 'run')
    @patch.object(placement.subprocess, 'check_output')
    def test_render_with_interfaces_calls_parent(
            self, check_output, run):
        check_output.return_value = _dpkg()
        run.return_value = _proc(SUPPORTED)
        charm = self.make_charm('caracal', wide=True,
                                strategy='breadth-first')
        with patch.object(charms_openstack.charm.HAOpenStackCharm,
                          'render_with_interfaces') as parent:
            charm.render_with_interfaces(['iface'], ['conf'])
        parent.assert_called_once_with(['iface'], ['conf'])

    @patch.object(placement.subprocess, 'run')
    @patch.object(placement.subprocess, 'check_output')
    def test_caracal_supported_has_no_ignored_warning(
            self, check_output, run):
        check_output.return_value = _dpkg()
        run.return_value = _proc(SUPPORTED)
        charm = self.make_charm('caracal', wide=True,
                                strategy='breadth-first')
        with patch.object(charms_openstack.charm.HAOpenStackCharm,
                          'render_with_interfaces') as parent:
            charm.render_with_interfaces(['iface'])
        parent.assert_called_once_with(['iface'], None)
        self.assertEqual(self.warnings(self.log), [])


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, 'src', 'templates')

EPOXY_DEFAULT_RENDER = (
    '[DEFAULT]\ndebug = False\nuse_syslog = true\n\n[api]\n'
    'auth_strategy = keystone\n\n\n\n[keystone_authtoken]\n\n'
    '[placement]\nrandomize_allocation_candidates = true\n\n'
    '[oslo_policy]\n'
    '# Note: Needed for Epoxy but due to be deprecated in the future.\n'
    'enforce_scope = False\nenforce_new_defaults = False')


class _Opts(object):
    debug = 'False'

    def __init__(self, wide=False, strategy=''):
        self.render_wide_provider_trees = wide
        self.render_generation_strategy = strategy


class _SharedDB(object):
    host = None


def render_template(release, wide=False, strategy=''):
    with open(os.path.join(TEMPLATES, release, 'placement.conf')) as f:
        source = f.read()
    # Default Environment mirrors charmhelpers' (no trim_blocks etc).
    env = jinja2.Environment(loader=jinja2.DictLoader({
        'parts/section-keystone-authtoken': '[keystone_authtoken]',
        'placement.conf': source}))
    return env.get_template('placement.conf').render(
        options=_Opts(wide, strategy), shared_db=_SharedDB())


class TestTemplates(test_utils.PatchHelper):

    def test_caracal_defaults_byte_identical_to_train(self):
        self.assertEqual(render_template('caracal'),
                         render_template('train'))

    def test_epoxy_defaults_byte_identical_to_baseline(self):
        self.assertEqual(render_template('epoxy'), EPOXY_DEFAULT_RENDER)

    def test_options_rendered_caracal(self):
        out = render_template('caracal', wide=True, strategy='breadth-first')
        self.assertIn('[placement]\nrandomize_allocation_candidates = true\n'
                      'allocation_candidates_generation_strategy = '
                      'breadth-first\n\n[workarounds]\n'
                      'optimize_for_wide_provider_trees = true', out)
        cp = configparser.ConfigParser()
        cp.read_string(out)
        self.assertEqual(
            cp.sections(),
            ['api', 'keystone_authtoken', 'placement', 'workarounds'])

    def test_options_rendered_epoxy_section_order(self):
        out = render_template('epoxy', wide=True, strategy='breadth-first')
        self.assertIn('allocation_candidates_generation_strategy = '
                      'breadth-first\n\n[workarounds]\n'
                      'optimize_for_wide_provider_trees = true\n\n'
                      '[oslo_policy]\n', out)
        cp = configparser.ConfigParser()
        cp.read_string(out)
        self.assertEqual(
            cp.sections(),
            ['api', 'keystone_authtoken', 'placement', 'workarounds',
             'oslo_policy'])

    def test_options_individually_rendered(self):
        for release in ('caracal', 'epoxy'):
            strat_only = render_template(release, strategy='breadth-first')
            self.assertIn('allocation_candidates_generation_strategy = '
                          'breadth-first', strat_only)
            self.assertNotIn('workarounds', strat_only)
            wide_only = render_template(release, wide=True)
            self.assertIn('[workarounds]', wide_only)
            self.assertNotIn('generation_strategy', wide_only)

    def test_train_template_has_no_tuning_options(self):
        with open(os.path.join(TEMPLATES, 'train', 'placement.conf')) as f:
            text = f.read()
        self.assertNotIn('workarounds', text)
        self.assertNotIn('generation_strategy', text)


class TestConfigYaml(test_utils.PatchHelper):

    def setUp(self):
        super().setUp()
        with open(os.path.join(ROOT, 'src', 'config.yaml')) as f:
            self.options = yaml.safe_load(f)['options']

    def test_wide_provider_trees_option(self):
        opt = self.options['optimize-for-wide-provider-trees']
        self.assertEqual(opt['type'], 'boolean')
        self.assertIs(opt['default'], False)

    def test_generation_strategy_option(self):
        opt = self.options['allocation-candidates-generation-strategy']
        self.assertEqual(opt['type'], 'string')
        self.assertEqual(opt['default'], '')

    def test_openstack_origin_default_unchanged(self):
        self.assertEqual(self.options['openstack-origin']['default'],
                         'caracal')
