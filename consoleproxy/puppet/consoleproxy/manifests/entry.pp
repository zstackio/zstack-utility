class consoleproxy_system {
   zstackbase::iptables {"-A INPUT -p tcp -m tcp --dport 7758 -j ACCEPT":}
}

class consoleproxy_agent {
    $egg = "$zstackbase::params::basepath/zstack_consoleproxy.egg"
    zstackbase::file_egg {$egg:
        egg_source => "puppet:///modules/consoleproxy/zstack-consoleproxy.egg",
    }

    zstackbase::install_egg {$egg:
        egg_subscribe => File["$egg"],
    }

    $service_file = "/etc/init.d/zstack-console-proxy"
    zstackbase::install_service_file {$service_file:
        file_source => "puppet:///modules/consoleproxy/zstack-console-proxy",
    }

    zstackbase::agent_service {"zstack-console-proxy":
        service_subscribe => [Exec["install_$egg"], File[$service_file]],
    }
}

class consoleproxy::entry {
    include zstackbase
    include zstacklib
    include consoleproxy_system
    include consoleproxy_agent

    Class['zstackbase'] -> Class['zstacklib'] -> Class['consoleproxy_system'] -> Class['consoleproxy_agent']
}
