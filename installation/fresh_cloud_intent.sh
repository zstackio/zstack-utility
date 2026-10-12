#!/bin/bash

# Return success only for the installer-owned full first-install path, before
# it writes the local installation identity. The target DB is independently
# checked by DeployDBCmd immediately before deployment.
zstack_is_fresh_cloud_install() {
    local upgrade="$1" only_install="$2" drop_db="$3" keep_db="$4"
    local install_root="$5" properties="$6" system_root="${7:-/}"
    [ "$upgrade" = "y" ] && return 1
    [ -n "$only_install" ] && return 1
    [ -n "$drop_db" ] && return 1
    [ -n "$keep_db" ] && return 1

    local identity_path
    for identity_path in \
            "$install_root/VERSION" \
            "$properties" \
            "$install_root/apache-tomcat/webapps/zstack/WEB-INF/classes/zstack.properties" \
            "$system_root/etc/init.d/zstack" \
            "$system_root/usr/lib/systemd/system/zstack.service" \
            "$system_root/etc/systemd/system/zstack.service"; do
        [ -e "$identity_path" ] && return 1
    done
    return 0
}
