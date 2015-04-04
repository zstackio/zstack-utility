define zstackbase::install_egg($egg_subscribe) {
    exec {"install_$title":
        command => "easy_install $title",
        path => "/bin/:/usr/bin",
        refreshonly => true,
        subscribe => $egg_subscribe,
        logoutput => true,
    }
}
