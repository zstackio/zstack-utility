class kvm_checksystem {
    $systemtype = $zstackbase::params::systemtype
    case $systemtype {
       /redhat/ : {
         case $operatingsystemrelease {
            /5(.*)/ : {
                fail("RedHat/CentOS 5.x is not suppored host, please use 6.3 or higher")
                }
            }
        }
      /ubuntu/: {
                notify {"System is $systemtype, release is $operatingsystemrelease":}
        }
      default: {
                fail("$systemtype is not suppored host")
        }
    }
}

class kvm_system {
  case $zstackbase::params::systemtype {
    "redhat" : {
        $qemuimg = "qemu-img"
        $libvirtpython = "libvirt-python"
        $libvirtd = "libvirt"
        $libvirtservice = "libvirtd"
        }
     "ubuntu" : {
        $qemuimg = "qemu-utils"
        $libvirtpython = "python-libvirt"
        $libvirtd = "libvirt-bin"
        $libvirtservice = "libvirt-bin"
        }
    }

  package {[
      "qemu-kvm",
      "$libvirtd",
      "$libvirtpython",
      "$qemuimg",
      "wget",
    ]:
    }

   service {"$libvirtservice":
     ensure => running,
     hasstatus => true,
     hasrestart => true,
     enable => true,
     require => Package["qemu-kvm", "$libvirtd", "$libvirtpython"],
   }

   zstackbase::iptables {"-A INPUT -p tcp -m tcp --dport 7700 -j ACCEPT":}
}

class kvm_agent {
    $egg = "$zstackbase::params::basepath/zstack_kvmagent.egg"
    zstackbase::file_egg {$egg:
        egg_source => "puppet:///modules/kvmagent/zstack-kvmagent.egg",
    }

    zstackbase::install_egg {$egg :
        egg_subscribe => File["$egg"],
    }

    $service_file = "/etc/init.d/zstack-kvmagent"
    zstackbase::install_service_file {$service_file:
        file_source => "puppet:///modules/kvmagent/zstack-kvmagent",
    }

    zstackbase::agent_service {"zstack-kvmagent":
        service_subscribe => [Exec["install_$egg"], File[$service_file]],
    }
}

class kvmagent::entry {
    include zstackbase
    include kvm_checksystem
    include zstacklib
    include kvm_system
    include kvm_agent

    Class['zstackbase'] -> Class['kvm_checksystem'] -> Class['zstacklib'] -> Class['kvm_system'] -> Class['kvm_agent']
}
