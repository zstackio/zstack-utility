class zstackbase {
    include zstackbase::params

    file {$zstackbase::params::basepath:
        ensure => "directory",
    }
}
