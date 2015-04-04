class zstacklib_packages {
    case $zstackbase::params::systemtype {
        "redhat" : {
            $pydev = "python-devel"
        }
        "ubuntu" : {
            $pydev = "python-dev"
        }
    }

    package {[
       "python-setuptools",
       "python",
       "gcc",
       "$pydev",
     ]:}

    exec {"install_pip":
        path => "/bin/:/usr/bin",
        command => "easy_install pip",
        creates => "/usr/bin/pip",
        logoutput => true,
        require => Package['python-setuptools'],
    }
}

class zstacklib_egg {
    $egg = "$zstackbase::params::basepath/zstacklib.egg"
    zstackbase::file_egg {$egg:
        egg_source => "puppet:///modules/zstacklib/zstacklib.egg",
    }

    zstackbase::install_egg {$egg:
        egg_subscribe => File["$egg"],
    }
}


class zstacklib::entry {
    include zstackbase
    include zstacklib_packages
    include zstacklib_egg

    Class['zstackbase'] -> Class['zstacklib_packages'] -> Class['zstacklib_egg']
}
