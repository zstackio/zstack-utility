"""
VM Local Volume Cache Plugin
Manages local cache pool and cache volumes for VMs on compute nodes
"""
import functools
import json
import os
import traceback
from typing import Any, Callable, TypeVar
from kvmagent import kvmagent
from kvmagent.plugins.volume_cache.command_wrapper.lvm import LvmCommandWrapper
from kvmagent.plugins.volume_cache.command_wrapper.filesystem import FileSystemCommandWrapper
from kvmagent.plugins.volume_cache.command_wrapper.lvm import LvmObjectType, LVType, PVInfoFields, VGInfoFields, LVInfoFields
from kvmagent.plugins.volume_cache.command_wrapper.filesystem import FileSystemType, FileSystemInfoFields, MountPointInfoFields
from kvmagent.plugins.volume_cache.command_wrapper.qemu_img import BackingVolume, BackingVolumeDeviceType, QemuImgCommandWrapper, supported_backing_volume_classes
from kvmagent.plugins.volume_cache.command_wrapper.exceptions import (
    CacheNotInstantiatedError,
    CacheOperationError,
    PoolNotFoundError,
    PoolNotInitializedError,
    PoolOperationError,
    UnsupportedDeviceTypeError,
    VolumeValidationError,
)
from kvmagent.plugins.volume_cache.objects import (
    CacheCapacityInfo,
    PVInfo,
    PoolHealthInfo,
    Qcow2FileInfo,
    VGInfo,
    LVInfo,
    FileSystemInfo,
    PoolCapacityInfo,
    MountPointInfo
)
from kvmagent.plugins.volume_cache.schemas import (
    AllocateCacheCmd,
    BaseCmd,
    CacheBaseCmd,
    CacheRsp,
    CheckPoolCmd,
    ConnectPoolCmd,
    ConnectPoolRsp,
    DeleteCacheCmd,
    DeleteCacheRsp,
    DeletePoolCmd,
    DeletePoolRsp,
    ExtendPoolCmd,
    ExtendPoolRsp,
    FlushCacheCmd,
    GcPoolCmd,
    GcPoolRsp,
    GetCacheCapacityCmd,
    GetPoolCapacityCmd,
    InitPoolCmd,
    InitPoolRsp,
    PoolBaseCmd,
    PoolCapacityRsp,
    PoolHealthRsp,
    PoolRsp,
    VolumeCacheBaseCommand,
    VolumeCacheBaseResponse,
    VolumeTO,
)
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import plugin
from zstacklib.utils.rollback import rollback, rollbackable

logger = log.get_logger(__name__)


