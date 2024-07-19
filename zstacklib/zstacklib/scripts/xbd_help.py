class Rados:
    """
    This class corresponds to xstor storage.

    Methods
    -------
    __init__(self, *args, **kwargs):
        Parameters:
        - clustername (str): The name of the cluster.
        - conffile (str): The path to the configuration file.

    shutdown(self):
        Closes the Rados connection.

    conf_read_file(self, path: Optional[str] = None):
        Reads the configuration file.
        Parameters:
        - path (str): The path to the configuration file.

    conf_get(self, option: str) -> Optional[str]:
        Gets the value of the specified configuration option.
        Parameters:
        - option (str): The option to read.
        Returns:
        - str: The value of the option or None.

    connect(self, timeout: int = 0):
        Connects to Rados.
        Parameters:
        - timeout (int): Has no effect and does not need to be specified.

    open_ioctx(self, ioctx_name: str) -> Ioctx:
        Opens an Ioctx (I/O context) in the specified pool.
        Parameters:
        - ioctx_name (str): The name of the storage pool.
        Returns:
        - Ioctx: A Rados Ioctx object.
    """

class Image:
    """
    This class corresponds to an RBD volume.

    Methods
    -------
    __init__(self, ioctx, name=None, snapshot=None, read_only=False, image_id=None):
        Parameters:
        - ioctx: The Ioctx returned by `open_ioctx`, specifying the pool to use.
        - name (str): The name of the volume.
        - snapshot (str): The name of the snapshot.
        - read_only (bool): Whether the image is read-only.
        - image_id (str): The image ID.

    close(self):
        Closes the RBD volume.

    resize(self, size, allow_shrink=True):
        Resizes the volume.
        Parameters:
        - size (int): The new size of the volume.
        - allow_shrink (bool): Whether shrinking is allowed.

    stat(self):
        Gets the status of the volume.
        Returns:
        - dict:
            - size (int): The size of the volume.
            - obj_size (int): The size of the objects.
            - num_objs (int): The number of objects.
            - order (int)
            - block_name_prefix (str): The block object name prefix.
            - parent_pool (int): Deprecated.
            - parent_name (str): Deprecated.

    size(self) -> int:
        Gets the size of the volume.
        Returns:
        - int: The total size of the volume in bytes.

    features(self) -> int:
        Gets the features bitmask of the image.
        Returns:
        - int: The features bitmask of the image.

    flags(self) -> int:
        Gets the flags bitmask of the image.
        Returns:
        - int: The flags bitmask of the image.

    list_snaps(self):
        Lists the snapshots.
        Returns:
        - SnapIterator: The snapshot iterator.

    create_snap(self, snap_name, flags=0):
        Creates a snapshot.
        Parameters:
        - snap_name (str): The name of the snapshot to create.
        - flags (int): Create snapshot flags.

    remove_snap(self, snap_name):
        Removes a snapshot.
        Parameters:
        - snap_name (str): The name of the snapshot to remove.

    rollback_to_snap(self, name):
        Rolls back to a snapshot.
        Parameters:
        - name (str): The name of the snapshot to roll back to.

    aio_read(self, offset, length, oncomplete):
        Asynchronous read interface.
        Parameters:
        - offset (int): The starting position to read from.
        - length (int): The length of data to read.
        - oncomplete: The callback function upon completion.

    aio_write(self, data, offset, oncomplete):
        Asynchronous write interface.
        Parameters:
        - data (bytes): The data to write.
        - offset (int): The starting position to write to.
        - oncomplete: The callback function upon completion.

    read(self, offset, length):
        Synchronous read.
        Parameters:
        - offset (int): The starting position to read from.
        - length (int): The length of data to read.

    write(self, data, offset):
        Synchronous write.
        Parameters:
        - data (bytes): The data to write.
        - offset (int): The starting position to write to.

    discard(self, offset, length):
        Discards data.
        Parameters:
        - offset (int): The starting position to discard data from.
        - length (int): The length of data to discard.

    flush(self):
        Flushes the volume.

    write_zeroes(self, offset, length, zero_flags=0):
        Writes zeroes to the volume.
        Parameters:
        - offset (int): The starting position to write zeroes.
        - length (int): The length of data to write zeroes.
        - zero_flags: Has no effect.

    invalidate_cache(self):
        Drops any cached data for the image.

    aio_discard(self, offset, length, oncomplete):
        Asynchronous discard.
        Parameters:
        - offset (int)
        - length (int)
        - oncomplete: The callback function upon completion.

    aio_write_zeroes(self, offset, length, oncomplete, zero_flags=0):
        Asynchronous write zeroes.
        Parameters:
        - offset (int): The starting position to write zeroes.
        - length (int): The length of data to write zeroes.
        - oncomplete: The callback function upon completion.
        - zero_flags: Has no effect.

    aio_flush(self, oncomplete):
        Asynchronously waits until all writes are fully flushed if caching is enabled.
        Parameters:
        - oncomplete: The callback function upon completion.
    """

class SnapIterator:
    """
    This class corresponds to a snapshot iterator.

    Methods
    -------
    __init__(self, Image image):
        Parameters:
        - image: The corresponding Image class.
    """
