import re
import tempfile
import os
import os.path
import platform
import json

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import shell
from zstacklib.utils import traceable_shell
from zstacklib.utils.bash import bash_progress_1, in_bash, bash_r, bash_roe
from zstacklib.utils.report import *

logger = log.get_logger(__name__)
HOST_ARCH = platform.machine()


class ImageStoreClient(object):

    ZSTORE_PROTOSTR = "zstore://"
    ZSTORE_CLI_BIN = "/usr/local/zstack/imagestore/bin/zstcli"
    ZSTORE_CLI_PATH = ZSTORE_CLI_BIN + " -rootca /var/lib/zstack/imagestorebackupstorage/package/certs/ca.pem"
    ZSTORE_DEF_PORT = 8000

    UPLOAD_BIT_PATH = "/imagestore/upload"
    DOWNLOAD_BIT_PATH = "/imagestore/download"
    COMMIT_BIT_PATH = "/imagestore/commit"
    CONVERT_TO_RAW = "/imagestore/convert/raw"

    RESERVE_CAPACITY = 10 * 1024 * 1024 * 1024

    def _check_zstore_cli(self):
        if not os.path.exists(self.ZSTORE_CLI_BIN):
            errmsg = '%s not found. Please reconnect all hosts, and try again.' % self.ZSTORE_CLI_BIN
            raise kvmagent.KvmError(errmsg)

    def _parse_image_reference(self, backupStorageInstallPath):
        if not backupStorageInstallPath.startswith(self.ZSTORE_PROTOSTR):
            raise kvmagent.KvmError('unexpected backup storage install path %s' % backupStorageInstallPath)

        xs = backupStorageInstallPath[len(self.ZSTORE_PROTOSTR):].split('/')
        if len(xs) != 2:
            raise kvmagent.KvmError('unexpected backup storage install path %s' % backupStorageInstallPath)

        return xs[0], xs[1]

    def _build_install_path(self, name, imgid):
        return "{0}{1}/{2}".format(self.ZSTORE_PROTOSTR, name, imgid)

    def upload_image(self, hostname, fpath, concurrency=None):
        imf = self.commit_image(fpath)

        extra_param = ""
        if concurrency and concurrency > 1:
            extra_param += "-concurrency=%d " % concurrency

        cmdstr = '%s -url %s:%s push %s %s' % (self.ZSTORE_CLI_PATH, hostname, self.ZSTORE_DEF_PORT, extra_param, fpath)
        logger.debug('pushing %s to image store' % fpath)
        shell.check_run(cmdstr)
        logger.debug('%s pushed to image store' % fpath)

        return imf

    def commit_image(self, fpath):
        cmdstr = '%s -json add -file %s' % (self.ZSTORE_CLI_PATH, fpath)
        logger.debug('adding %s to local image store' % fpath)
        output = shell.call(cmdstr.encode(encoding="utf-8"))
        logger.debug('%s added to local image store' % fpath)

        return jsonobject.loads(output.splitlines()[-1])

    def stop_backup_jobs(self, vm):
        with linux.ShowLibvirtErrorOnException(vm):
            cmdstr = '%s stopbak -domain %s' % (self.ZSTORE_CLI_PATH, vm)
            return shell.call(cmdstr).strip()

    def stop_vm_backup_jobs(self, vm, force=False):
        with linux.ShowLibvirtErrorOnException(vm):
            cmdstr = '%s stopbak -force=%s -domain %s -batbak' % (self.ZSTORE_CLI_PATH, force, vm)
            return shell.call(cmdstr).strip()

    def stop_volume_backup_job(self, vm, drive, force=False):
        with linux.ShowLibvirtErrorOnException(vm):
            cmdstr = '%s stopbak -force=%s -domain %s -drive %s' % (self.ZSTORE_CLI_PATH, force, vm, drive)
            return shell.call(cmdstr).strip()

    @staticmethod
    def check_capacity(dstdir):
        if not os.path.isdir(dstdir):
            return

        avaliable = linux.get_free_disk_size(dstdir)
        if avaliable < ImageStoreClient.RESERVE_CAPACITY:
            raise Exception(
                'storage free size is less than reserved capacity: %d' % ImageStoreClient.RESERVE_CAPACITY)


    def stop_mirror(self, vm, complete, node, force=False):
        with linux.ShowLibvirtErrorOnException(vm):
            cmdstr = '%s stopmirr -force=%s -domain %s -delbitmap=%s -drive "%s"' % \
                     (self.ZSTORE_CLI_PATH, force, vm, complete, node)
            shell.call(cmdstr)

    def query_mirror_volumes(self, vm):
        with linux.ShowLibvirtErrorOnException(vm):
            cmdstr = '%s querymirr -domain %s' % \
                     (self.ZSTORE_CLI_PATH, vm)
            jobj = jsonobject.loads(shell.call(cmdstr))
            if jobj is None:
                return None
            return jobj.__dict__ if hasattr(jobj, "__dict__") else jobj.mirrorVolumes

    def mirror_volume(self, vm, node, dest, lastvolume, currvolume, volumetype, mode, speed, reporter):
        PFILE = linux.create_temp_file()

        def _get_progress(synced):
            last = linux.tail_1(PFILE).strip()
            if not last or not last.isdigit():
                return synced

            reporter.progress_report(get_exact_percent(last, reporter.taskStage), "report")
            return synced

        with linux.ShowLibvirtErrorOnException(vm):
            cmdstr = '%s -progress %s mirror -dest %s -domain %s -drive "%s" -lastMirrorVolume "%s" -mirrorVolume "%s" -volumeType %s -mode "%s" -speed %d' % \
                     (self.ZSTORE_CLI_PATH, PFILE, dest, vm, node, lastvolume, currvolume, volumetype, mode, speed)
            _, mode, err = bash_progress_1(cmdstr, _get_progress)
            linux.rm_file_force(PFILE)
            if err:
                raise Exception('fail to mirror volume %s, because %s' % (vm, str(err)))

    def query_vm_mirror_latencies_boundary(self, vm, times):
        with linux.ShowLibvirtErrorOnException(vm):
            infosMaps = []
            maxLatencies = []
            maxInfoMap = {}
            minInfoMap = {}
            PFILE = linux.create_temp_file()
            cmdstr = '%s querylat -domain %s -count %d > %s' % (self.ZSTORE_CLI_PATH, vm, times, PFILE)
            if shell.run(cmdstr) != 0 or os.path.getsize(PFILE) == 0:
                logger.debug("Failed to query latency for vm: [%s]", vm)
                return maxInfoMap, minInfoMap

            with open(PFILE) as fd:
                linux.rm_file_force(PFILE)
                for line in fd.readlines():
                    infosMap = {}
                    j = jsonobject.loads(line.strip())
                    for key, val in j.__dict__.iteritems():
                        infosMap[key] = val
                    infosMaps.append(infosMap)
                    maxLatencies.append(max(infosMap.values()))

                if maxLatencies:
                    maxLatency = max(maxLatencies)
                    minLatency = min(maxLatencies)
                    for infoMap in infosMaps:
                        k = [k for k, v in infoMap.items() if v == maxLatency]
                        if k:
                            maxInfoMap = infoMap
                            break
                    for infoMap in infosMaps:
                        values = infoMap.values()
                        if values and all(i <= minLatency for i in values):
                            minInfoMap = infoMap
                            break
            return vm, maxInfoMap, minInfoMap

    def backup_volume(self, vm, node, bitmap, mode, dest, point_in_time, speed, reporter, stage):
        self.check_capacity(os.path.dirname(dest))

        PFILE = linux.create_temp_file()

        def _get_progress(synced):
            last = linux.tail_1(PFILE).strip()
            if not last or not last.isdigit():
                return synced

            reporter.progress_report(get_exact_percent(last, stage), "report")
            return synced

        with linux.ShowLibvirtErrorOnException(vm):
            p_option = ""
            if point_in_time is not None:
                p_option = "-point-in-time=%s" % str(point_in_time).lower()

            cmdstr = '%s -progress %s backup -bitmap %s -dest %s -domain %s -drive "%s" -mode %s %s -speed %s' % \
                     (self.ZSTORE_CLI_PATH, PFILE, bitmap, dest, vm, node, mode, p_option, speed)
            _, mode, err = bash_progress_1(cmdstr, _get_progress)
            linux.rm_file_force(PFILE)
            if err:
                self.check_capacity(os.path.dirname(dest))
                raise Exception('fail to backup vm %s, because %s' % (vm, str(err)))
            return mode.strip()

    # args -> (bitmap, mode, drive)
    # {'drive-virtio-disk0': { "backupFile": "foo", "mode":"full" },
    #  'drive-virtio-disk1': { "backupFile": "bar", "mode":"top" }}
    def backup_volumes(self, vm, args, dstdir, point_in_time, reporter, stage):
        self.check_capacity(dstdir)
        PFILE = linux.create_temp_file()

        def _get_progress(synced):
            last = linux.tail_1(PFILE).strip()
            if not last or not last.isdigit():
                return synced

            reporter.progress_report(get_exact_percent(last, stage), "report")
            return synced

        with linux.ShowLibvirtErrorOnException(vm):
            p_option = ""
            if point_in_time is not None:
                p_option = "-point-in-time=%s" % str(point_in_time).lower()

            cmdstr = '%s -progress %s batbak -domain %s -destdir %s %s -args %s' % \
                     (self.ZSTORE_CLI_PATH, PFILE, vm, dstdir, p_option, ':'.join(["%s,%s,%s,%s" % x for x in args]))
            _, mode, err = bash_progress_1(cmdstr, _get_progress)
            linux.rm_file_force(PFILE)
            if err:
                self.check_capacity(dstdir)
                raise Exception('fail to backup vm %s, because %s' % (vm, str(err)))
            return mode.strip()

    def top_backup_volumes(self, vm, args, dstdir):
        with linux.ShowLibvirtErrorOnException(vm):
            cmdstr = '%s battopbak -domain %s -destdir %s -args %s' % \
                     (self.ZSTORE_CLI_PATH, vm, dstdir, ':'.join(["%s,%s" % x for x in args]))
            _, mode, err = bash_roe(cmdstr)
            if err:
                raise Exception('fail to top backup vm %s, because %s' % (vm, str(err)))
            return mode.strip()

    def image_already_pushed(self, hostname, imf):
        cmdstr = '%s -url %s:%s info %s' % (self.ZSTORE_CLI_PATH, hostname, self.ZSTORE_DEF_PORT, self._build_install_path(imf.name, imf.id))
        if shell.run(cmdstr) != 0:
            return False
        return True

    def upload_to_imagestore(self, cmd, req):
        self._check_zstore_cli()

        crsp = self.commit_to_imagestore(cmd, req)

        extpara = ""
        taskid = req[http.REQUEST_HEADER].get(http.TASK_UUID)
        if cmd.threadContext:
            if cmd.threadContext['task-stage']:
                extpara += " -stage %s" % cmd.threadContext['task-stage']
            if cmd.threadContext.api:
                taskid = cmd.threadContext.api

        push_ext_param = ""
        if cmd.concurrency and cmd.concurrency > 1:
            push_ext_param += " -concurrency %d" % cmd.concurrency

        cmdstr = '%s -url %s:%s -callbackurl %s -taskid %s -imageUuid %s %s push %s %s' % (
            self.ZSTORE_CLI_PATH, cmd.hostname, self.ZSTORE_DEF_PORT, req[http.REQUEST_HEADER].get(http.CALLBACK_URI),
            taskid, cmd.imageUuid, extpara, push_ext_param, cmd.primaryStorageInstallPath)
        logger.debug('pushing %s to image store' % cmd.primaryStorageInstallPath)
        shell = traceable_shell.get_shell(cmd)
        shell.call(cmdstr)
        logger.debug('%s pushed to image store' % cmd.primaryStorageInstallPath)

        rsp = kvmagent.AgentResponse()
        rsp.backupStorageInstallPath = jsonobject.loads(crsp).backupStorageInstallPath
        return jsonobject.dumps(rsp)


    def commit_to_imagestore(self, cmd, req):
        self._check_zstore_cli()

        fpath = cmd.primaryStorageInstallPath

        # Synchronize cached writes for 'fpath'
        linux.sync_file(fpath)

        # Add the image to registry
        cmdstr = '%s -json  -callbackurl %s -taskid %s -imageUuid %s add -desc \'%s\' -file %s' % (self.ZSTORE_CLI_PATH, req[http.REQUEST_HEADER].get(http.CALLBACK_URI),
                req[http.REQUEST_HEADER].get(http.TASK_UUID), cmd.imageUuid, cmd.description, fpath)
        logger.debug('adding %s to local image store' % fpath)
        output = shell.call(cmdstr.encode(encoding="utf-8"))
        logger.debug('%s added to local image store' % fpath)

        imf = jsonobject.loads(output.splitlines()[-1])

        rsp = kvmagent.AgentResponse()
        rsp.backupStorageInstallPath = self._build_install_path(imf.name, imf.id)
        rsp.size = imf.virtualsize
        rsp.actualSize = imf.size

        return jsonobject.dumps(rsp)

    def download_from_imagestore(self, cachedir, host, bs_path, ps_path, concurrency=1, failure_action=None):
        self._check_zstore_cli()

        name, imageid = self._parse_image_reference(bs_path)
        extra_param = ""
        if cachedir:
            extra_param += " -cachedir %s" % cachedir

        pull_extra_param = ""
        if concurrency and concurrency > 1:
            pull_extra_param += " -concurrency=%d" % concurrency
        cmdstr = '%s -url %s:%s %s pull %s -installpath %s %s:%s' % \
                 (self.ZSTORE_CLI_PATH, host, self.ZSTORE_DEF_PORT, extra_param, pull_extra_param, ps_path, name, imageid)
        logger.debug('pulling %s:%s from image store' % (name, imageid))

        try:
            shell.call(cmdstr)
        except Exception as ex:
            if failure_action:
                failure_action()
            err = str(ex)
            if 'Please check whether ImageStore directory is correctly mounted' in err:
                raise Exception("Target image not found, please check whether ImageStore directory is correctly mounted.")
            raise ex
        
        logger.debug('%s:%s pulled to local cache' % (name, imageid))

    def image_info(self, host, install_path):
        self._check_zstore_cli()
        name, imageid = self._parse_image_reference(install_path)
        cmd = "%s -url %s:%s -json info %s:%s" % (self.ZSTORE_CLI_PATH, host, self.ZSTORE_DEF_PORT, name, imageid)
        s = shell.ShellCmd(cmd)
        s(False)
        if s.return_code == 0:
            return jsonobject.loads(s.stdout)


    @in_bash
    def clean_imagestore_cache(self, cachedir):
        if not cachedir or not os.path.exists(cachedir):
            return

        cdir = os.path.join(os.path.realpath(cachedir), "zstore-cache")
        cmdstr = "find %s -type f -name image -links 1 -exec unlink {} \;" % cdir
        bash_r(cmdstr)
        cmdstr = "find %s -depth -mindepth 1 -type d -empty -exec rmdir {} \;" % cdir
        bash_r(cmdstr)

    def clean_meta(self, path):
        meta_path = os.path.splitext(path)[0] + ".imf"
        linux.rm_file_force(meta_path)
        linux.rm_file_force(meta_path + "2")

    def convert_image_raw(self, cmd):
        destPath = cmd.srcPath.replace('.qcow2', '.raw')
        linux.qcow2_convert_to_raw(cmd.srcPath, destPath)
        rsp = kvmagent.AgentResponse()
        rsp.destPath = destPath
        return jsonobject.dumps(rsp)
