# Overview

Virtual Accelerator is a 6WIND solution to enhance network performance on
hypervisors. This charm will install the software into /usr/local/bin.

# Installation

To deploy this charm you will need at a minimum: a working Juju 2.0+
installation (this charm uses the `resources` feature), a working OpenStack
bundle.

This charm has been tested with xenial, with OpenStack Mitaka release.

# Usage

Deploy the Virtual Accelerator charm and relate it to your Openstack setup:

   juju deploy cs:~6wind/virtual-accelerator --resource credentials=~/credentials.deb
   # --resource license=va.lic --resource custom_fp_conf=custom_fast_path.env

   juju add-relation virtual-accelerator nova-compute

   juju add-relation virtual-accelerator neutron-openvswitch

MANDATORY: The 6WIND's packages are available from a 6WIND repository server. In
order to download these packages, you need to get a credentials file that is
available from support@6wind.com.

OPTIONAL: If you have one, provide your license file as a resource when
deploying. Without it, the Virtual Accelerator will only run for a grace
period of 24 hours.

# Contact Information

6WIND support - support@6wind.com

## Upstream Project Name

6WIND website http://www.6wind.com
