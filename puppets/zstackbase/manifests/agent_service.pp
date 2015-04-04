define zstackbase::agent_service($service_subscribe) {
    service {$title:
        ensure => "running",
        hasstatus => true,
        hasrestart => true,
        enable => true,
        subscribe => $service_subscribe,
    }
}
