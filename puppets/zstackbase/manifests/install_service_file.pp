define zstackbase::install_service_file($file_source) {
    file {$title:
        mode => 755,
        owner => root,
        group => root,
        source => $file_source,
    }
}
