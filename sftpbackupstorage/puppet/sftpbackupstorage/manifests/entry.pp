class sftpbackupstorage_system {
    case $zstackbase::params::systemtype {
        "redhat" : {
            $sshclient = "openssh-clients"
        }
        "ubuntu" : {
            $sshclient = "openssh-client"
        }
    }

    package {[
        "wget",
        "openssh-server",
        "$sshclient",
    ]:}

   zstackbase::iptables {"-A INPUT -p tcp -m tcp --dport 7171 -j ACCEPT":}
}

class sftpbackupstorage_sshkey {
    #TODO:fix the root dir
    $sshkey_dir = "/home/root/.ssh"
    file {"$sshkey_dir":
        ensure => "directory",
        owner => "root",
        group => "root",
        mode => 700,
    }

    $authorized_keys = "$sshkey_dir/authorized_keys"
    file {"$authorized_keys":
        ensure => "present",
        owner => "root",
        group => "root",
        mode => 600,
    }

    exec {"generate_sshkey_for_sftp":
        command => "ssh-keygen -t dsa -N '' -f $sshkey_dir/id_rsa.sftp",
        path => "/bin/:/usr/bin",
        creates => "$sshkey_dir/id_rsa.sftp",
    }

    exec {"import_public_key":
        command => "fgrep -x -q -f $sshkey_dir/id_rsa.sftp.pub $authorized_keys || cat $sshkey_dir/id_rsa.sftp.pub >> $authorized_keys",
        path => "/bin/:/usr/bin",
    }

    File["$sshkey_dir"] -> File["$authorized_keys"] -> Exec["generate_sshkey_for_sftp"] -> Exec["import_public_key"]
}

class sftpbackupstorage_agent {
    $egg = "$zstackbase::params::basepath/zstack_sftpbackupstorage.egg"
    zstackbase::file_egg {$egg:
        egg_source => "puppet:///modules/sftpbackupstorage/zstack-sftpbackupstorage.egg",
    }

    zstackbase::install_egg {$egg:
        egg_subscribe => File["$egg"],
    }

    $service_file = "/etc/init.d/zstack-sftpbackupstorage"
    zstackbase::install_service_file {$service_file:
        file_source => "puppet:///modules/sftpbackupstorage/zstack-sftpbackupstorage",
    }

    zstackbase::agent_service {"zstack-sftpbackupstorage":
        service_subscribe => [Exec["install_$egg"], File[$service_file]],
    }
}

class sftpbackupstorage::entry {
    include zstackbase
    include zstacklib
    include sftpbackupstorage_system
    include sftpbackupstorage_sshkey
    include sftpbackupstorage_agent

    Class['zstackbase'] -> Class['zstacklib'] -> Class['sftpbackupstorage_system'] -> Class['sftpbackupstorage_sshkey'] -> Class['sftpbackupstorage_agent']
}