def ensure_pool_initialized(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        self = args[0] # type: PoolProcessor
        if not self.is_initialized:
            raise PoolNotInitializedError("Pool %s is not initialized" % self.pool_uuid)
        return func(*args, **kwargs)
    return wrap

class PoolProcessor(object):
    DEFAULT_VG_METADATA_SIZE = "512M"  # type: str
    DEFAULT_LV_TYPE = LVType.LINEAR
    DEFAULT_LV_STRIPES = 1
    DEFAULT_LV_STRIPESIZE = "64K"
    DEFAULT_FS_TYPE = FileSystemType.XFS

    VM_LOCAL_VOLUME_CACHE_POOL_LVM_TAG_PREFIX = "zs::volume_cache_pool"
    VM_LOCAL_VOLUME_CACHE_POOL_MANAGED_LVM_TAG = "%s::%s" % (VM_LOCAL_VOLUME_CACHE_POOL_LVM_TAG_PREFIX, "managed")
    VM_LOCAL_VOLUME_CACHE_POOL_UUID_LVM_TAG_PREFIX = "%s::%s" % (VM_LOCAL_VOLUME_CACHE_POOL_LVM_TAG_PREFIX, "pool_uuid")
    VM_LOCAL_VOLUME_CACHE_POOL_MOUNT_PATH_LVM_TAG_PREFIX = "%s::%s" % (VM_LOCAL_VOLUME_CACHE_POOL_LVM_TAG_PREFIX, "mount_path")

    # Legacy (pre-rename) LVM tag prefix constants. Kept for read/scan
    # compatibility so that hosts upgraded from older releases -- where VG/PV/LV
    # metadata is still tagged with the old ``zs::vm_local_volume_cache_pool*``
    # prefix -- remain discoverable. All write paths (create/add-tag/remove-tag)
    # must continue to use the canonical new prefix above.
    LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_LVM_TAG_PREFIX = "zs::vm_local_volume_cache_pool"
    LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_MANAGED_LVM_TAG = "%s::%s" % (LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_LVM_TAG_PREFIX, "managed")
    LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_UUID_LVM_TAG_PREFIX = "%s::%s" % (LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_LVM_TAG_PREFIX, "pool_uuid")
    LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_MOUNT_PATH_LVM_TAG_PREFIX = "%s::%s" % (LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_LVM_TAG_PREFIX, "mount_path")

    VM_LOCAL_VOLUME_CACHE_POOL_LVM_NAME_PREFIX = "vlvc_pool"
    HEARTBEAT_FILE_RELATIVE_PATH = ".heartbeat"

    pool_uuid = None  # type: str
    mount_path = None  # type: str

    pvs = None  # type: list[PVInfo] | None
    vg = None  # type: VGInfo | None
    lv = None  # type: LVInfo | None
    fs = None  # type: FileSystemInfo | None
    mount_point = None  # type: MountPointInfo | None

    @property
    def pool_tag(self):
        # type: () -> str
        return "%s::%s" % (self.VM_LOCAL_VOLUME_CACHE_POOL_UUID_LVM_TAG_PREFIX, self.pool_uuid)

    @property
    def legacy_pool_tag(self):
        # type: () -> str
        """ Legacy pool UUID tag (pre-rename). Used for read/scan only; never written. """
        return "%s::%s" % (self.LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_UUID_LVM_TAG_PREFIX, self.pool_uuid)

    @property
    def mount_path_tag(self):
        # type: () -> str
        return "%s::%s" % (self.VM_LOCAL_VOLUME_CACHE_POOL_MOUNT_PATH_LVM_TAG_PREFIX, self.mount_path)

    @property
    def vg_name(self):
        return "%s_vg_%s" % (self.VM_LOCAL_VOLUME_CACHE_POOL_LVM_NAME_PREFIX, self.pool_uuid)

    @property
    def lv_name(self):
        return "%s_lv_%s" % (self.VM_LOCAL_VOLUME_CACHE_POOL_LVM_NAME_PREFIX, self.pool_uuid)

    @property
    def vg_metadata_size(self):
        # type: () -> str
        """ Get VG metadata size used by this pool """
        if not self.vg:
            return self.DEFAULT_VG_METADATA_SIZE
        return self.vg[VGInfoFields.VG_MDA_SIZE]

    @property
    def heartbeat_file_path(self):
        # type: () -> str
        """ Get heartbeat file path on the mounted filesystem """
        return os.path.join(self.mount_path, self.HEARTBEAT_FILE_RELATIVE_PATH)

    @property
    def is_initialized(self):
        # type: () -> bool
        """ Check if pool is already initialized on host """
        return all([self.pvs, self.vg, self.lv, self.fs, self.mount_point])

    def __init__(self, pool_uuid, mount_path):
        # type: (str, str) -> None
        self.pool_uuid = pool_uuid
        self.mount_path = mount_path

    @classmethod
    def discover_local_pool(cls, pool_uuid):
        # type: (str) -> PoolProcessor|None
        LvmCommandWrapper.rescan_pv()
        LvmCommandWrapper.rescan_vg()
        LvmCommandWrapper.rescan_lv()

        lv_objects_by_uuid = {}
        for pool_uuid_tag in (cls.VM_LOCAL_VOLUME_CACHE_POOL_UUID_LVM_TAG_PREFIX + "::" + pool_uuid,
                              cls.LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_UUID_LVM_TAG_PREFIX + "::" + pool_uuid):
            found = LvmCommandWrapper.get_lvm_objects_by_tag(
                LvmObjectType.LV, pool_uuid_tag,
                [LVInfoFields.LV_UUID, LVInfoFields.LV_NAME, LVInfoFields.LV_TAGS, VGInfoFields.VG_NAME])
            if not found:
                continue
            for lv_object in found:
                if not cls._is_managed_lv_object(lv_object):
                    continue
                lv_objects_by_uuid.setdefault(lv_object[LVInfoFields.LV_UUID.value], lv_object)

        if not lv_objects_by_uuid:
            return None
        if len(lv_objects_by_uuid) > 1:
            raise PoolOperationError("Multiple local volume cache LVs found for pool UUID %s" % pool_uuid)

        lv_object = list(lv_objects_by_uuid.values())[0]
        mount_path_tag = cls._get_mount_path_tag_from_lv_object(lv_object)
        if not mount_path_tag:
            raise PoolOperationError("LV %s in VG %s is tagged for pool UUID %s but missing mount path tag" % (
                lv_object[LVInfoFields.LV_NAME.value], lv_object[VGInfoFields.VG_NAME.value], pool_uuid))

        return cls(pool_uuid, mount_path_tag.split("::", 3)[-1])

    @classmethod
    def _get_mount_path_tag_from_lv_object(cls, lv_object):
        # type: (dict[str, Any]) -> str|None
        lv_tags = lv_object[LVInfoFields.LV_TAGS.value].split(",")
        mount_path_prefixes = (cls.VM_LOCAL_VOLUME_CACHE_POOL_MOUNT_PATH_LVM_TAG_PREFIX,
                               cls.LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_MOUNT_PATH_LVM_TAG_PREFIX)
        return next((tag for prefix in mount_path_prefixes for tag in lv_tags if tag.startswith(prefix + "::")), None)

    @classmethod
    def _is_managed_lv_object(cls, lv_object):
        # type: (dict[str, Any]) -> bool
        lv_tags = lv_object[LVInfoFields.LV_TAGS.value].split(",")
        managed_tags = (cls.VM_LOCAL_VOLUME_CACHE_POOL_MANAGED_LVM_TAG,
                        cls.LEGACY_VM_LOCAL_VOLUME_CACHE_POOL_MANAGED_LVM_TAG)
        return any(tag in lv_tags for tag in managed_tags)

    def __create_pvs(self, device_paths, metadata_size=None, force=False):
        # type: (list[str], str|None, bool) -> list[PVInfo]
        """ Create physical volumes on given device paths and return their PVInfo"""
        _metadata_size = metadata_size if metadata_size else self.DEFAULT_VG_METADATA_SIZE
        created_pvs = []
        for device_path in device_paths:
            FileSystemCommandWrapper.wipe_block_device_superblock(device_path,
                                                                  force=force)
            pv_uuid = LvmCommandWrapper.create_pv(device_path,
                                                  metadata_size=_metadata_size,
                                                  force=force)
            logger.info("Created PV %s on device %s" % (pv_uuid, device_path))
            created_pvs.append(PVInfo(pv_uuid))

        return created_pvs

    def __remove_pvs(self, device_paths, force=False, is_exception=False):
        # type: (list[str], bool, bool) -> None
        """ Remove physical volumes used by this pool """
        for device_path in device_paths:
            try:
                LvmCommandWrapper.remove_pv(
                    device_path, force=force)
                logger.info("Removed PV %s" % device_path)
            except Exception as e:
                logger.error("Failed to remove PV %s : %s" % (device_path, str(e)))
                logger.error(traceback.format_exc())
                if is_exception:
                    raise PoolOperationError("Failed to remove PV %s : %s" % (device_path, str(e)))

    def __create_vg(self, pvs, metadata_size=None):
        # type: (list[PVInfo], str|None) -> VGInfo
        """ Create volume group with given physical volumes and return VGInfo"""
        if not pvs:
            raise Exception("No physical volumes to create VG")
        pv_names = [pv[PVInfoFields.PV_NAME] for pv in pvs]  # type: list[str]
        _metadata_size = metadata_size if metadata_size else self.DEFAULT_VG_METADATA_SIZE
        vg_uuid = LvmCommandWrapper.create_vg(vg_name=self.vg_name,
                                              pv_names=pv_names,
                                              tags=[self.pool_tag, self.mount_path_tag, self.VM_LOCAL_VOLUME_CACHE_POOL_MANAGED_LVM_TAG],
                                              metadata_size=_metadata_size)
        for pv_name in pv_names:
            LvmCommandWrapper.tag_lvm_object(
                LvmObjectType.PV, pv_name, [self.pool_tag, self.mount_path_tag, self.VM_LOCAL_VOLUME_CACHE_POOL_MANAGED_LVM_TAG])
        return VGInfo(vg_uuid)

    def __extend_vg(self, vg, pvs):
        # type: (VGInfo, list[PVInfo]) -> VGInfo
        """ Extend volume group with given physical volumes and return updated VGInfo"""
        if not pvs:
            raise Exception("No physical volumes to extend VG")
        pv_names = [pv[PVInfoFields.PV_NAME] for pv in pvs]  # type: list[str]
        LvmCommandWrapper.extend_vg(
            vg_name=vg[VGInfoFields.VG_NAME], pv_names=pv_names, metadata_size=self.vg_metadata_size)  # type: ignore
        for pv in pvs:
            LvmCommandWrapper.tag_lvm_object(
                LvmObjectType.PV, pv[PVInfoFields.PV_NAME], [self.pool_tag, self.mount_path_tag, self.VM_LOCAL_VOLUME_CACHE_POOL_MANAGED_LVM_TAG])
            pv.reload()
        vg.reload()
        return vg

    def __remove_vg(self, force=False, is_exception=False):
        # type: (bool, bool) -> None
        """ Remove volume group used by this pool """
        try:
            LvmCommandWrapper.remove_vg(self.vg_name, force=force)
            logger.info("Removed VG %s" % self.vg_name)
        except Exception as e:
            logger.error("Failed to remove VG %s: %s" % (self.vg_name, str(e)))
            logger.error(traceback.format_exc())
            if is_exception:
                raise PoolOperationError("Failed to remove VG %s: %s" % (self.vg_name, str(e)))

    def __create_lv(self, vg, lv_type=None, lv_stripes=None, lv_stripesize=None):
        # type: (VGInfo, LVType|None, int|None, str|None) -> LVInfo
        """ Create cache logical volume in the volume group and return LVInfo"""
        if not vg:
            raise Exception("Volume group is not created")

        _lv_type = lv_type if lv_type else self.DEFAULT_LV_TYPE
        if _lv_type in [LVType.STRIPED, LVType.RAID0]:
            stripes = str(lv_stripes) if lv_stripes else str(
                self.DEFAULT_LV_STRIPES)
            stripesize = lv_stripesize if lv_stripesize else self.DEFAULT_LV_STRIPESIZE
        else:
            logger.info(
                "LV type is %s, ignoring stripes and stripesize parameters" % _lv_type.value)
            stripes = None
            stripesize = None

        lv_uuid = LvmCommandWrapper.create_lv(lv_name=self.lv_name,
                                              vg_name=self.vg_name,
                                              type=_lv_type,
                                              stripes=stripes,
                                              stripesize=stripesize,
                                              extents="100%FREE",
                                              tags=[self.pool_tag, self.mount_path_tag, self.VM_LOCAL_VOLUME_CACHE_POOL_MANAGED_LVM_TAG])
        LvmCommandWrapper.active_lv(lv_name=self.lv_name, vg_name=self.vg_name)
        return LVInfo(lv_uuid)

    def __extend_lv(self, lv, size=None, extents=None):
        # type: (LVInfo, str|None, str|None) -> LVInfo
        """ Extend cache logical volume with given size or extents and return updated LVInfo"""
        if not lv:
            raise Exception("Logical volume is not created")
        if not size and not extents:
            raise Exception(
                "Either size or extents must be specified to extend LV")
        LvmCommandWrapper.extend_lv(
            lv_name=lv[LVInfoFields.LV_NAME], vg_name=self.vg_name, size=size, extents=extents)  # type: ignore
        lv.reload()
        return lv

    def __extend_lv_full_size(self, lv):
        # type: (LVInfo) -> LVInfo
        """ Extend cache logical volume to full size of the volume group and return updated LVInfo"""
        if not lv:
            raise Exception("Logical volume is not created")
        self.__extend_lv(lv, extents="+100%FREE")
        lv.reload()
        return lv

    def __remove_lv(self, force=False, is_exception=False):
        # type: (bool, bool) -> None
        """ Remove logical volume used by this pool """
        try:
            LvmCommandWrapper.remove_lv(lv_name=self.lv_name,
                                        vg_name=self.vg_name,
                                        force=force)
            logger.info("Removed LV %s" % self.lv_name)
        except Exception as e:
            logger.error("Failed to remove LV %s: %s" % (self.lv_name, str(e)))
            logger.error(traceback.format_exc())
            if is_exception:
                raise PoolOperationError("Failed to remove LV %s: %s" % (self.lv_name, str(e)))

    def __make_filesystem(self, lv, fs_type=None, force=False):
        # type: (LVInfo, FileSystemType|None, bool) -> FileSystemInfo
        _fs_type = fs_type if fs_type else self.DEFAULT_FS_TYPE
        if not lv:
            raise Exception("Logical volume is not created")
        _device_path = lv[LVInfoFields.LV_PATH]  # type: str
        device_path = FileSystemCommandWrapper.create_filesystem(
            _device_path, _fs_type, force=force)
        return FileSystemInfo(device_path)

    def __extend_filesystem(self, fs):
        # type: (FileSystemInfo) -> FileSystemInfo
        """ Extend filesystem to occupy the whole logical volume and return updated FileSystemInfo"""
        if not fs:
            raise Exception("Filesystem is not created")
        FileSystemCommandWrapper.extend_filesystem(fs.block_device)
        fs.reload()
        return fs

    def __wipe_filesystem(self, force=False, is_exception=False):
        # type: (bool, bool) -> None
        assert self.lv and self.lv[LVInfoFields.LV_PATH], "Logical volume is not available to wipe filesystem signatures"
        block_device = self.lv[LVInfoFields.LV_PATH]
        try:
            FileSystemCommandWrapper.wipe_block_device_superblock(
                block_device, force=force)
            logger.info("Wiped filesystem signatures on device %s" % block_device)
        except Exception as e:
            logger.error("Failed to wipe filesystem signatures on device %s: %s"
                         % (block_device, str(e)))
            logger.error(traceback.format_exc())
            if is_exception:
                raise PoolOperationError("Failed to wipe filesystem signatures on device %s: %s"
                                % (block_device, str(e)))

    def __mount_filesystem(self, fs, mount_path, force=False):
        # type: (FileSystemInfo, str, bool) -> MountPointInfo
        if not fs:
            raise Exception("Filesystem is not created")
        if not FileSystemCommandWrapper.get_mount_point(fs[FileSystemInfoFields.UUID], mount_path):
            FileSystemCommandWrapper.mount_filesystem(
                fs[FileSystemInfoFields.UUID], mount_path, force=force)
        return MountPointInfo(fs[FileSystemInfoFields.UUID], mount_path)

    def __umount_filesystem(self, mount_path, force=False, is_exception=False):
        # type: (str, bool, bool) -> None
        try:
            FileSystemCommandWrapper.umount_filesystem(
                mount_path, force=force)
            logger.info("Unmounted filesystem from mount path %s" % mount_path)
        except Exception as e:
            logger.error("Failed to unmount filesystem from mount path %s: %s" % (mount_path, str(e)))
            logger.error(traceback.format_exc())
            if is_exception:
                raise PoolOperationError("Failed to unmount filesystem from mount path %s: %s" % (mount_path, str(e)))

    def __load_pvs(self):
        # type: () -> list[PVInfo]
        """ Load PVInfo of physical volumes used by this pool based on the PV UUIDs tagged with pool UUID """
        LvmCommandWrapper.rescan_pv()
        pvs = self.__get_lvm_objects_by_pool_tag(
            LvmObjectType.PV, [PVInfoFields.PV_UUID])
        if not pvs:
            raise Exception("No PVs found for pool %s" % self.pool_uuid)
        # type: ignore
        return [PVInfo(pv[PVInfoFields.PV_UUID.value]) for pv in pvs]

    def __load_vg(self):
        # type: () -> VGInfo
        """ Load VGInfo of volume group used by this pool based on the VG UUID tagged with pool UUID """
        LvmCommandWrapper.rescan_vg()
        vgs = self.__get_lvm_objects_by_pool_tag(
            LvmObjectType.VG, [VGInfoFields.VG_UUID])
        if not vgs:
            raise Exception("No VG found for pool %s" % self.pool_uuid)
        if len(vgs) > 1:
            raise Exception("Multiple VGs found for pool %s: %s" % (
                self.pool_uuid, ','.join([vg[VGInfoFields.VG_UUID.value] for vg in vgs])))
        return VGInfo(vgs.pop()[VGInfoFields.VG_UUID.value])

    def __load_lv(self):
        # type: () -> LVInfo
        """ Load LVInfo of logical volume used by this pool based on the LV UUID tagged with pool UUID """
        LvmCommandWrapper.rescan_lv()
        lvs = self.__get_lvm_objects_by_pool_tag(
            LvmObjectType.LV,
            [LVInfoFields.LV_UUID, LVInfoFields.LV_NAME, LVInfoFields.LV_ACTIVE, VGInfoFields.VG_NAME])
        if not lvs:
            raise Exception("No LV found for pool %s" % self.pool_uuid)
        if len(lvs) > 1:
            raise Exception("Multiple LVs found for pool %s: %s" % (
                self.pool_uuid, ','.join([lv[LVInfoFields.LV_UUID.value] for lv in lvs])))
        lv = lvs.pop()
        if lv[LVInfoFields.LV_ACTIVE.value] != "active":
            LvmCommandWrapper.active_lv(
                lv_name=lv[LVInfoFields.LV_NAME.value], vg_name=lv[VGInfoFields.VG_NAME.value])
        return LVInfo(lv[LVInfoFields.LV_UUID.value])

    def __get_lvm_objects_by_pool_tag(self, object_type, fields):
        # type: (LvmObjectType, list) -> list[dict[str, str]]
        """ Read-side lookup that matches either the new or the legacy pool-uuid
        tag for this pool's UUID, de-duplicating by the first requested field. """
        primary_field = fields[0].value
        merged = {}
        for tag in (self.pool_tag, self.legacy_pool_tag):
            found = LvmCommandWrapper.get_lvm_objects_by_tag(object_type, tag, fields)
            if not found:
                continue
            for obj in found:
                key = obj.get(primary_field)
                if key is None:
                    continue
                merged.setdefault(key, obj)
        return list(merged.values())

    def __load_filesystem(self):
        # type: () -> FileSystemInfo
        """ Load FileSystemInfo of filesystem on cache logical volume based on the device path of the logical volume """
        if not self.lv or not self.lv[LVInfoFields.LV_PATH]:
            raise Exception("Logical volume is not loaded")
        filesystem = FileSystemCommandWrapper.get_filesystem_object(
            self.lv[LVInfoFields.LV_PATH])
        if not filesystem:
            raise Exception("No filesystem found on logical volume %s" %
                            self.lv[LVInfoFields.LV_PATH])
        return FileSystemInfo(self.lv[LVInfoFields.LV_PATH])

    def __load_mount_point(self):
        # type: () -> MountPointInfo
        """ Load MountPointInfo of mount point used by this pool based on the mount path tagged with pool UUID """
        if not self.fs or not self.fs[FileSystemInfoFields.UUID]:
            raise Exception("Filesystem is not loaded")
        self.__mount_filesystem(fs=self.fs, mount_path=self.mount_path)
        return MountPointInfo(self.fs[FileSystemInfoFields.UUID], self.mount_path)

    def __check_pvs(self):
        # type: () -> list[PVInfo] | None
        """ Check if physical volumes used by this pool are healthy"""
        unhealthy_pvs = []
        if not self.pvs:
            raise Exception("Physical volumes are not loaded")
        for pv in self.pvs:
            if not LvmCommandWrapper.check_pv(pv[PVInfoFields.PV_NAME]):
                unhealthy_pvs.append(pv)
        if unhealthy_pvs:
            logger.warning("Unhealthy PVs found for pool %s: %s"
                           % (self.pool_uuid, ','.join([pv[PVInfoFields.PV_NAME] for pv in unhealthy_pvs])))
            return unhealthy_pvs
        return None

    def __check_vg(self):
        # type: () -> VGInfo| None
        """ Check if volume group used by this pool is healthy"""
        if not self.vg:
            raise Exception("Volume group is not loaded")
        if not LvmCommandWrapper.check_vg(self.vg[VGInfoFields.VG_NAME]):
            logger.warning("Unhealthy VG found for pool %s: %s"
                           % (self.pool_uuid, self.vg[VGInfoFields.VG_NAME]))
            return self.vg

        return None

    def __check_lv(self):
        # type: () -> LVInfo | None
        """ Check if logical volume used by this pool is healthy"""
        if not self.lv:
            raise Exception("Logical volume is not loaded")
        if not LvmCommandWrapper.check_lv(self.lv[LVInfoFields.LV_NAME], self.vg_name):
            logger.warning("Unhealthy LV found for pool %s: %s"
                           % (self.pool_uuid, self.lv[LVInfoFields.LV_NAME]))
            return self.lv
        return None

    def __check_filesystem(self):
        # type: () -> MountPointInfo | None
        """ Check if filesystem on cache logical volume is healthy"""
        if not self.fs:
            raise Exception("Filesystem is not loaded")
        if not self.mount_point:
            raise Exception("Mount point is not loaded")

        if not FileSystemCommandWrapper.check_filesystem(self.mount_path,
                                                         self.heartbeat_file_path):
            logger.warning("Unhealthy filesystem found for pool %s on device %s"
                           % (self.pool_uuid, self.fs.block_device))
            return self.mount_point
        return None

    @rollback
    def init_pool(self, device_paths, metadata_size=None,
                  lv_type=None, lv_stripes=None, lv_stripesize=None,
                  fs_type=None, force=False):
        # type: (list[str], str|None, LVType|None, int|None, str|None, FileSystemType|None, bool) -> None
        """ Initialize cache pool with given mount point and physical volumes
        steps:
        1. Check if mount point is valid and not already used by existing pool
        2. Check if physical volumes are valid and not already used by existing pool
        3. Create LVM volume group with given physical volumes and tag with pool UUID
        4. Create cache logical volume in the volume group
        5. Format cache logical volume with appropriate filesystem
        """

        rollback_create_pvs = rollbackable(lambda: self.__remove_pvs(device_paths=device_paths, force=True, is_exception=False))
        rollback_create_vg = rollbackable(lambda: self.__remove_vg(force=True, is_exception=False))
        rollback_create_lv = rollbackable(lambda: self.__remove_lv(force=True, is_exception=False))
        rollback_make_fs = rollbackable(lambda: self.__wipe_filesystem(force=True, is_exception=False))
        rollback_mount_fs = rollbackable(lambda: self.__umount_filesystem(self.mount_path, force=True, is_exception=False))

        _metadata_size = metadata_size or self.DEFAULT_VG_METADATA_SIZE
        _lv_type = lv_type or self.DEFAULT_LV_TYPE
        _lv_stripes = lv_stripes or self.DEFAULT_LV_STRIPES
        _lv_stripesize = lv_stripesize or self.DEFAULT_LV_STRIPESIZE
        _fs_type = fs_type or self.DEFAULT_FS_TYPE

        rollback_create_pvs()
        pvs = self.__create_pvs(device_paths=device_paths,
                                metadata_size=_metadata_size,
                                force=force)
        
        rollback_create_vg()
        vg = self.__create_vg(pvs=pvs, metadata_size=_metadata_size)

        rollback_create_lv()
        lv = self.__create_lv(vg=vg, lv_type=_lv_type, lv_stripes=_lv_stripes,
                              lv_stripesize=_lv_stripesize)

        rollback_make_fs()
        fs = self.__make_filesystem(lv=lv, fs_type=_fs_type, force=force)

        rollback_mount_fs()
        self.__mount_filesystem(fs=fs, mount_path=self.mount_path, force=force)

        self.connect_pool()


    def connect_pool(self):
        # type: () -> None
        """ Connect to an existing pool on host with given mount path
        steps:
        1. Check if mount point is valid and used by a pool with matching UUID tag
        2. Load pool information based on the cache logical volume associated with the mount point
        3. If force is True, we will try to fix any inconsistency in pool resources (e.g. unmount stale filesystem, wipe stale filesystem signatures, etc.) to successfully connect to the pool; if force is False, we will raise exception if any inconsistency is detected
        """
        FileSystemCommandWrapper.partprobe()
        try:
            self.pvs = self.__load_pvs()
            self.vg = self.__load_vg()
            self.lv = self.__load_lv()
            self.fs = self.__load_filesystem()
            self.mount_point = self.__load_mount_point()
        except Exception as e:
            logger.error("Failed to connect pool %s on mount path %s: %s" % (
                self.pool_uuid, self.mount_path, str(e)))
            logger.error(traceback.format_exc())
            raise PoolOperationError("Failed to connect pool %s on mount path %s: %s" % (
                self.pool_uuid, self.mount_path, str(e)))

    @ensure_pool_initialized
    @rollback
    def extend_pool(self, additional_device_paths, force=False):
        # type: (list[str], bool) -> None
        """ Extend existing pool with additional physical volumes
        steps:
        1. Check if additional physical volumes are valid and not already used by existing pool
        2. Create physical volumes on the additional device paths
        3. Extend volume group with the new physical volumes
        """
        assert self.pvs and self.vg and self.lv and self.fs and self.mount_point
        rollback_create_pvs = rollbackable(lambda: self.__remove_pvs(
        device_paths=additional_device_paths, force=True, is_exception=False))
        rollback_create_pvs()
        additional_pvs = self.__create_pvs(device_paths=additional_device_paths,
                                            metadata_size=self.vg_metadata_size,
                                            force=force)
        

        self.__extend_vg(self.vg, additional_pvs)
        self.__extend_lv_full_size(self.lv)
        self.__extend_filesystem(self.fs)
        logger.info("Extended VG %s with additional PVs: %s"
                    % (self.vg[VGInfoFields.VG_NAME],
                        ",".join([pv[PVInfoFields.PV_NAME] for pv in additional_pvs])))

    @ensure_pool_initialized
    def delete_pool(self):
        # type: () -> None
        """ Delete cache pool and all its resources """
        assert self.mount_point and self.pvs
        try:
            # todo: clear all cache files in the filesystem before umount to avoid stale cache files after pool deletion
            self.__umount_filesystem(self.mount_path, force=True, is_exception=True)
            self.__wipe_filesystem(force=True, is_exception=True)
            self.__remove_lv(force=True, is_exception=True)
            self.__remove_vg(force=True, is_exception=True)
            self.__remove_pvs([pv[PVInfoFields.PV_NAME] for pv in self.pvs], force=True, is_exception=True)
        except Exception as e:
            logger.error("Failed to delete pool %s: %s" % (self.pool_uuid, str(e)))
            logger.error(traceback.format_exc())
            raise PoolOperationError("Failed to delete pool %s: %s" % (self.pool_uuid, str(e)))

    @ensure_pool_initialized
    def check_pool(self):
        """ Check health status of the pool resources and return a dict with status of each resource type (PV, VG, LV, filesystem) """
        assert self.pvs
        unhealthy_pvs = self.__check_pvs()
        unhealthy_vg = self.__check_vg()
        unhealthy_lv = self.__check_lv()
        unhealthy_filesystem = self.__check_filesystem()
        return PoolHealthInfo(
            pvs={pv:(pv not in unhealthy_pvs) if unhealthy_pvs else True for pv in self.pvs},
            vg=not unhealthy_vg,
            lv=not unhealthy_lv,
            filesystem=not unhealthy_filesystem
        )

    @ensure_pool_initialized
    def get_capacity(self):
        # type: () -> PoolCapacityInfo
        """ Get total capacity of the pool based on the size of the filesystem """
        assert self.mount_point
        self.mount_point.reload()
        cap = self.mount_point.capacity
        return cap

    @ensure_pool_initialized
    def gc_pool(self, volume_uuids):
        # type: (list[str]) -> list[str]
        """ Garbage collect unexpected files and directories in the pool mount point.

        Scans the mount point for all files and top-level directories, compares
        them against the expected cache files (derived from *volume_uuids*) and
        the heartbeat file, then removes anything unexpected.

        Args:
            volume_uuids: Volume UUIDs whose cache files should be kept.

        Returns:
            List of absolute paths that were successfully removed.
        """
        assert self.mount_point
        mount_path = self.mount_point[MountPointInfoFields.TARGET]

        # Build expected absolute paths for files
        expected_files = set()
        expected_files.add(os.path.join(mount_path, self.HEARTBEAT_FILE_RELATIVE_PATH))
        for vol_uuid in volume_uuids:
            cache_name = "%s_%s" % (CacheProcessor.CACHE_FILE_NAME_PREFIX, vol_uuid)
            expected_files.add(os.path.join(mount_path, cache_name))

        # Collect unexpected files using FileSystemCommandWrapper
        all_files = FileSystemCommandWrapper.get_all_files(mount_path)
        unexpected_files = [f for f in all_files if f not in expected_files]

        # Collect unexpected top-level directories (skip reserved ones)
        reserved_dirs = {"lost+found"}
        expected_dir_names = reserved_dirs
        unexpected_dirs = []
        for entry in os.listdir(mount_path):
            entry_path = os.path.join(mount_path, entry)
            if os.path.isdir(entry_path) and entry not in expected_dir_names:
                unexpected_dirs.append(entry_path)

        # Remove unexpected files first, then directories
        gc_files = []
        for path in unexpected_files:
            logger.info("GC pool %s: removing unexpected file %s" % (self.pool_uuid, path))
            if FileSystemCommandWrapper.remove_path(path, is_exception=False):
                gc_files.append(path)
            else:
                logger.warning("GC pool %s: failed to remove file %s" % (self.pool_uuid, path))

        for path in unexpected_dirs:
            logger.info("GC pool %s: removing unexpected directory %s" % (self.pool_uuid, path))
            if FileSystemCommandWrapper.remove_path(path, is_exception=False):
                gc_files.append(path)
            else:
                logger.warning("GC pool %s: failed to remove directory %s" % (self.pool_uuid, path))

        return gc_files

    @ensure_pool_initialized
    def init_cache(self, volume):
        # type: (VolumeTO | jsonobject.JsonObject) -> CacheProcessor
        """ Initialize cache for a cache volume with given UUID
        and size on the mounted filesystem of the pool
        """
        return CacheProcessor(self, volume)

class CacheProcessor(object):
    CACHE_FILE_NAME_PREFIX = "cache_for_volume"
    BITMAP_NAME = "block-cache"

    __pool = None  # type: PoolProcessor
    __cache_file = None  # type: Qcow2FileInfo
    __backing_volume = None  # type: BackingVolume

    volume = None # type: VolumeTO | jsonobject.JsonObject

    @property
    def pool(self):
        return self.__pool

    @property
    def cache_file(self):
        return self.__cache_file
    
    @property
    def backing_volume(self):
        return self.__backing_volume

    @property
    def install_path(self):
        assert self.pool and self.pool.mount_point
        return os.path.join(self.pool.mount_point[MountPointInfoFields.TARGET],
                            "%s_%s" % (self.CACHE_FILE_NAME_PREFIX, self.volume.volumeUuid))

    @property
    def is_instantiated(self):
        return os.path.isfile(self.install_path) and QemuImgCommandWrapper.get_img_fmt(self.install_path) == "qcow2"

    def __init__(self, pool_processor, volume, auto_create=True):
        # type: (PoolProcessor, VolumeTO | jsonobject.JsonObject, bool) -> None
        if not pool_processor or not pool_processor.is_initialized:
            raise PoolNotInitializedError("PoolProcessor is not initialized, cannot create CacheProcessor")

        self.__pool = pool_processor
        self.volume = volume

        backing_volume_class = supported_backing_volume_classes.get(
            BackingVolumeDeviceType(self.volume.deviceType)) # type: type[BackingVolume] | None

        if not backing_volume_class:
            raise UnsupportedDeviceTypeError("Unsupported backing volume device type %s for volume %s"
                            % (self.volume.deviceType, self.volume.volumeUuid))

        self.__backing_volume = backing_volume_class(self.volume)

        if auto_create and (not self.is_instantiated):
            logger.info("Cache file does not exist at path %s, creating new cache file" % self.install_path)
            self.create()

        if self.is_instantiated:
            self.__cache_file = Qcow2FileInfo(self.install_path)

    def __create_cache_file(self, size):
        # type: (int) -> Qcow2FileInfo
        """ Create a cache file with given size on the mounted filesystem of the pool """
        if self.is_instantiated:
            raise CacheOperationError("Cache file already exists at path %s" % self.install_path)
        QemuImgCommandWrapper.qcow2_create(image_path=self.install_path,
                                           virtual_size=size,
                                           cluster_size="128k",
                                           block_cache=False)
        return Qcow2FileInfo(self.install_path)

    def __remove_cache_file(self, is_exception=False):
        # type: (bool) -> None
        """ Remove cache file from the mounted filesystem of the pool """
        if not self.is_instantiated:
            logger.warning("Cache file does not exist at path %s, nothing to remove" % self.install_path)
            return
        try:
            os.remove(self.install_path)
            logger.info("Removed cache file at path %s" % self.install_path)
        except Exception as e:
            logger.error("Failed to remove cache file %s: %s" % (self.install_path, str(e)))
            logger.error(traceback.format_exc())
            if is_exception:
                raise CacheOperationError("Failed to remove cache file %s: %s" % (self.install_path, str(e)))
    
    def __get_capacity(self):
        # type: () -> tuple[int, int]
        """ Get capacity of the cache file based on its virtual size """
        if not self.is_instantiated:
            raise CacheNotInstantiatedError("Cache file is not instantiated at path %s, cannot get capacity" % self.install_path)
        assert self.cache_file
        return self.cache_file.virtual_size, self.cache_file.actual_size

    @rollback
    def create(self):
        # type: () -> None
        """ Create cache volume with given virtual size on the pool and return the device path of the cache volume """
        if not self.pool or not self.pool.is_initialized or not self.pool.check_pool().is_healthy:
            raise PoolOperationError("PoolProcessor is not healthy, cannot create cache volume")
        rollback_create_cache_file = rollbackable(lambda: self.__remove_cache_file(is_exception=False))
        rollback_create_cache_file()
        assert self.volume.size
        self.__create_cache_file(self.volume.size)
    
    def delete(self):
        self.__remove_cache_file(is_exception=True)
    
    def flush(self, on_progress_callback=None):
        if not self.is_instantiated:
            raise CacheNotInstantiatedError("Cache file is not instantiated at path %s, cannot flush" % self.install_path)

        flush_error = [None]

        bitmap_name = self.BITMAP_NAME
        bitmaps = QemuImgCommandWrapper.get_qcow2_bitmaps(self.install_path)
        
        if list(filter(lambda b: b["name"] == bitmap_name, bitmaps)):
            # Found existing bitmap with the same name, try to flush the bitmap to backing volume
            logger.info("Found existing bitmap with name %s in cache file %s, try to flush bitmap to backing volume %s"
                        % (bitmap_name, self.install_path, self.backing_volume.source_path))
        else:
            # Degraded flush will flush full cache file to backing volume without bitmap optimization
            logger.info("No existing bitmap with name %s found in cache file %s, degraded flush will be performed without bitmap optimization"
                        % (bitmap_name, self.install_path))
            bitmap_name = None

        def _on_progress_callback(progress, err):
            logger.info("Volume %s is flushing cache to backing volume, progress: %s%%" % (self.volume.volumeUuid, progress))
            if err:
                flush_error[0] = err
            if on_progress_callback:
                on_progress_callback(progress, err)

        QemuImgCommandWrapper.flush_qcow2_to_backing_volume(qcow2_path=self.install_path,
                                                            output_format=self.backing_volume.output_format,
                                                            source_path=self.backing_volume.source_path,
                                                            bitmap_name=bitmap_name,
                                                            on_progress=_on_progress_callback)
        if flush_error[0]:
            raise CacheOperationError("Failed to flush cache file %s to backing volume %s: %s"
                            % (self.install_path, self.backing_volume.source_path, flush_error[0]))

    def get_capacity(self):
        # type: () -> CacheCapacityInfo
        virtual_size, actual_size = self.__get_capacity()
        return CacheCapacityInfo(virtual_size=virtual_size, actual_size=actual_size)

class FlushCacheTaskDaemon(plugin.TaskDaemon):
    def __init__(self, task_spec, cache):
        # type: (object, CacheProcessor) -> None
        super(FlushCacheTaskDaemon, self).__init__(task_spec, "FlushVolumeCache")
        self.cache = cache
        self.progress = 0
        self.error = None

    def _cancel(self):
        logger.warning("Cancel is not supported for cache flush task, task will continue to completion")

    def _get_percent(self):
        # type: () -> int
        return self.progress

    def _get_detail(self):
        # type: () -> jsonobject.JsonObject
        return jsonobject.loads(json.dumps({
            "volumeUuid": self.cache.volume.volumeUuid,
            "cacheInstallPath": self.cache.install_path
        }))

    def update_progress(self, progress, err):
        # type: (float|None, str|None) -> None
        if progress is not None:
            self.progress = int(max(0, min(99, progress)))
        if err:
            self.error = err

    def flush(self):
        self.cache.flush(on_progress_callback=self.update_progress)
        if self.error:
            raise Exception(self.error)
        self.progress = 100

T_Cmd = TypeVar("T_Cmd", bound="BaseCmd")
T_Rsp = TypeVar("T_Rsp", bound="VolumeCacheBaseResponse")

def auto_serialize(cmd_type, rsp_type):
    # type: (type[T_Cmd], type[T_Rsp]) -> Callable[[Callable[[VolumeCachePlugin, T_Cmd], T_Rsp]], Callable[[VolumeCachePlugin, dict[str, Any]], str]]
    def decorator(func):
        # type: (Callable[[VolumeCachePlugin, T_Cmd], T_Rsp]) -> Callable[[VolumeCachePlugin, dict[str, Any]], str]
        @functools.wraps(func)
        def wrapper(self, req):
            # type: (VolumeCachePlugin, dict[str, Any]) -> str
            try:
                cmd = cmd_type.from_json(jsonobject.loads(req[http.REQUEST_BODY])) # type: BaseCmd
                rsp_obj = func(self, cmd)
                assert isinstance(rsp_obj, rsp_type), "Response object must be instance of %s" % rsp_type.__name__
                return jsonobject.dumps(rsp_obj)
            except Exception as e:
                logger.error(traceback.format_exc())
                raise e
        return wrapper
    return decorator

def ensure_pool(initialized=False):
    # type: (bool) -> Callable[[Callable[[VolumeCachePlugin, T_Cmd, PoolProcessor], T_Rsp]], Callable[[VolumeCachePlugin, T_Cmd], T_Rsp]]
    def decorator(func):
        # type: (Callable[[VolumeCachePlugin, T_Cmd, PoolProcessor], T_Rsp]) -> Callable[[VolumeCachePlugin, T_Cmd], T_Rsp]
        @functools.wraps(func)
        def wrapper(self, cmd):
            # type: (VolumeCachePlugin, T_Cmd) -> T_Rsp
            pool_processor = self.pool_processors.get(cmd.poolUuid)
            if not pool_processor:
                pool_processor = self._load_pool_on_demand(cmd.poolUuid)
            if initialized and not pool_processor.is_initialized:
                raise PoolNotInitializedError("Pool processor for pool UUID %s is not initialized" % cmd.poolUuid)
            return func(self, cmd, pool_processor)
        return wrapper
    return decorator

class VolumeCachePlugin(kvmagent.KvmAgent):
    pool_processors = None  # type: dict[str, PoolProcessor]

    INIT_POOL_PATH = "/hostcachestore/init"
    CONNECT_POOL_PATH = "/hostcachestore/connect"
    EXTEND_POOL_PATH = "/hostcachestore/extend"
    DELETE_POOL_PATH = "/hostcachestore/delete"
    CHECK_POOL_PATH = "/hostcachestore/check"
    GET_POOL_CAPACITY_PATH = "/hostcachestore/getcapacity"
    GC_POOL_PATH = "/hostcachestore/gc"

    CREATE_CACHE_PATH = "/volumecache/create"
    DELETE_CACHE_PATH = "/volumecache/delete"
    FLUSH_CACHE_PATH = "/volumecache/flush"
    GET_CACHE_CAPACITY_PATH = "/volumecache/getcapacity"

    # Legacy HTTP path aliases (pre-rename). Registered alongside the new
    # routes above so that older management-node builds -- which still target
    # ``/localvolumecache/*`` during rolling upgrades -- keep working. Each
    # alias maps 1:1 to its corresponding new path handler.
    LEGACY_INIT_POOL_PATH = "/localvolumecache/pool/init"
    LEGACY_CONNECT_POOL_PATH = "/localvolumecache/pool/connect"
    LEGACY_EXTEND_POOL_PATH = "/localvolumecache/pool/extend"
    LEGACY_DELETE_POOL_PATH = "/localvolumecache/pool/delete"
    LEGACY_CHECK_POOL_PATH = "/localvolumecache/pool/check"
    LEGACY_GET_POOL_CAPACITY_PATH = "/localvolumecache/pool/getcapacity"
    LEGACY_GC_POOL_PATH = "/localvolumecache/pool/gc"

    LEGACY_CREATE_CACHE_PATH = "/localvolumecache/create"
    LEGACY_DELETE_CACHE_PATH = "/localvolumecache/delete"
    LEGACY_FLUSH_CACHE_PATH = "/localvolumecache/flush"
    LEGACY_GET_CACHE_CAPACITY_PATH = "/localvolumecache/getcapacity"

    def __init__(self):
        super(VolumeCachePlugin, self).__init__()
        self.pool_processors = {}

    def _load_pool_on_demand(self, pool_uuid):
        # type: (str) -> PoolProcessor
        pool = self.pool_processors.get(pool_uuid)
        if pool:
            return pool

        pool = PoolProcessor.discover_local_pool(pool_uuid)
        if not pool:
            raise PoolNotFoundError("No local volume cache pool found for pool UUID %s" % pool_uuid)

        pool.connect_pool()
        self.pool_processors[pool_uuid] = pool
        logger.info("Connected local volume cache pool %s on mount path %s" % (
            pool.pool_uuid, pool.mount_path))
        return pool

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_POOL_PATH, self.init_pool)
        http_server.register_async_uri(self.CONNECT_POOL_PATH, self.connect_pool)
        http_server.register_async_uri(self.EXTEND_POOL_PATH, self.extend_pool)
        http_server.register_async_uri(self.DELETE_POOL_PATH, self.delete_pool)
        http_server.register_async_uri(self.CHECK_POOL_PATH, self.check_pool)
        http_server.register_async_uri(self.GET_POOL_CAPACITY_PATH, self.get_pool_capacity)
        http_server.register_async_uri(self.GC_POOL_PATH, self.gc_pool)

        http_server.register_async_uri(self.CREATE_CACHE_PATH, self.create_cache)
        http_server.register_async_uri(self.DELETE_CACHE_PATH, self.delete_cache)
        http_server.register_async_uri(self.FLUSH_CACHE_PATH, self.flush_cache)
        http_server.register_async_uri(self.GET_CACHE_CAPACITY_PATH, self.get_cache_capacity)

        # Register legacy ``/localvolumecache/*`` aliases so that rolling
        # upgrades -- where the management node may still be on an older
        # release that targets the pre-rename URLs -- continue to reach the
        # same handlers.
        http_server.register_async_uri(self.LEGACY_INIT_POOL_PATH, self.init_pool)
        http_server.register_async_uri(self.LEGACY_CONNECT_POOL_PATH, self.connect_pool)
        http_server.register_async_uri(self.LEGACY_EXTEND_POOL_PATH, self.extend_pool)
        http_server.register_async_uri(self.LEGACY_DELETE_POOL_PATH, self.delete_pool)
        http_server.register_async_uri(self.LEGACY_CHECK_POOL_PATH, self.check_pool)
        http_server.register_async_uri(self.LEGACY_GET_POOL_CAPACITY_PATH, self.get_pool_capacity)
        http_server.register_async_uri(self.LEGACY_GC_POOL_PATH, self.gc_pool)

        http_server.register_async_uri(self.LEGACY_CREATE_CACHE_PATH, self.create_cache)
        http_server.register_async_uri(self.LEGACY_DELETE_CACHE_PATH, self.delete_cache)
        http_server.register_async_uri(self.LEGACY_FLUSH_CACHE_PATH, self.flush_cache)
        http_server.register_async_uri(self.LEGACY_GET_CACHE_CAPACITY_PATH, self.get_cache_capacity)

    def stop(self):
        pass

    def _to_pool_rsp(self, pool):
        # type: (PoolProcessor) -> PoolRsp
        rsp = PoolRsp()
        assert pool.vg and pool.lv and pool.fs and pool.mount_point
        rsp.poolUuid = pool.pool_uuid
        rsp.mountPoint = pool.mount_point[MountPointInfoFields.TARGET]
        try:
            pool_capacity = pool.get_capacity()
            rsp.capacity = pool_capacity.total
        except Exception as e:
            logger.warning("Failed to read capacity for pool %s: %s" % (pool.pool_uuid, str(e)))
            rsp.capacity = None
        return rsp

    def _to_pool_health_rsp(self, pool_health_info):
        # type: (PoolHealthInfo) -> PoolHealthRsp
        rsp = PoolHealthRsp()
        rsp.healthy = pool_health_info.is_healthy
        if not pool_health_info.is_healthy:
            # aggregate failure reason: first unhealthy layer wins
            reasons = []
            unhealthy_pvs = [pv[PVInfoFields.PV_NAME] for pv, healthy in pool_health_info.pvs.items() if not healthy]
            if unhealthy_pvs:
                reasons.append("unhealthy pvs: %s" % ",".join(unhealthy_pvs))
            if pool_health_info.vg is False:
                reasons.append("vg unhealthy")
            if pool_health_info.lv is False:
                reasons.append("lv unhealthy")
            if pool_health_info.filesystem is False:
                reasons.append("filesystem unhealthy")
            rsp.reason = "; ".join(reasons) if reasons else "unhealthy"
        return rsp

    def _to_pool_capacity_rsp(self, capacity):
        # type: (PoolCapacityInfo) -> PoolCapacityRsp
        rsp = PoolCapacityRsp()
        rsp.total = capacity.total
        rsp.used = capacity.used
        rsp.available = capacity.available
        rsp.allocated = capacity.allocated
        rsp.dirty = capacity.dirty
        return rsp

    def _to_cache_rsp(self, cache):
        # type: (CacheProcessor) -> CacheRsp
        rsp = CacheRsp()
        rsp.installPath = cache.install_path
        capacity = cache.get_capacity()
        rsp.virtualSize = capacity.virtual_size
        rsp.actualSize = capacity.actual_size
        return rsp

    @kvmagent.replyerror
    @auto_serialize(InitPoolCmd, InitPoolRsp)
    def init_pool(self, cmd):
        # type: (InitPoolCmd) -> InitPoolRsp
        pool = self.pool_processors.get(cmd.poolUuid)
        if pool:
            if pool.is_initialized:
                return self._to_pool_rsp(pool)
            pool.connect_pool()
            return self._to_pool_rsp(pool)

        pool = PoolProcessor(cmd.poolUuid, cmd.mountPoint)
        pool.init_pool(
            device_paths=cmd.devices,
            force=bool(cmd.force)
        )
        self.pool_processors[cmd.poolUuid] = pool
        return self._to_pool_rsp(pool)

    @kvmagent.replyerror
    @auto_serialize(ConnectPoolCmd, ConnectPoolRsp)
    def connect_pool(self, cmd):
        # type: (ConnectPoolCmd) -> ConnectPoolRsp
        pool = self.pool_processors.get(cmd.poolUuid)
        if pool:
            pool.connect_pool()
        else:
            pool = self._load_pool_on_demand(cmd.poolUuid)
        return self._to_pool_rsp(pool)

    @kvmagent.replyerror
    @auto_serialize(ExtendPoolCmd, ExtendPoolRsp)
    @ensure_pool(initialized=True)
    def extend_pool(self, cmd, pool):
        # type: (ExtendPoolCmd, PoolProcessor) -> ExtendPoolRsp
        pool.extend_pool(additional_device_paths=cmd.devices, force=bool(cmd.force))
        pool.connect_pool()

        return self._to_pool_rsp(pool)

    @kvmagent.replyerror
    @auto_serialize(DeletePoolCmd, DeletePoolRsp)
    @ensure_pool(initialized=True)
    def delete_pool(self, cmd, pool):
        # type: (DeletePoolCmd, PoolProcessor) -> DeletePoolRsp
        pool.delete_pool()
        self.pool_processors.pop(cmd.poolUuid, None)
        return DeletePoolRsp()

    @kvmagent.replyerror
    @auto_serialize(CheckPoolCmd, PoolHealthRsp)
    @ensure_pool(initialized=True)
    def check_pool(self, cmd, pool):
        # type: (CheckPoolCmd, PoolProcessor) -> PoolHealthRsp
        pool_health = pool.check_pool()
        return self._to_pool_health_rsp(pool_health)

    @kvmagent.replyerror
    @auto_serialize(GetPoolCapacityCmd, PoolCapacityRsp)
    @ensure_pool(initialized=True)
    def get_pool_capacity(self, cmd, pool):
        # type: (GetPoolCapacityCmd, PoolProcessor) -> PoolCapacityRsp
        capacity = pool.get_capacity()
        return self._to_pool_capacity_rsp(capacity)

    @kvmagent.replyerror
    @auto_serialize(AllocateCacheCmd, CacheRsp)
    @ensure_pool(initialized=True)
    def create_cache(self, cmd, pool):
        # type: (AllocateCacheCmd, PoolProcessor) -> CacheRsp

        cache = pool.init_cache(volume=cmd.volume)
        return self._to_cache_rsp(cache)

    @kvmagent.replyerror
    @auto_serialize(DeleteCacheCmd, DeleteCacheRsp)
    @ensure_pool(initialized=True)
    def delete_cache(self, cmd, pool):
        # type: (DeleteCacheCmd, PoolProcessor) -> DeleteCacheRsp
        cache = pool.init_cache(volume=cmd.volume)
        cache.delete()
        return DeleteCacheRsp()

    @kvmagent.replyerror
    @auto_serialize(FlushCacheCmd, CacheRsp)
    @ensure_pool(initialized=True)
    def flush_cache(self, cmd, pool):
        # type: (FlushCacheCmd, PoolProcessor) -> CacheRsp
        cache = pool.init_cache(volume=cmd.volume)
        with FlushCacheTaskDaemon(cmd, cache) as daemon:
            daemon.flush()

        return self._to_cache_rsp(cache)

    @kvmagent.replyerror
    @auto_serialize(GcPoolCmd, GcPoolRsp)
    @ensure_pool(initialized=True)
    def gc_pool(self, cmd, pool):
        # type: (GcPoolCmd, PoolProcessor) -> GcPoolRsp
        volume_uuids = cmd.inUseCacheUuids if cmd.inUseCacheUuids else []
        gc_files = pool.gc_pool(volume_uuids)

        rsp = GcPoolRsp()
        rsp.gcFiles = gc_files
        rsp.gcCount = len(gc_files)
        return rsp

    @kvmagent.replyerror
    @auto_serialize(GetCacheCapacityCmd, CacheRsp)
    @ensure_pool(initialized=True)
    def get_cache_capacity(self, cmd, pool):
        # type: (GetCacheCapacityCmd, PoolProcessor) -> CacheRsp
        cache = CacheProcessor(pool, cmd.volume, auto_create=False)
        return self._to_cache_rsp(cache)
