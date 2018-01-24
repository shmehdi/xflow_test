from tempest.common import custom_matchers
from tempest.common import waiters
from tempest import config
from tempest import exceptions
from tempest.lib.common.utils import test_utils
from tempest.scenario import manager
from tempest import test

CONF=config.CONF

class TestClass(manager.ScenarioTest):

def nova_show(self, server):
        got_server = (self.servers_client.show_server(server['id'])
                      ['server'])
        excluded_keys = ['OS-EXT-AZ:availability_zone']
        # Exclude these keys because of LP:#1486475
        excluded_keys.extend(['OS-EXT-STS:power_state', 'updated'])
        self.assertThat(
            server, custom_matchers.MatchesDictExceptForKeys(
                got_server, excluded_keys=excluded_keys))

    def cinder_show(self, volume):
        got_volume = self.volumes_client.show_volume(volume['id'])['volume']
        self.assertEqual(volume, got_volume)

    def nova_reboot(self, server):
        self.servers_client.reboot_server(server['id'], type='SOFT')
        waiters.wait_for_server_status(self.servers_client,
                                       server['id'], 'ACTIVE')

    def check_partitions(self):
        # NOTE(andreaf) The device name may be different on different guest OS
        partitions = self.linux_client.get_partitions()
        self.assertEqual(1, partitions.count(CONF.compute.volume_device_name))

    def create_and_add_security_group_to_server(self, server):
        secgroup = self._create_security_group()
        self.servers_client.add_security_group(server['id'],
                                               name=secgroup['name'])
        self.addCleanup(self.servers_client.remove_security_group,
                        server['id'], name=secgroup['name'])

        def wait_for_secgroup_add():
            body = (self.servers_client.show_server(server['id'])
                    ['server'])
            return {'name': secgroup['name']} in body['security_groups']

        if not test_utils.call_until_true(wait_for_secgroup_add,
                                          CONF.compute.build_timeout,
                                          CONF.compute.build_interval):
            msg = ('Timed out waiting for adding security group %s to server '
                   '%s' % (secgroup['id'], server['id']))
            raise exceptions.TimeoutException(msg)

    def _get_floating_ip_in_server_addresses(self, floating_ip, server):
        for network_name, addresses in server['addresses'].items():
            for address in addresses:
                if (address['OS-EXT-IPS:type'] == 'floating' and
                        address['addr'] == floating_ip['ip']):
                    return address

    @test.idempotent_id('bdbb5441-9204-419d-a225-b4fdbfb1a1a8')
    @test.services('compute', 'volume', 'image', 'network')
    def test_minimum_basic_scenario(self):
        image = self.glance_image_create()
		print('keypair created')
        keypair = self.create_keypair()

        server = self.create_server(image_id=image,
                                    key_name=keypair['name'],
                                    wait_until='ACTIVE')
        servers = self.servers_client.list_servers()['servers']
        self.assertIn(server['id'], [x['id'] for x in servers])

		print('instance created')
        self.nova_show(server)

        volume = self.create_volume()
        volumes = self.volumes_client.list_volumes()['volumes']
        self.assertIn(volume['id'], [x['id'] for x in volumes])

        self.cinder_show(volume)

        volume = self.nova_volume_attach(server, volume)
        self.addCleanup(self.nova_volume_detach, server, volume)
        self.cinder_show(volume)

        floating_ip = self.create_floating_ip(server)
        # fetch the server again to make sure the addresses were refreshed
        # after associating the floating IP
        server = self.servers_client.show_server(server['id'])['server']
        address = self._get_floating_ip_in_server_addresses(
            floating_ip, server)
        self.assertIsNotNone(
            address,
            "Failed to find floating IP '%s' in server addresses: %s" %
            (floating_ip['ip'], server['addresses']))

        self.create_and_add_security_group_to_server(server)

        # check that we can SSH to the server before reboot
        self.linux_client = self.get_remote_client(
            floating_ip['ip'], private_key=keypair['private_key'])

        self.nova_reboot(server)

        # check that we can SSH to the server after reboot
        # (both connections are part of the scenario)
        self.linux_client = self.get_remote_client(
            floating_ip['ip'], private_key=keypair['private_key'])

        self.check_partitions()

        # delete the floating IP, this should refresh the server addresses
        self.compute_floating_ips_client.delete_floating_ip(floating_ip['id'])

        def is_floating_ip_detached_from_server():
            server_info = self.servers_client.show_server(
                server['id'])['server']
            address = self._get_floating_ip_in_server_addresses(
                floating_ip, server_info)
            return (not address)

        if not test_utils.call_until_true(
            is_floating_ip_detached_from_server,
            CONF.compute.build_timeout,
            CONF.compute.build_interval):
            msg = ("Floating IP '%s' should not be in server addresses: %s" %
                   (floating_ip['ip'], server['addresses']))
            raise exceptions.TimeoutException(msg)
