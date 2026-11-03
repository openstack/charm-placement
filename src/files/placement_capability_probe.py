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

"""Capability probe for the installed python3-placement package.

Run by the charm with the system python (``/usr/bin/python3 -I``) because
the charm virtualenv cannot import oslo.config or placement. Prints exactly
one JSON line with the keys ``optimize_for_wide_provider_trees``,
``allocation_candidates_generation_strategy`` (booleans) and
``strategy_choices`` (list of strings or null).
"""

import json

from oslo_config import cfg

import placement.conf

WIDE_OPTION = 'optimize_for_wide_provider_trees'
STRATEGY_OPTION = 'allocation_candidates_generation_strategy'


def option_choices(conf, group, name):
    """Return the choices declared by an option, or None."""
    try:
        opt = conf._groups[group]._opts[name]['opt']
        return list(opt.type.choices)
    except Exception:
        return None


def option_is_registered(conf, group, name):
    """Return True when the group exposes the option."""
    try:
        getattr(conf, group)[name]
        return True
    except Exception:
        return False


def main():
    conf = cfg.ConfigOpts()
    placement.conf.register_opts(conf)
    strategy_supported = option_is_registered(
        conf, 'placement', STRATEGY_OPTION)
    print(json.dumps({
        WIDE_OPTION: option_is_registered(conf, 'workarounds', WIDE_OPTION),
        STRATEGY_OPTION: strategy_supported,
        'strategy_choices': (
            option_choices(conf, 'placement', STRATEGY_OPTION)
            if strategy_supported else None),
    }))


if __name__ == '__main__':
    main()
