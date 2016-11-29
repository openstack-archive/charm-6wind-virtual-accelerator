import libvirt
import os
import shutil
import ssl
import subprocess
import tempfile
import urllib

from pylxd import network, container, Client

import charmhelpers.contrib.openstack.utils as ch_utils
import charmhelpers.contrib.openstack.neutron as neutron
import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.files as files
import charmhelpers.core.host as host
import charmhelpers.fetch as fetch

from charms_openstack.charm import OpenStackCharm
from charms_openstack.adapters import OpenStackRelationAdapters

class VirtualAcceleratorCharm(OpenStackCharm):
    """VirtualAcceleratorCharm defines all possible actions for managing VA.
    """

    # Internal name of charm - used for HA support + others
    name = 'va'

    # First release of openstack this charm supports
    release = 'liberty'

    # Packages the service needs installed
    packages = [
        'libvirt-bin',
        'python-libvirt',
        'qemu',
        'qemu-system-x86',
        'libcurl3',
        'libjansson4',
        neutron.headers_package()
    ]

    # Init services the charm manages
    services = ['virtual-accelerator']

    # Standard interface adapters class to use.
    adapters_class = OpenStackRelationAdapters

    # Ports that need exposing.
    default_service = ''

    resource_creds = 'credentials'
    resource_va_license = 'license'
    resource_fp_conf = 'custom_fp_conf'
    product = 'virtual-accelerator'
    ovs_pkg = 'openvswitch-switch'
    os_extensions = '6wind-openstack-extensions'
    fp_config = '/usr/local/etc/fast-path.env'
    license_file = '/usr/local/etc/va.lic'
    startup_script = '/usr/local/bin/%s.sh' % product
    cpuset_env = '/usr/local/etc/cpuset.env'

    def ports_to_check(self, ports):
        """VA does not expose ports. Don't check any ports automatically.

        Refer to:
        https://github.com/openstack/charms.openstack#not-checking-services-are-running
        """
        return []

    def __init__(self, release=None, **kwargs):
        """Custom initialiser for class
        If no release is passed, then the charm determines the release from the
        ch_utils.os_release() function.
        """
        if release is None:
            release = ch_utils.os_release('nova-common')
        OpenStackCharm.__init__(self, release=release, **kwargs)

    def _get_dpkg_arch(self):
        """Returns the running machine's architecture.
        """
        return subprocess.check_output(['dpkg', '--print-architecture'],
                                       universal_newlines=True).rstrip()

    def _install_deb(self, pkg):
        """Install the provided debian package.
        """
        return subprocess.check_output(['dpkg', '-i', pkg])

    def _fetch_6wind_repo_pkg(self, output):
        """Download the 6WIND package providing 6WIND repository.
        It requires an SSL connection to 6WIND servers through an SSL context.
        Put the package into the output file.
        """
        distrib = 'ubuntu-{}'.format(ch_utils.lsb_release()['DISTRIB_RELEASE'])
        arch = self._get_dpkg_arch()
        version = hookenv.config('va-version')

        pkg = '6wind-%s-%s-repository_%s-1_%s.deb' % \
            (self.product, distrib, version, arch)
        subdir = '%s/%s/%s/%s' % (self.product, distrib, arch, version)
        repo_url = 'https://repo.6wind.com/%s/%s' % (subdir, pkg)

        certs_dir = '/usr/local/etc/certs'
        cacert = certs_dir + '/6wind_ca.crt'
        cert = certs_dir + '/6wind_client.crt'
        key = certs_dir + '/6wind_client.key'

        ctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH,
                                         cafile=cacert)
        ctx.load_cert_chain(cert, key)

        hookenv.log('Using the following URL for 6WIND repo: %s' % \
                    repo_url, level=hookenv.INFO)
        response = urllib.request.urlopen(repo_url, context=ctx)

        host.write_file(output, response.read())

        return

    def _remove_6wind_repo(self):
        """Remove the 6WIND repository package.
        """
        hookenv.status_set('maintenance', 'Uninstalling 6WIND repository')
        hookenv.log('Uninstalling 6WIND repository', level=hookenv.INFO)
        distrib = 'ubuntu-{}'.format(ch_utils.lsb_release()['DISTRIB_RELEASE'])
        arch = self._get_dpkg_arch()

        pkg = '6wind-%s-%s-repository' % (self.product, distrib)
        fetch.apt_purge(pkg)
        fetch.apt_update()

    def install_prerequisites(self):
        """Install correct libvirt and qemu packages.
        For xenial and later, use distro packages since patches are upstream.
        """
        hookenv.status_set('maintenance', 'Installing prerequisites')
        hookenv.log('Installing libvirt, qemu and linux headers',
                    level=hookenv.INFO)
        fetch.apt_install(self.packages,
                          options=['--option=Dpkg::Options::=--force-confnew'])

    def delete_default_libvirt_net(self):
        """Remove the 'default' libvirt network as it otherwise sets up
        bridges and complicated iptables rules, that impedes readability.
        """
        hookenv.status_set('maintenance', 'Cleaning libvirt default network')
        conn = libvirt.open()
        try:
            default_net = conn.networkLookupByName('default')
        except libvirt.libvirtError:
            return conn.close()

        hookenv.log('Deleting default libvirt network', level=hookenv.INFO)
        if default_net.isActive():
            default_net.destroy()
        default_net.undefine()

    def install_credentials(self):
        """Install 6WIND credentials using apt, to enable 6WIND repository
        access.
        """
        hookenv.status_set('maintenance', 'Installing credentials')
        resource = hookenv.resource_get(self.resource_creds)
        if not resource:
            hookenv.log('Missing required credentials resource',
                        level=hookenv.CRITICAL)
            raise Exception('Missing credentials resource: '
                            '{}'.format(self.resource_creds))

        hookenv.log('Installing 6WIND credentials', level=hookenv.INFO)
        self._install_deb(resource)

    def __post_install(self):
        """Do some post-install voodoo.
        """
        hookenv.status_set('maintenance', 'Setting up LXC netns sync with vrf')
        files.sed(self.startup_script, 'vrfd -s', 'vrfd -ls')

        hookenv.status_set('maintenance', 'Disabling CPUSET')
        files.sed(self.cpuset_env, '.*CPUSET_ENABLE.*', 'CPUSET_ENABLE=0')

        host.service('enable', self.product)

    def install_va(self):
        """Install the product using the 6WIND repository.
        While at it, mark OVS on hold, to prevent a version without 6WIND
        patches from being installed on upgrade.
        """
        hookenv.status_set('maintenance', 'Installing %s' % self.product)
        output = '/tmp/6wind-REPO.deb'

        hookenv.log('Downloading 6WIND %s repo package' % self.product,
                    level=hookenv.INFO)
        self._fetch_6wind_repo_pkg(output)

        hookenv.log('Installing 6WIND %s repo package' % self.product,
                    level=hookenv.INFO)
        self._install_deb(output)

        fetch.apt_update()

        hookenv.log('Installing 6WIND %s' % self.product, level=hookenv.INFO)
        fetch.apt_install(self.product)

        self.__post_install()

        hookenv.log('Set hold mark on %s to prevent our 6WIND version from being'
                    ' overridden' % self.ovs_pkg, level=hookenv.INFO)
        fetch.apt_hold(self.ovs_pkg)

    def uninstall_va(self):
        """Uninstall the product, and all packages related to 6WIND.
        Revert the OVS package to the one without 6WIND patches.
        """
        self._remove_6wind_repo()

        hookenv.status_set('maintenance', 'Uninstalling %s' % self.product)
        hookenv.log('Uninstalling %s' % self.product, level=hookenv.INFO)
        fetch.apt_purge(self.product)

        hookenv.status_set('maintenance', 'Cleanup of 6WIND packages')
        hookenv.log('Cleanup of 6WIND packages', level=hookenv.INFO)
        fetch.apt_purge('6wind*')

        hookenv.status_set('maintenance', 'Final cleanup')
        hookenv.log('Final cleanup', level=hookenv.INFO)
        subprocess.check_output(['apt-get', '--assume-yes', 'autoremove'])

        hookenv.status_set('maintenance', 'Reinstall original %s' % self.ovs_pkg)
        hookenv.log('Reinstall original %s' % self.ovs_pkg, level=hookenv.INFO)
        fetch.apt_unhold(self.ovs_pkg)
        cache = fetch.apt_cache()
        pkg = cache[self.ovs_pkg]
        for ver in pkg.version_list:
            # select the closest version in cache, not coming from 6WIND
            if '6wind' in ver.ver_str:
                continue
            fetch.apt_install('%s=%s' % (self.ovs_pkg, ver.ver_str),
                              ['--option=Dpkg::Options::=--force-confold',
                               '--allow-downgrades'])
            break

        self._libvirt_restart()

    def install_os_extensions(self):
        """Install OpenStack extensions that provide 6WIND monkey patch.
        """
        hookenv.status_set('maintenance', 'Installing 6WIND Openstack Extensions')
        hookenv.log('Installing 6WIND Openstack Extensions', level=hookenv.INFO)
        fetch.apt_install(self.os_extensions)

    def uninstall_os_extensions(self):
        """Uninstall OpenStack extensions.
        """
        hookenv.status_set('maintenance', 'Uninstalling 6WIND Openstack Extensions')
        hookenv.log('Uninstalling 6WIND Openstack Extensions', level=hookenv.INFO)
        fetch.apt_purge(self.os_extensions)

    def install_license(self):
        """Put the license resource into the default folder.
        There, il will be scanned when starting the product.
        """
        hookenv.status_set('maintenance', 'Installing license')
        resource = hookenv.resource_get(self.resource_va_license)
        if not resource:
            hookenv.log('VA will run temporarily, without license',
                        level=hookenv.INFO)
            return

        f = open(resource, 'r')
        for line in f:
            if 'BOILERPLATE' in line:
                # ignore this file, it's not a real license file.
                f.close()
                return
        f.close()

        hookenv.log('Installing 6WIND license into ', level=hookenv.INFO)
        shutil.copyfile(resource, self.license_file)
        return

    def uninstall_license(self):
        """Remove the license file from the unit.
        """
        hookenv.status_set('maintenance', 'Uninstalling license')
        try:
            os.remove(self.license_file)
        except FileNotFoundError:
            return

    def render_config(self):
        """Use the FP Wizard to generate the fast path config file, considering
        the charm's configuration options.
        """
        hookenv.status_set('maintenance', 'Generating %s' % self.fp_config)
        hookenv.log('Generating %s' % self.fp_config, level=hookenv.INFO)

        tmp_file = None
        resource = hookenv.resource_get(self.resource_fp_conf)
        if resource:
            with open(resource, 'r') as f:
                line = f.readline()
                if 'BOILERPLATE' not in line:
                    hookenv.log('Use provided custom fp config file',
                                level=hookenv.INFO)
                    tmp_file = resource
                else:
                    hookenv.log('Boilerplate fp config. Using default conf.',
                                level=hookenv.INFO)
                f.close()
        if not tmp_file:
            vm_mem = hookenv.config('VM_MEMORY')
            tmp_conf = tempfile.NamedTemporaryFile()

            tmp_conf.write(str.encode('VM_MEMORY=%s\n' % vm_mem))
            tmp_conf.flush()
            tmp_file = tmp_conf.name

        subprocess.run(['fp-conf-tool', '--update', '--file=%s' % tmp_file])

        shutil.copyfile(tmp_file, self.fp_config)

        if tmp_conf:
            tmp_conf.close()

    def _libvirt_restart(self):
        """Restart libvirt.
        """
        service = 'libvirt-bin'
        hookenv.status_set('maintenance', 'Restarting %s' % service)
        host.service_restart(service)

    def _lxc_bridge_ports_readd(self):
        """When VA restarts, it shuts off all interfaces, including the bridge
        containing LXC containers veth. As they are configured dynamically when
        starting the container itself, there's no /etc/network config for them
        and ifup can't bring them up again.
        Here we use pylxd to get the interfaces names on the host and set them
        up again in the correct bridge.
        """
        hookenv.status_set('maintenance', 'Updating LXC bridge ports')

        client = Client()
        networks = network.Network.all(client)

        for net in networks:
            if net.used_by:
                for c in net.used_by:
                    ct = container.Container.get(client, c.split('/')[-1])
                    ct_net = ct.state().network
                    for iface, conf in ct_net.items():
                        if conf['host_name']:
                            host_name = conf['host_name']
                            subprocess.check_output(['brctl', 'addif',
                                                     net.name, host_name])
                            hookenv.log('Added %s to bridge %s.' %
                                        (net.name, host_name),
                                        level=hookenv.INFO)

    def restart(self):
        """Restart the product, typically after changing configuration options.
        Restart libvirt afterwards, to take fast path hugepages into account.
        """
        hookenv.status_set('maintenance', 'Restarting %s' % self.product)
        hookenv.log('Restarting %s' % self.product, level=hookenv.INFO)
        for service in self.services:
            host.service_restart(service)
        self._libvirt_restart()
        self._lxc_bridge_ports_readd()

    def stop(self):
        """Stop the running product service. This is done when terminating.
        """
        hookenv.status_set('maintenance', 'Stopping %s' % self.product)
        hookenv.log('Stopping %s' % self.product, level=hookenv.INFO)
        for service in self.services:
            host.service_stop(service)
        self._libvirt_restart()
        self._lxc_bridge_ports_readd()
