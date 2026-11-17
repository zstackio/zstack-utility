import json
import os

from zstacklib.utils.sansec_utils import ValidationError


def read_config(path):
    try:
        with open(path) as source:
            config = json.load(source)
    except UnicodeError as error:
        raise ValidationError('Sansec configuration must be valid UTF-8') from error
    if not isinstance(config, dict) or not isinstance(config.get('devices'), dict):
        raise ValidationError('Sansec configuration requires a devices map')
    if not isinstance(config.get('libraryPath'), str) or not os.path.isabs(config['libraryPath']):
        raise ValidationError('Sansec SDK libraryPath must be absolute')
    timeout = config.get('timeout')
    if type(timeout) is not int or not 1 <= timeout <= 30:
        raise ValidationError('Sansec SDK timeout must be between 1 and 30 seconds')
    serials = []
    for profile in config['devices'].values():
        if not isinstance(profile, dict):
            raise ValidationError('Sansec device profile must be an object')
        for key in ('serialNumber', 'firmwareVersion', 'libraryVersion', 'driverVersion'):
            if not isinstance(profile.get(key), str) or not profile[key].strip():
                raise ValidationError('Sansec profile requires %s' % key)
        if profile.get('driverVersionSource', 'version') not in ('version', 'srcversion'):
            raise ValidationError('Sansec driverVersionSource must be version or srcversion')
        serials.append(profile['serialNumber'])
        if type(profile.get('compatible')) is not bool:
            raise ValidationError('Sansec compatibility must be explicitly configured')
        for key in ('pollInterval', 'validityPeriod', 'recoveryInterval'):
            if type(profile.get(key)) is not int or profile[key] < 0:
                raise ValidationError('Invalid Sansec timing profile')
        if profile['pollInterval'] <= timeout or profile['validityPeriod'] <= profile['pollInterval']:
            raise ValidationError('Sansec requires timeout < pollInterval < validityPeriod')
    if len(serials) != len(set(serials)):
        raise ValidationError('Sansec serial-to-PCI mapping must be unique; PF selection is not documented')
    return config
