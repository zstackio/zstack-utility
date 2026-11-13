# storage_type -> driver_name -> (should_use_driver, driver_class).
_driver_registrations = {}


def register_driver(storage_type, driver_name, should_use_driver, driver_class):
    """should_use_driver(cmd) selects driver_class when True; invalid requests must raise."""
    storage_drivers = _driver_registrations.setdefault(storage_type, {})
    registration = (should_use_driver, driver_class)
    if driver_name in storage_drivers and storage_drivers[driver_name] != registration:
        raise ValueError('volume driver already registered: %s/%s' % (storage_type, driver_name))
    storage_drivers[driver_name] = registration


def get_driver(storage_type, cmd, default_driver_class):
    # Missing plugin configuration must not silently select the Plain driver.
    if not _driver_registrations.get(storage_type):
        raise RuntimeError('volume drivers are not configured: %s' % storage_type)
    # Propagate selection errors; falling back would hide a malformed request.
    matching_drivers = [(driver_name, driver_class) for driver_name, (should_use_driver, driver_class)
                        in _driver_registrations[storage_type].items() if should_use_driver(cmd)]
    # Drivers are mutually exclusive; registration order must not choose a winner.
    if len(matching_drivers) > 1:
        raise ValueError('multiple volume drivers match %s: %s' %
                         (storage_type, ', '.join(driver_name for driver_name, _ in matching_drivers)))
    # The storage adapter supplies its Plain driver as the explicit default.
    driver_class = matching_drivers[0][1] if matching_drivers else default_driver_class
    return driver_class(cmd)
