define zstackbase::iptables($requires=[]) {
    exec { "$title":
        command => "iptables $title",
        path => "/sbin:/bin/:/usr/bin",
        unless => "/sbin/iptables-save | grep -- '$title' > /dev/null",
        logoutput => true,
        require => $requires,
    }
}
