# Memory optimization deployment

The standard `zstackbuild` Ant build compiles the adjacent `zstack-zram`
checkout into an RPM and places the package, build manifest, runtime inventory
and installer in the WAR's KVM Agent materials. Set `zstackzram.checkout` to
use a different checkout. The service repository specifies the required Go
toolchain and RPM build tools.

The RPM Version follows `product.version`, including the standard `build.num`
when supplied. RPM Release defaults to `1`; `zstackzram.rpmRelease` can select
a higher release for a package rebuild of the same product version. Git branch
names remain source selectors and are not used as RPM Release values.

Adding or reconnecting a supported Host uses `kvm.py` to verify the package and
install it through the system package manager. Existing configuration and
control state are preserved. A running service that cannot be safely replaced
is reported as requiring maintenance; reconnect does not force it to stop.
The installer upgrades only a service previously installed from the product
RPM. An unmanaged systemd unit override or drop-in stops the operation before
the package or running controller is changed and must be resolved explicitly.

KSM scripts, configuration, systemd unit and tmpfiles configuration are
distributed by the existing Ansible file deployment. Python Agent source
packages continue to use the standard sdist build.

The service RPM contains no kernel or kernel module. On Alinux4, the Host's
exact kernel profile selects the driver RPM from the configured ZStack
repository. Disk files and the loaded module are checked separately; an old
module already in use is not forcibly unloaded. Unsupported Hosts retain
their capability and maintenance status through the Agent APIs.
