import ipaddress
import os
import stat
import tempfile
from urllib.parse import urlsplit, urlunsplit

import yaml


def _database_url(url, vip):
    try:
        address = str(ipaddress.ip_address(vip.strip('[]')))
        if not isinstance(url, str) or not url.startswith('jdbc:'):
            raise ValueError()
        parsed = urlsplit(url[5:])
        if (parsed.scheme not in ('mysql', 'mariadb') or not parsed.hostname
                or ',' in parsed.netloc or parsed.username is not None or not parsed.path.strip('/')):
            raise ValueError()
        host = '[%s]' % address if ':' in address else address
        authority = '%s:%s' % (host, parsed.port or 3306)
        return 'jdbc:' + urlunsplit((parsed.scheme, authority, parsed.path, parsed.query, parsed.fragment))
    except (ValueError, AttributeError):
        raise ValueError('Morph HA requires a database VIP and a single MySQL/MariaDB JDBC endpoint')


def configure_ha_database(application_path, region_path, vip):
    try:
        with open(application_path) as stream:
            application = yaml.safe_load(stream)
        with open(region_path) as stream:
            region = yaml.safe_load(stream)
    except yaml.YAMLError:
        raise ValueError('Invalid Morph YAML configuration')
    try:
        spring = region.setdefault('spring', {})
        datasource = spring.setdefault('datasource', {})
        original_url = datasource.get('url') or application['spring']['datasource']['url']
        url = _database_url(original_url, vip)
        changed = datasource.get('url') != url
        datasource['url'] = url
        flyway_url = spring.get('flyway', {}).get('url') or application['spring'].get('flyway', {}).get('url')
        if flyway_url:
            flyway = spring.setdefault('flyway', {})
            url = _database_url(flyway_url, vip)
            changed = changed or flyway.get('url') != url
            flyway['url'] = url
    except (KeyError, TypeError, AttributeError):
        raise ValueError('Invalid Morph datasource or region configuration')
    if not changed:
        return False

    metadata = os.stat(region_path)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', prefix='.morph-config-',
                                         dir=os.path.dirname(region_path), delete=False) as stream:
            temporary_path = stream.name
            yaml.safe_dump(region, stream, default_flow_style=False, sort_keys=False)
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
        os.replace(temporary_path, region_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
    return True
