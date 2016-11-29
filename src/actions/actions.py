#!/usr/bin/env python3

import os
import sys

# Load modules from $CHARM_DIR/lib
sys.path.append('lib')

import charms.reactive as reactive
import charmhelpers.core.hookenv as hookenv

import charms_openstack.charm as charm


def va_restart_action(*args):
    """Restart Virtual Accelerator"""
    with charm.provide_charm_instance() as va_charm:
        va_charm.restart()
        neutron_control = \
            reactive.RelationBase.from_state('neutron-control.connected')
        neutron_control.request_restart('openvswitch-switch')
        hookenv.status_set('active', 'Unit is ready')

ACTIONS = {
    "restart": va_restart_action,
}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        return "Action %s undefined" % action_name
    else:
        try:
            action(args)
        except Exception as e:
            hookenv.action_fail(str(e))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
