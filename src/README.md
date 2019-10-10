# Overview

This charm provides the Placement service for an OpenStack Cloud.

OpenStack Train or later is required.

# Usage

As of Train, the placement API is managed by this charm and is no longer managed
by the nova-cloud-controller charm.

Placement relies on mysql, keystone, and nova-cloud-controller charms:

    juju deploy --series bionic --config openstack-origin=cloud:bionic-train cs:placement
    juju add-relation placement mysql
    juju add-relation placement keystone
    juju add-relation placement nova-cloud-controller

If upgrading nova-cloud-controller to Train, the upgrade requires some coordination to
transition to the new API endpoints. Prior to upgrading nova-cloud-controller to Train,
the placement charm must be deployed for Train and related to the Stein-based
nova-cloud-controller. It is important that nova-cloud-controller is paused while the
API transition occurs (pause prior to adding relations for the placement charm) as the
placement charm will migrate existing placement tables from the nova_api database to a
new placement database. Once the new placement endpoints are registered,
nova-cloud-controller can be resumed. After all of the steps have completed,
nova-cloud-controller can then be upgraded to Train. Here's an example of the steps
that were just described:

    juju deploy --series bionic --config openstack-origin=cloud:bionic-train cs:placement
    juju run-action nova-cloud-controller/0 pause
    juju add-relation placement mysql
    juju add-relation placement keystone
    juju add-relation placement nova-cloud-controller
    openstack endpoint list # ensure placement endpoints are listening on new placment IP address
    juju run-action nova-cloud-controller/0 resume
    juju config nova-cloud-controller openstack-origin=cloud:bionic-train

# Bugs

Please report bugs on [Launchpad](https://bugs.launchpad.net/charm-placement/+filebug).

For general questions please refer to the OpenStack [Charm Guide](https://docs.openstack.org/charm-guide/latest/).
