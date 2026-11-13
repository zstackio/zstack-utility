_disk_xml_extensions = {}


def register_extension(extension_name, modify_disk_xml):
    registered_extension = _disk_xml_extensions.get(extension_name)
    if registered_extension is not None and registered_extension is not modify_disk_xml:
        raise ValueError('disk XML extension is already registered: %s' % extension_name)
    _disk_xml_extensions[extension_name] = modify_disk_xml


def apply_extensions(disk_xml, volume, source_type):
    if not _disk_xml_extensions:
        raise RuntimeError('disk XML extensions are not configured')
    # Inspect every disk, including backing layers not described by the volume TO flags.
    for modify_disk_xml in _disk_xml_extensions.values():
        modify_disk_xml(disk_xml, volume, source_type)
    return disk_xml
