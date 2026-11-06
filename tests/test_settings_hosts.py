from django.test import SimpleTestCase

from trackable.settings.hosts import hosts_from_fqdn_list


class HostsFromFqdnListTest(SimpleTestCase):
    def test_scheme_and_host_only(self):
        self.assertEqual(hosts_from_fqdn_list("https://a.example.com"), ["a.example.com"])

    def test_host_with_port_no_scheme(self):
        self.assertEqual(hosts_from_fqdn_list("a.example.com:8000"), ["a.example.com"])

    def test_bare_host(self):
        self.assertEqual(hosts_from_fqdn_list("a.example.com"), ["a.example.com"])

    def test_scheme_port_and_path(self):
        self.assertEqual(
            hosts_from_fqdn_list("https://a.example.com:443/path"), ["a.example.com"]
        )

    def test_comma_separated_list_mixed_styles(self):
        self.assertEqual(
            hosts_from_fqdn_list("a.example.com:8000,b.example.com"),
            ["a.example.com", "b.example.com"],
        )

    def test_empty_string(self):
        self.assertEqual(hosts_from_fqdn_list(""), [])

    def test_whitespace_only(self):
        self.assertEqual(hosts_from_fqdn_list("   "), [])

    def test_lowercases_hostnames(self):
        self.assertEqual(hosts_from_fqdn_list("HTTPS://A.Example.com"), ["a.example.com"])

    def test_skips_empty_entries_between_commas(self):
        self.assertEqual(
            hosts_from_fqdn_list("a.example.com,,b.example.com"),
            ["a.example.com", "b.example.com"],
        )
