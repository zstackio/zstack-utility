class virtualrouter_system {
    package {[
        "dnsmasq",
    ]:
    }

    file {"/etc/dnsmasq.conf":
        mode => 644,
        owner => root,
        group => root,
        source => "puppet:///modules/virtualrouter/dnsmasq.conf",
        require => Package["dnsmasq"],
    }

    exec { "create_host_dhcp_file":
        command => "/bin/touch /etc/hosts.dhcp",
        creates => "/etc/hosts.dhcp",
        require => Package["dnsmasq"],
    }

    exec { "create_host_option_file":
        command => "/bin/touch /etc/hosts.option",
        creates => "/etc/hosts.option",
        require => Package["dnsmasq"],
    }

    service {"dnsmasq":
        ensure => "running",
        hasstatus => true,
        hasrestart => true,
        enable => true,
        require => [File["/etc/dnsmasq.conf"], Package["dnsmasq"], Exec["create_host_dhcp_file", "create_host_option_file"]],
    }

    file {"/etc/sysconfig/iptables":
        mode => 600,
        owner => root,
        group => root,
        source => "puppet:///modules/virtualrouter/iptables",
    }

    service {"iptables":
        ensure => "running",
        hasstatus => true,
        hasrestart => true,
        enable => true,
        require => [File["/etc/sysconfig/iptables"]],
    }

    zstackbase::iptables {"-A INPUT -p tcp -m tcp --dport 7272 -j ACCEPT":
        requires => [Service["iptables"]],
    }
}

class virtualrouter_agent {
    $egg = "$zstackbase::params::basepath/zstack_virtualrouter.egg"

    zstackbase::file_egg {$egg:
        egg_source => "puppet:///modules/virtualrouter/zstack-virtualrouter.egg",
    }

    zstackbase::install_egg {$egg:
        egg_subscribe => File["$egg"],
    }

    $service_file = "/etc/init.d/zstack-virtualrouter"
    zstackbase::install_service_file {$service_file:
        file_source => "puppet:///modules/virtualrouter/zstack-virtualrouter",
    }

    zstackbase::agent_service {"zstack-virtualrouter":
        service_subscribe => [Exec["install_$egg"], File[$service_file]],
    }
}

class virtualrouter::entry {
    include zstackbase
    include zstacklib
    include virtualrouter_system
    include virtualrouter_agent

    Class['zstackbase'] -> Class['zstacklib'] -> Class['virtualrouter_system'] -> Class['virtualrouter_agent']
}
