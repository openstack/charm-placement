# Overview

The placement charm deploys [Placement][upstream-placement], the core OpenStack
API service that tracks the inventory and usage of various cloud resources
(e.g. compute, storage, network addresses). The charm works alongside other
Juju-deployed OpenStack services.

> **Note**: The placement charm is supported starting with OpenStack Train.

# Usage

## Configuration

This section covers common and/or important configuration options. See file
`config.yaml` for the full list of options, along with their descriptions and
default values. See the [Juju documentation][juju-docs-config-apps] for details
on configuring applications.

#### `openstack-origin`

The `openstack-origin` option states the software sources. A common value is an
OpenStack UCA release (e.g. 'cloud:bionic-ussuri' or 'cloud:focal-victoria').
See [Ubuntu Cloud Archive][wiki-uca]. The underlying host's existing apt
sources will be used if this option is not specified (this behaviour can be
explicitly chosen by using the value of 'distro').

## Deployment

Placement is often containerised. Here a single unit is deployed to a new
container on machine '1':

    juju deploy --to lxd:1 placement

Placement requires these applications to be present: keystone,
nova-cloud-controller, and a cloud database.

The database application is determined by the series. Prior to focal
[percona-cluster][percona-cluster-charm] is used, otherwise it is
[mysql-innodb-cluster][mysql-innodb-cluster-charm]. In the example deployment
below mysql-innodb-cluster has been chosen.

    juju deploy mysql-router placement-mysql-router
    juju add-relation placement-mysql-router:db-router mysql-innodb-cluster:db-router
    juju add-relation placement-mysql-router:shared-db placement:shared-db

Add relations to the remaining applications:

    juju add-relation placement:identity-service keystone:identity-service
    juju add-relation placement:placement nova-cloud-controller:placement

## Upgrading to OpenStack Train

Prior to OpenStack Train, the placement API was managed by the
nova-cloud-controller charm. Some extra steps are therefore needed when
performing a Stein to Train upgrade. The documented procedure can be found on
the [Special charm procedures][cdg-upgrade-special] page in the [OpenStack
Charms Deployment Guide][cdg].

## High availability

When more than one unit is deployed with the [hacluster][hacluster-charm]
application the charm will bring up an HA active/active cluster.

There are two mutually exclusive high availability options: using virtual IP(s)
or DNS. In both cases the hacluster subordinate charm is used to provide the
Corosync and Pacemaker backend HA functionality.

See [Infrastructure high availability][cdg-ha-apps] in the [OpenStack Charms
Deployment Guide][cdg] for details.

# Documentation

The OpenStack Charms project maintains two documentation guides:

* [OpenStack Charm Guide][cg]: for project information, including development
  and support notes
* [OpenStack Charms Deployment Guide][cdg]: for charm usage information

# Bugs

Please report bugs on [Launchpad][lp-bugs-charm-placement].

<!-- LINKS -->

[cg]: https://docs.openstack.org/charm-guide
[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide
[lp-bugs-charm-placement]: https://bugs.launchpad.net/charm-placement/+filebug
[upstream-placement]: https://docs.openstack.org/placement
[cdg-upgrade-special]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/upgrade-special.html
[cdg-ha-apps]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-ha.html#ha-applications
[hacluster-charm]: https://jaas.ai/hacluster
[wiki-uca]: https://wiki.ubuntu.com/OpenStack/CloudArchive
[juju-docs-config-apps]: https://juju.is/docs/configuring-applications
[percona-cluster-charm]: https://jaas.ai/percona-cluster
[mysql-innodb-cluster-charm]: https://jaas.ai/mysql-innodb-cluster
