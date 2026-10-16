# Memory optimization deployment

The standard and OSS BIN builds consume the published service RPM pinned by
`zstackzram.rpm.url` and `zstackzram.rpm.sha256` in their respective
`zstackbuild/build.properties` and `zstackbuild/build.oss.properties` files.
Ant verifies the bytes before extracting the RPM's original build manifest and
staging its inventory, installer and canonical NEVRA-named RPM into the WAR's
KVM Agent materials. The RPM remains published through the existing RPM
repository and ISO package lists; it is not copied from the WAR. Cloud
`product.version` and `build.num` do not select or rebuild the service RPM.

`build-zstack-zram-rpm` is the separate component release target. It freezes
the selected `zstackzram.checkout` and takes Version and Release defaults from
that frozen source's RPM spec. A new component build is published once through
the existing RPM repository workflow; later BINs update the URL and SHA pin to
consume that published package. The service repository specifies the required
Go toolchain and RPM build tools.

Adding or reconnecting a supported Host uses the existing `zstack_repo` selection
(`false` retains the Host's enabled repositories) and downloads the exact declared
package into a fresh root-private system temporary directory. The existing
`skip_packages` setting can exclude `zstack-zram`. The Ant build selects its Go
compiler through `zstackzram.go`; the metadata and staging helpers run with
`/bin/python` and support Python 2.7 and Python 3. Download and byte verification
complete before the protected installer may exit the old controller. Same-version
reconnects still verify the package and actual running process. Missing packages
or failed verification warn without falling back to a WAR-carried RPM.
The installer then uses the system package manager. Existing configuration and
control state are preserved. A running service that cannot be safely replaced
is reported as requiring maintenance; reconnect does not force it to stop.
The installer upgrades only a service previously installed from the product
RPM. An unmanaged systemd unit override or drop-in stops the operation before
the package or running controller is changed and must be resolved explicitly.
The existing installer and Host control locks continue to cover stop/install/start;
the worker journals, pool, Unknown operations, and restart-intent receipt are not
stored in the download directory and are not removed with temporary materials.

KSM uses the distribution-provided `ksm` and `ksmtuned` services. The existing
Host deployment and Agent configuration paths manage their settings and
verify the native readback. Python Agent source packages continue to use
the standard sdist build.

The service RPM contains no kernel or kernel module. On Alinux4, the Host's
exact kernel profile selects the driver RPM from the configured ZStack
repository. Disk files and the loaded module are checked separately; an old
module already in use is not forcibly unloaded. Unsupported Hosts retain
their capability and maintenance status through the Agent APIs.
