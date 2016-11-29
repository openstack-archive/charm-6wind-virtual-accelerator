import charms.reactive as reactive
import charmhelpers.core.host as host
import charmhelpers.contrib.openstack.utils as ch_utils

import charms_openstack.charm as charm
import charm.openstack.virtual_accelerator as va

NOVA_DEFAULT_CONFS = {
    'liberty': [
        ('monkey_patch', 'true'),
        ('monkey_patch_modules', 'nova.virt.libvirt.vif:openstack_6wind_extensions.liberty.nova.virt.libvirt.vif.decorator'),
    ],
    'mitaka': [
        ('monkey_patch', 'true'),
        ('monkey_patch_modules', 'nova.virt.libvirt.vif:openstack_6wind_extensions.mitaka.nova.virt.libvirt.vif.decorator'),
    ],
}

@reactive.when_not('charm.installed')
def install_packages():
    with charm.provide_charm_instance() as va_charm:
        va_charm.install_prerequisites()
        va_charm.delete_default_libvirt_net()
        va_charm.install_credentials()
        va_charm.install_va()
        va_charm.install_license()
        va_charm.install_os_extensions()
    reactive.set_state('charm.installed')

@reactive.when('config.changed', 'charm.installed')
def config_changed():
    with charm.provide_charm_instance() as va_charm:
        va_charm.render_config()

@reactive.when('neutron-plugin.connected', 'charm.installed')
def configure_neutron_plugin(neutron_plugin):
    release = ch_utils.os_release('nova-common')
    neutron_plugin.configure_plugin(
        plugin='ovs',
        config={
            "nova-compute": {
                "/etc/nova/nova.conf": {
                    "sections": {
                        'DEFAULT': NOVA_DEFAULT_CONFS[release],
                    }
                }
            }
        }
    )
    # Assess status, to update Workload and Agent states in `juju status`
    with charm.provide_charm_instance() as va_charm:
        va_charm.assess_status()

@reactive.when_file_changed(va.VirtualAcceleratorCharm.fp_config)
@reactive.when('charm.installed')
@reactive.when('service-control.connected')
def restart_va(neutron_control):
    with charm.provide_charm_instance() as va_charm:
        va_charm.restart()
# https://github.com/openstack/charm-interface-service-control
        neutron_control.request_restart('openvswitch-switch')

@reactive.when('neutron-plugin.connected')
def set_conn_state(neutron_plugin):
    reactive.set_state('plugin-connected-once')

@reactive.when('plugin-connected-once')
@reactive.when_not('neutron-plugin.connected')
@reactive.when_not('departed')
def departing():
    with charm.provide_charm_instance() as va_charm:
        va_charm.stop()
        va_charm.uninstall_os_extensions()
        va_charm.uninstall_license()
        va_charm.uninstall_va()
        # uninstall only once
        reactive.set_state('departed')
