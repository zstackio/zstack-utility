define zstackbase::file_egg($egg_source, $egg_require=[]) {
    file {$title:
        mode => 400,
        owner => root,
        group => root,
        source => $egg_source,
        require => $egg_require,
    }
}
