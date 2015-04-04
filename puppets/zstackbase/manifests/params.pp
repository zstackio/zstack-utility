class zstackbase::params {
    $systemtype = $operatingsystem ? {
    /(Red Hat|CentOS|Fedora)/ => "redhat",
    /(Ubuntu|Debian)/ => "ubuntu",
    }

    $basepath = "/var/lib/zstack"
}
