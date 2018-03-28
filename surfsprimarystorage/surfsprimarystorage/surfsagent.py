__author__ = 'frank'

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.log as log
import zstacklib.utils.shell as shell
import zstacklib.utils.lichbd as lichbd
import zstacklib.utils.iptables as iptables
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.lock as lock
import zstacklib.utils.linux as linux
import zstacklib.utils.sizeunit as sizeunit
from zstacklib.utils import plugin
from zstacklib.utils.rollback import rollback, rollbackable
import os
import errno
import functools
import traceback
import pprint
import threading
import commands
import json
import time
logger = log.get_logger(__name__)

class SurfsCmdManage(object):
    def __init__(self):
        self.back_type='hdd'
        self.iqn_name='iqn.2017-10.org.surfs:'
        self.iscsi_port='3262'
        self.target_path='/surfs_storage'
        self.init_name=self._get_local_iscsi_initname()
        pooldata=self.get_pool_msg()
        psign = []
        if pooldata is None:
            logger.debug('Surfs is not ready')
            return
        else:
            for xpool in pooldata:
                if xpool['success'] is False:
                    logger.debug('Surfs is ready but pool %s is not ready'%xpool['pool'])
                else:
                    psign.append(xpool['pool'])
        if len(psign) == 0:
            logger.debug('no pool is ready')
            raise
        logger.debug('Surfs start complete!!!')         
        #self._resume_local_target(psign)
        #logger.debug('Local target reconnect complete!')    
    
    def _resume_local_target(self,pools):
        if os.path.exists(self.target_path) is False:
            return
        storage_dir=os.listdir(self.target_path)
        for xf in storage_dir:
            xdir=os.path.join(self.target_path,xf)
            if os.path.isfile(xdir):
                continue
            vol_ids=os.listdir(xdir)
            for vl in vol_ids:
                vol_dir=os.path.join(xdir,vl)
                vol_pool_ip=self.get_volume_pool_ip(vl)
                if vol_pool_ip is None:
                    self._clean_overdue_target(self.iqn_name,vl)
                    self._clean_overdue_link(vol_dir)
                    continue
                
                expmsg=self.get_exprot_msg(vl)
                if expmsg is None:
                    self._clean_overdue_target(self.iqn_name,vl)
                    self._clean_overdue_link(vol_dir)
                    continue
                
                if self.init_name != expmsg['InitiatorName']:
                    self._clean_overdue_target(self.iqn_name,vl)
                    self._clean_overdue_link(vol_dir)
                    continue                    
                                                        
                newip=self._check_target(self.iqn_name, self.init_name,'a12345678:a12345678', vl,vol_dir)
                if newip is None:
                    continue
                oldip=self._get_target_ip(self.iqn_name + vl)

                if oldip != newip:
                    self._clean_overdue_target(self.iqn_name,vl)
                    self._connect_root_target(vl, newip,self.iqn_name + vl,self.iscsi_port)
                    self._find_target_path(vl)
                    self._clean_overdue_link(vol_dir)
                    self._link_local_target(vol_dir, vl, newip)
                else:
                    self._login_local_target(self.iqn_name + vl)
                                            
    def _update_target_ip(self,target_name,newip):
        cmdstr='iscsiadm -m node -T ' + target_name + ' -o update --name node.discovery_address  --value=' + newip
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Failed to do :' + cmdstr + '[' + rslt + ']')        
                        
    def _get_target_ip(self,target_name):
        cmdstr='iscsiadm -m node -T ' + target_name + ' |grep node.discovery_address'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Failed to do :' + cmdstr + '[' + rslt + ']')
            return None
        if 'No records found' in rslt:
            return None       
        return rslt.split('=')[1]
    
    def _loginout_local_target(self,target_name):
        cmdstr='iscsiadm -m node -T ' + target_name + ' -u'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Failed to do :' + cmdstr + '[' + rslt + ']')               
                
    def _login_local_target(self,target_name):
        cmdstr='iscsiadm -m node -T ' + target_name + ' -l'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Failed to do :' + cmdstr + '[' + rslt + ']') 
    
    def _link_local_target(self,vol_dir,volname,newip):
        iscsipath='/dev/disk/by-path/ip-' + newip + ':' + self.iscsi_port + '-iscsi-' + self.iqn_name + volname + '-lun-0'            
        cmdstr='ln -s ' + iscsipath + ' ' + vol_dir
        ret,rslt=commands.getstatusoutput(cmdstr)        
                   
    def _clean_overdue_target(self,iqnname,volname):
        self._loginout_local_target(iqnname + volname)
        cmdstr='iscsiadm -m node -T ' + iqnname + volname + ' -o delete'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Failed to do :' + cmdstr + '[' + rslt + ']')

    def _clean_overdue_link(self,overdir):
        cmdstr='rm -f ' + overdir
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Failed to do :' + cmdstr + '[' + rslt + ']')            
                             
    def _check_target(self,iqn_name,initor_name,chap_info,volname,linkdir):
        cmdstr='surfs check_export ' + iqn_name + volname + ' ' + initor_name + ' ' + chap_info + ' ' + volname
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Error:[%s] for [%s]'%(rslt,cmdstr))
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            if 'volume not find' in rmsg['message']:
                self._clean_overdue_link(linkdir)
            return None
        return rmsg['data']['ip']       
    
    def get_pool_msg(self):
        cmdstr='surfs connect'
        i=0
        while i < 5:
            ret,rslt=commands.getstatusoutput(cmdstr)
            if ret == 0:
                rmsg=json.loads(rslt)
                if rmsg["success"] is False:
                    i += 1 
                    time.sleep(1)
                    continue
                else:
                    return rmsg["data"]
        return None
    
    def get_volume_pool_ip(self,volname):
        cmdstr= 'surfs volume ' + volname
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            return None
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            return None
        
        return rmsg["data"]["ip"]
          
    def download_image_to_surfs(self,url,image_uuid,image_fmt):
        cmdstr='surfs image-add %s %s %s'%(url,image_fmt,image_uuid)       
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        return True
        
    def get_iamge_size(self,imageid):
        cmdstr='surfs image-info ' + imageid
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        size=rmsg['data']['size']
        return size
    
    def delete_image(self,imageuuid):
        cmdstr='surfs image-del %s'%imageuuid
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        return True
    
    def get_storage_ip(self,mg_ip):
        return mg_ip
    
    def create_data_volume(self,vol_id,sizestr,typestr,ipstr=None):
        cmdstr=''
        if ipstr is None:
            cmdstr='surfs create -T %s -V %s %s'%(typestr,sizestr,vol_id)
        else:
            cmdstr='surfs create -T %s -V %s -P %s %s'%(typestr,sizestr,ipstr,vol_id)
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        return True
    
    def clone_vol(self,src_id,dst_id):
        cmdstr='surfs --pretty copy %s %s'%(src_id,dst_id)
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        return True
    
    def create_vol_from_snap(self,snap_id,vol_id):
        s_msg=self.get_snap_info(s_id)
        vol_size=s_msg['srcsize']
        size_G= sizeunit.Byte.toGigaByte(vol_size) + 1
        cmdstr='surfs snap_to_volume ' + snap_id + ' ' + vol_id + ' ' + size_G
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        return True
    
    def get_vol_size(self,vol_id):
        cmdstr='surfs --pretty volume %s'%vol_id
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        
        return rmsg['data']['size']
    
    def _get_pool_list(self):
        cmdstr='surfs info'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        
        return rmsg['data']['pools']
    
    def get_vol_used_size(self,vol_id):
        return '0' 
    
    def get_snap_info(self,snap_id):
        cmdstr='surfs snapinfo ' + snap_id
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)       
        return rmsg 
    
    def get_snap_exist_byvol(self,vol_id):
        poollist=self._get_pool_list()
        s_list=[]
        tstr=''
        for s in poollist:
            if s['connected'] is False:
                continue
            
            cmdstr='surfs snaplist ' + s['pool']
            ret,rslt=commands.getstatusoutput(cmdstr)
            if ret !=0:
                raise Exception('Error:%s'%rslt)
            rmsg=json.loads(rslt)
            if rmsg['success'] is False:
                raise Exception('Error:%s'%rslt)
            for x in rmsg['data']:
                if x['volume']== vol_id:
                    if str(x['ctime']) in tstr:
                        continue
                    else:
                        s_list.append(x)
                        tstr=tstr + ',' + str(x['ctime'])
               
        return s_list
    
    def get_after_snaps(self,vol_id,snap_id):
        snaps=self.get_snap_exist_byvol(vol_id)
        snap=self.get_snap_info(snap_id)
        afters=[]
        for x in snaps:
            if x['ctime'] > snap['data']['ctime']:
                afters.append(x)
        return afters
        
    
    def create_snapshot(self,vol_id,snap_id):
        cmdstr='surfs snap ' + vol_id + ' ' + snap_id 
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
    
    def delete_snapshot(self,snap_id):
        cmdstr = 'surfs delete ' + snap_id
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.warn("Failed to delete volume or snapshot[%s]"%vol_id)
            return False
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            if 'not found' in rmsg['message']:
                logger.warn(rmsg['message'])
                return False
            else:
                logger.warn("Failed to delete volume or snapshot[%s]"%vol_id)
                return False
        return True
            
    def rollback_from_snap(self,snap_id,vol_id):
        cmdstr='surfs snaprollback ' + vol_id + ' ' + snap_id
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
    
    def clone_image(self,image_id,vol_id):
        cmdstr='surfs image-clone ' + image_id + ' ' + vol_id
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt) 
    
    def delete_volume(self,vol_id):
        self.disexport_volume(vol_id)
        cmdstr = 'surfs delete ' + vol_id
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.warn("Failed to delete volume or snapshot[%s]"%vol_id)
            return False
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            logger.warn("Failed to delete volume or snapshot[%s]"%vol_id)
            return False
        return True
    
    def disexport_volume(self,vol_id):
        cmdstr = 'surfs disexport ' + vol_id
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            return False
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            return False       
    
    def export_target(self,initname,vol_name):
        cmdstr='surfs export ' + self.iqn_name + vol_name + ' ' + initname + ' a12345678:a12345678 ' + vol_name 
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        
        return rmsg['data']['ip']
    
    def _get_local_iscsi_initname(self):
        ret,result=commands.getstatusoutput('cat /etc/iscsi/initiatorname.iscsi')
        if ret >0:
            return  None
        if 'InitiatorName' in result and '=' in result:
            return result.split('=')[1].strip()
        else:
            return None 
    
    def export_root_target(self,initname,vol_name,poolname):
        cmdstr='surfs export ' + self.iqn_name + vol_name + ' ' + initname + ' a12345678:a12345678 ' + vol_name 
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        if os.path.exists(self.target_path) is False:
            commands.getstatusoutput('mkdir ' + self.target_path)
        ppath=os.path.join(self.target_path,poolname)
        if os.path.exists(ppath) is False:
            commands.getstatusoutput('mkdir ' + ppath)
        iscsi_name=self.iqn_name + vol_name
        self._connect_root_target(vol_name, rmsg['data']['ip'], iscsi_name, self.iscsi_port)
        self._link_target_to_rootpath(ppath, vol_name,rmsg['data']['ip'])
        
        return rmsg['data']['ip']
    
    def _find_target_path(self,volname):
        cmdstr='find /dev -type l -print0 | xargs --null file | grep -e ' + self.iqn_name + volname
        k=0
        while True:           
            ret,rslt=commands.getstatusoutput(cmdstr)       
            if ret !=0:
               k=k + 1
               if k < 5:
                   time.sleep(0.3)
                   continue
               else:
                   raise Exception('Error:%s'%rslt)
            return rslt           
   
    def _link_target_to_rootpath(self,rootpath,volname,poolip):
        linkstrs=self._find_target_path(volname)
        if len(linkstrs) ==0:
            return
        lun=self._parse_link_paths(linkstrs)
        iscsipath='/dev/disk/by-path/ip-' + poolip + ':' + self.iscsi_port + '-iscsi-' + self.iqn_name + volname + '-lun-' + lun
        cmdstr=''
        if volname in rootpath:
            cmdstr='ln -s ' + iscsipath + ' ' + rootpath
        else:                            
            cmdstr='ln -s ' + iscsipath + ' ' + rootpath + '/' + volname
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
    
    def _discovery_targets(self,st_ip,volname):
        cmdstr='iscsiadm -m discovery -t sendtargets -p ' + st_ip + ':' + self.iscsi_port
        k=0
        while k < 5:
            ret,rslt=commands.getstatusoutput(cmdstr)
            if ret !=0:
                k = k +1
                time.sleep(0.3)
                logger.debug('warning:%s'%rslt)
                continue
            else:
                if volname in rslt:
                    break
                else:
                    k= k + 1
                    time.sleep(0.3)
                    logger.debug('warning:%s'%rslt)
                    continue
        if k==5:
            raise Exception('Error:can not execute[%s]'%cmdstr)        
    
    def set_target_chap(self,st_ip,volname):
        iscsi_name=self.iqn_name + volname
        self._discovery_targets(st_ip,volname)
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -o update --name node.session.auth.authmethod --value=CHAP'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Error:%s'%rslt)
        
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -o update --name node.session.auth.username --value=a12345678'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Error:%s'%rslt)
        
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -o update --name node.session.auth.password --value=a12345678'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Error:%s'%rslt) 
        
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -l'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0: 
            raise Exception('Error:%s'%rslt)
        else:
            logger.debug('OK:%s'%rslt)                       
           
    def _connect_root_target(self,vol_name,st_ip,iscsi_name,iscsi_port):        
        self._discovery_targets(st_ip,vol_name)
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -o update --name node.session.auth.authmethod --value=CHAP'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -o update --name node.session.auth.username --value=a12345678'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -o update --name node.session.auth.password --value=a12345678'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)        
                   
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -l'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
    
    def clean_target_after_detach(self,pool,volname):
        
        iscsi_name=self.iqn_name + volname
        cmdstr='rm -f ' + self.target_path + '/' + pool + '/' + volname
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Error:%s'%rslt)
        
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -u'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Error:%s'%rslt)
        
        cmdstr='iscsiadm -m node -T ' + iscsi_name + ' -o delete'
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Error:%s'%rslt)
                
        cmdstr='surfs disexport ' + volname
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Error:%s'%rslt)
    
    def get_exprot_msg(self,vol_id):
        cmdstr='surfs getexport ' + vol_id
        k =0
        while True:
            ret,rslt=commands.getstatusoutput(cmdstr)
            if ret !=0:
                time.sleep(0.3)
                k = k +1
                continue
            if k > 5:
                return None            
            rmsg=json.loads(rslt)
            if rmsg['success'] is False:
                return None
            else:
                return rmsg["data"]
            
    def del_export_acl(self,volname):
        cmdstr='surfs delexportacl ' + self.iqn_name + volname + ' ' + self.init_name + ' ' + volname
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.debug('Error:%s'%rslt)       
    
    def start_vm_vol_resume(self,poolname,vol_id):
        eptmsg=self.get_exprot_msg(vol_id)
        storage_path=self.target_path + '/' + poolname + '/' + vol_id
        if eptmsg is None:
            self.export_root_target(self.init_name, vol_id, poolname)           
        else:
            if self.init_name == eptmsg['InitiatorName']:
                p_ip=self.get_volume_pool_ip(vol_id)
                if p_ip is None:
                    logger.debug('Can not get info of the volume[%s]'%vol_id)
                    return
                self._clean_overdue_link(storage_path)
                self._clean_overdue_target(self.iqn_name, vol_id)
                try:
                    self._discovery_targets(p_ip,vol_id)
                    self._connect_root_target(vol_id, p_ip, self.iqn_name + vol_id,self.iscsi_port)
                    self._link_target_to_rootpath(storage_path, vol_id, p_ip)  
                except:
                    self.export_root_target(self.init_name, vol_id, poolname)                                                          
            else:
                newip=self._check_target(self.iqn_name,
                                                   self.init_name, 
                                                   'a12345678:a12345678', 
                                                   vol_id, 
                                                   storage_path)
                self._clean_overdue_target(self.iqn_name ,vol_id)
                self._clean_overdue_link(storage_path)
                self._connect_root_target(vol_id,
                                            newip,
                                            self.iqn_name + vol_id,
                                            self.iscsi_port)
                self._link_target_to_rootpath(storage_path,vol_id,newip)
    
    def _parse_link_paths(self,linkstr):
        lines=linkstr.split('\n')
        for x in lines:
            if 'part' in x:
                continue
            return x.split('-lun-')[1].split(':')[0]
                
    def migrate_vm_prepare(self,poolname,volname):
        link_dir=self.target_path + '/' + poolname + '/' + volname
        commands.getstatusoutput("rm -f " + link_dir)
        '''
        linkstrs=''
        try:
            linkstrs=self._find_target_path(volname)
        except:
            pass
        '''
        self._clean_overdue_target(self.iqn_name, volname)
        self.del_export_acl(volname)
            
        self.export_root_target(self.init_name, volname, poolname)
    
    def migrate_vm_after(self,poolname,volname):
        link_dir=self.target_path + '/' + poolname + '/' + volname
        commands.getstatusoutput("rm -f " + link_dir)
        linkstrs=''
        try:
            linkstrs=self._find_target_path(volname)
        except:
            pass
        if len(linkstrs)> 0:
            self._clean_overdue_target(self.iqn_name, volname)
            self.del_export_acl(volname)
    
    def _excute_cmd(self,cmd_str,surfstype=True):
        k=0
        while True:
            ret,rslt=commands.getstatusoutput(cmd_str)
            if ret !=0:
                time.sleep(0.3)
                k = k +1
                if k > 5:
                    return None
                continue
            if surfstype is False:
                return rslt            
            rmsg=json.loads(rslt)
            if rmsg['success'] is False:
                return None
            else:
                return rmsg["data"]
    
    def check_vol_before_attach(self,vol_id,vol_size,vol_type,ipstr=None):
        if vol_size < 1:
            vol_size=1
        if vol_id is None:
            return
        v_type=self.back_type
        if vol_type is not None:
            v_type= vol_type
        cmdstr='surfs volume ' + vol_id
        if self._excute_cmd(cmdstr) is None:
            self.create_data_volume(vol_id, str(vol_size), v_type,ipstr)
            b=0
            while True:
                time.sleep(0.5)
                if self._excute_cmd(cmdstr) is None:
                    b = b +1
                    continue
                else:
                    break
                if b > 5:
                    break
    def get_vol_info(self,vol_id):
        cmdstr='surfs volume ' + vol_id
        return self._excute_cmd(cmdstr)
    
    def check_nodeip_result(self,vol_name):
        poolip=self.get_volume_pool_ip(vol_name)
        if poolip is None:
            return False
        ipmsg=self._excute_cmd('ip a', surfstype=False)
        if ipmsg is None:
            return False
        if poolip in ipmsg:
            return True
        else:
            return False
    
    def local_disk_link(self,fileio_path,vol_id,pool_name):
        cmdstr=''
        if os.path.exists(self.target_path + '/' + pool_name) is False:
            cmdstr='mkdir ' + self.target_path + '/' + pool_name
            self._excute_cmd(cmdstr, surfstype=False)
        storage_path=self.target_path + '/' + pool_name + '/' + vol_id
        cmdstr='rm -f ' + storage_path
        self._excute_cmd(cmdstr, surfstype=False)
        cmdstr='ln -s ' + fileio_path + ' ' + storage_path
        self._excute_cmd(cmdstr, surfstype=False)
                                                                                                                                                                                                                                    
class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None

class AttachDataVolRsp(AgentResponse):
    def __init__(self):
        super(AttachDataVolRsp,self).__init__()
        self.poolip=''
        self.iscsiport=''
        self.target=''
        self.lun=''
        self.devicetype='iscsi'

class InitRsp(AgentResponse):
    def __init__(self):
        super(InitRsp, self).__init__()
        self.fsid = None
        self.userKey = None

class DownloadRsp(AgentResponse):
    def __init__(self):
        super(DownloadRsp, self).__init__()
        self.size = None

class CpRsp(AgentResponse):
    def __init__(self):
        super(CpRsp, self).__init__()
        self.size = None
        self.actualSize = None

class CreateSnapshotRsp(AgentResponse):
    def __init__(self):
        super(CreateSnapshotRsp, self).__init__()
        self.size = None
        self.actualSize = None

class GetVolumeSizeRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

class PingRsp(AgentResponse):
    def __init__(self):
        super(PingRsp, self).__init__()
        self.operationFailure = False
        self.fsid=''
        self.poolclsmsg=''

class GetFactsRsp(AgentResponse):
    def __init__(self):
        super(GetFactsRsp, self).__init__()
        self.fsid = None

class GetVolumeSizeRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

def replyerror(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
            rsp = AgentResponse()
            rsp.success = False
            rsp.error = str(e)
            logger.warn(err)
            return jsonobject.dumps(rsp)
    return wrap

class SurfsAgent(object):

    INIT_PATH = "/surfs/primarystorage/init"
    CREATE_VOLUME_PATH = "/surfs/primarystorage/volume/createempty"
    DELETE_PATH = "/surfs/primarystorage/delete"
    CLONE_PATH = "/surfs/primarystorage/volume/clone"
    FLATTEN_PATH = "/surfs/primarystorage/volume/flatten"
    SFTP_DOWNLOAD_PATH = "/surfs/primarystorage/sftpbackupstorage/download"
    SFTP_UPLOAD_PATH = "/surfs/primarystorage/sftpbackupstorage/upload"
    ECHO_PATH = "/surfs/primarystorage/echo"
    CREATE_SNAPSHOT_PATH = "/surfs/primarystorage/snapshot/create"
    DELETE_SNAPSHOT_PATH = "/surfs/primarystorage/snapshot/delete"
    COMMIT_IMAGE_PATH = "/surfs/primarystorage/snapshot/commit"
    PROTECT_SNAPSHOT_PATH = "/surfs/primarystorage/snapshot/protect"
    ROLLBACK_SNAPSHOT_PATH = "/surfs/primarystorage/snapshot/rollback"
    UNPROTECT_SNAPSHOT_PATH = "/surfs/primarystorage/snapshot/unprotect"
    CP_PATH = "/surfs/primarystorage/volume/cp"
    DELETE_POOL_PATH = "/surfs/primarystorage/deletepool"
    GET_VOLUME_SIZE_PATH = "/surfs/primarystorage/getvolumesize"
    PING_PATH = "/surfs/primarystorage/ping"
    GET_FACTS = "/surfs/primarystorage/facts"
    ATTACH_VOLUME_PREPARE = "/surfs/primarystorage/attachprepare"
    DETACH_VOLUME_AFTER = "/surfs/primarystorage/detachafter"
    START_VM_BEFORE = "/surfs/primarystorage/startvmbefore"
    SURFS_MIGRATE_PREPARE = "/surfs/primarystorage/migrateprepare"
    SURFS_MIGRATE_AFTER = "/surfs/primarystorage/migrateafter"

    http_server = http.HttpServer(port=6731)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DELETE_PATH, self.delete)
        self.http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create)
        self.http_server.register_async_uri(self.CLONE_PATH, self.clone)
        self.http_server.register_async_uri(self.COMMIT_IMAGE_PATH, self.commit_image)
        self.http_server.register_async_uri(self.CREATE_SNAPSHOT_PATH, self.create_snapshot)
        self.http_server.register_async_uri(self.DELETE_SNAPSHOT_PATH, self.delete_snapshot)
        self.http_server.register_async_uri(self.PROTECT_SNAPSHOT_PATH, self.protect_snapshot)
        self.http_server.register_async_uri(self.UNPROTECT_SNAPSHOT_PATH, self.unprotect_snapshot)
        self.http_server.register_async_uri(self.ROLLBACK_SNAPSHOT_PATH, self.rollback_snapshot)
        self.http_server.register_async_uri(self.FLATTEN_PATH, self.flatten)
        self.http_server.register_async_uri(self.SFTP_DOWNLOAD_PATH, self.sftp_download)
        self.http_server.register_async_uri(self.SFTP_UPLOAD_PATH, self.sftp_upload)
        self.http_server.register_async_uri(self.CP_PATH, self.cp)
        self.http_server.register_async_uri(self.DELETE_POOL_PATH, self.delete_pool)
        self.http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_async_uri(self.GET_FACTS, self.get_facts)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.ATTACH_VOLUME_PREPARE,self.attach_datavol_prepare)
        self.http_server.register_async_uri(self.DETACH_VOLUME_AFTER,self.detach_datavol_after)
        self.http_server.register_async_uri(self.START_VM_BEFORE,self.start_vm_before)
        self.http_server.register_async_uri(self.SURFS_MIGRATE_PREPARE,self.migrate_vm_before)
        self.http_server.register_async_uri(self.SURFS_MIGRATE_AFTER,self.migrate_vm_after)
        self.fsid='surfsc48-2cef-454c-b0d0-b6e6b467c022'
        self.surfs_mgr = SurfsCmdManage()
    
    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = InitRsp()
        rsp.fsid = self.fsid
        self._set_capacity_to_response(rsp)
        rsp.userKey = "AQDVyu9VXrozIhAAuT2yMARKBndq9g3W8KUQvw=="
        return jsonobject.dumps(rsp)

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        xmsg=self._parse_install_path(cmd.installPath)
        pool=''
        vol_name=''
        if len(xmsg) == 2:
            pool=xmsg[0]
            vol_name=xmsg[1]
        if len(xmsg) == 3:
            pool=xmsg[1]
            vol_name=xmsg[2]

        self.surfs_mgr.delete_volume(vol_name)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def migrate_vm_after(self,req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rootmsg=cmd.rootinstallPath.split("/");
        datamsg=cmd.datainstallPath;
        rsp = AgentResponse()
        if self.surfs_mgr.init_name is None:
            rsp.success=False
            rsp.error='can not get local initorname'
        self.surfs_mgr.migrate_vm_after(rootmsg[2], rootmsg[3])
        if datamsg is None or len(datamsg)==0:
            return jsonobject.dumps(rsp)
        else:
            vdvls=vmsg.split(',')
            for x in vdvls:
                dvl=x.split(':')
                if len(dvl) !=2:
                    continue
                self.surfs_mgr.migrate_vm_after(dvl[0], dvl[1])        
        
        return jsonobject.dumps(rsp)         
    
    @replyerror
    def migrate_vm_before(self,req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rootmsg=cmd.rootinstallPath.split("/");
        datamsg=cmd.datainstallPath;
        rsp = AgentResponse()
        if self.surfs_mgr.init_name is None:
            rsp.success=False
            rsp.error='can not get local initorname'        
        devstrs=self.surfs_mgr.migrate_vm_prepare(rootmsg[2], rootmsg[3])
        
        if datamsg is None or len(datamsg)==0:
            return jsonobject.dumps(rsp)
        else:
            vdvls=vmsg.split(',')
            for x in vdvls:
                dvl=x.split(':')
                if len(dvl) !=2:
                    continue
                self.surfs_mgr.migrate_vm_prepare(dvl[0], dvl[1])            
        
        return jsonobject.dumps(rsp)
    
    @replyerror
    def start_vm_before(self,req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        xmsg=cmd.installPath.split('/')
        vmsg=cmd.volinstallPath
        rsp = AgentResponse()
        if self.surfs_mgr.init_name is None:
            rsp.success=False
            rsp.error='can not get local initorname'       
        self.surfs_mgr.start_vm_vol_resume(xmsg[2], xmsg[3])

        if vmsg is None or len(vmsg)==0:
            return jsonobject.dumps(rsp)
        else:
            vdvls=vmsg.split(',')
            for x in vdvls:
                dvl=x.split(':')
                if len(dvl) !=2:
                    continue
                if self.surfs_mgr.check_nodeip_result(dvl[1]) is True:
                    poolmsg=self.surfs_mgr.get_vol_info(dvl[1])
                    if poolmsg is None:
                        self.surfs_mgr.start_vm_vol_resume(dvl[0], dvl[1])
                    else:
                        fileio_dir='/' + poolmsg['pool'] + '/' + dvl[1] + '/fileio'
                        if os.path.exists(fileio_dir) is False:
                            self.surfs_mgr.start_vm_vol_resume(dvl[0], dvl[1])
                        else:
                            self.surfs_mgr.local_disk_link(fileio_dir,dvl[1],dvl[0])    
                else:                
                    self.surfs_mgr.start_vm_vol_resume(dvl[0], dvl[1])
                                                        
        return jsonobject.dumps(rsp)
    
    @replyerror
    def detach_datavol_after(self,req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp=AttachDataVolRsp()
        xmsg=cmd.installPath.split('/')
        if len(xmsg) != 4:
            rsp.success=False
            rsp.error='installPath[' + cmd.installPath + '] is error'
            return jsonobject.dumps(rsp)
        self.surfs_mgr.clean_target_after_detach(xmsg[2], xmsg[3])
        return jsonobject.dumps(rsp)
           
    @replyerror
    def attach_datavol_prepare(self,req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp=AttachDataVolRsp()
        xmsg=cmd.installPath.split('/')
        if len(xmsg) != 4:
            rsp.success=False
            rsp.error='installPath[' + cmd.installPath + '] is error'
            return jsonobject.dumps(rsp)
        self.surfs_mgr.check_vol_before_attach(xmsg[3], cmd.volsize, cmd.voltype,cmd.mgip)
        vol_ip=self.surfs_mgr.get_volume_pool_ip(xmsg[3])
        bsign=False
        if vol_ip == cmd.mgip:
            poolmsg=self.surfs_mgr.get_vol_info(xmsg[3])
            if poolmsg is None:
                bsign=True
            else:
                fileio_dir='/' + poolmsg['pool'] + '/' + xmsg[3] + '/fileio'
                if os.path.exists(fileio_dir) is False:
                    bsign=True
                else:
                    self.surfs_mgr.local_disk_link(fileio_dir, xmsg[3], xmsg[2])
                    rsp.devicetype='file'         
        else:
            bsign=True
            
        if bsign is True:
            self.surfs_mgr.export_root_target(self.surfs_mgr.init_name, xmsg[3], xmsg[2])
            self.surfs_mgr._find_target_path(xmsg[3])
              
        return jsonobject.dumps(rsp)
    
    @replyerror
    def create(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        _,pool,image_name = self._parse_install_path(cmd.installPath)

        size_G = sizeunit.Byte.toGigaByte(cmd.size) + 1
        size = "%dG" % (size_G)
        v_type=self.surfs_mgr.back_type
        try:
            v_type=getattr(cmd, 'poolcls')
        except:
            logger.warn('Can not get attribute:poolcls')
        #self.surfs_mgr.create_data_volume(image_name,size,v_type)
        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)
    
    @replyerror
    def clone(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        _,src_vol_id = self._parse_install_path(cmd.srcPath)
        _,pname,dst_vol_id = self._parse_install_path(cmd.dstPath)

        _,src_id,src_type=src_vol_id.split('@')
        if src_type == 'image':
            self.surfs_mgr.clone_image(src_id, dst_vol_id)
        else:
            self.surfs_mgr.clone_vol(src_vol_id,dst_vol_id)
        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def commit_image(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        _,_,s_id = self._parse_install_path(cmd.snapshotPath)
        _,_,v_id = self._parse_install_path(cmd.dstPath)
        self.surfs_mgr.create_vol_from_snap(s_id,v_id)
        rsp = CpRsp()
        rsp.size = self._get_file_size(dpath)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)
    
    @replyerror
    def create_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        do_create = True
        imagename, sp_name,pooltype = spath.split('@')
        xmsg=imagename.split('/')
        image_name=''
        if len(xmsg) == 2:
            image_name=xmsg[1]
        if len(xmsg) == 3:
            image_name=xmsg[2]
        rsp = CreateSnapshotRsp()
        if pooltype == 'image':
            pass
        else:
            if self.surfs_mgr.get_vol_info(image_name) is None:
                rsp.success=False
                rsp.error='The volume has never be attached to any vm'
                return jsonobject.dumps(rsp)

        if cmd.skipOnExisting:
            if pooltype == 'image':
                do_create = False
            else:
                snaps = self.surfs_mgr.get_snap_exist_byvol(image_name)
                for s in snaps:
                    do_create = False

        if do_create:
            self.surfs_mgr.create_snapshot(image_name,sp_name)

        
        if pooltype == 'image':
            rsp.size= self.surfs_mgr.get_iamge_size(sp_name)
        else:
            rsp.size = self.surfs_mgr.get_vol_size(image_name)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)
        xmsg=spath.split('@')
        sp_name=xmsg[1]
        rsp = AgentResponse()
        try:
            self.surfs_mgr.delete_snapshot(sp_name)
            self._set_capacity_to_response(rsp)
        except Exception, e:
            logger.debug('%s' % str(e))
            rsp.success = False
            rsp.error = str(e)
            raise
        return jsonobject.dumps(rsp)

    @replyerror
    def protect_snapshot(self, req):
        rsp = AgentResponse()
        return jsonobject.dumps(rsp)

    @replyerror
    def unprotect_snapshot(self, req):
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def rollback_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        xmsg=spath.split('@')
        image=xmsg[0].split('/')[2]
        snap=xmsg[1]
        afters = self.surfs_mgr.get_after_snaps(image,snap)
        rsp = AgentResponse()

        if (len(afters) > 0):
            afters.reverse()
            rsp.success = False
            rsp.error = 'If you want to rollback , please delete the later snapshots [%s]' % (afters)
        else:
            self.surfs_mgr.rollback_from_snap(snap,image)
            self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    @replyerror
    def flatten(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.path)

        rsp = AgentResponse()
        rsp.success = False
        rsp.error = 'unsupported flatten'
        return jsonobject.dumps(rsp)

    @replyerror
    def sftp_upload(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        src_path = self._normalize_install_path(cmd.primaryStorageInstallPath)
        prikey_file = linux.write_to_temp_file(cmd.sshKey)
        bs_folder = os.path.dirname(cmd.backupStorageInstallPath)

        rsp = AgentResponse()
        rsp.success = False
        rsp.error = 'unsupported SimpleSftpBackupStorage,  only supports surfs backupstorage'
        return jsonobject.dumps(rsp)


    @replyerror
    @rollback
    def sftp_download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        hostname = cmd.hostname
        prikey = cmd.sshKey
        _,pool, image_name = self._parse_install_path(cmd.primaryStorageInstallPath)
        tmp_image_name = 'tmp-%s' % image_name
        prikey_file = linux.write_to_temp_file(prikey)

        rsp = AgentResponse()
        rsp.success = False
        rsp.error = 'unsupported SimpleSftpBackupStorage,  only supports surfs backupstorage'
        #self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def cp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        _,_,s_id = self._parse_install_path(cmd.srcPath)
        _,_,v_id = self._parse_install_path(cmd.dstPath)
        self.surfs_mgr.clone_vol(s_id,v_id)
              
        rsp = CpRsp()
        rsp.size = self.surfs_mgr.get_vol_size(v_id)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_pool(self, req):
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        _,_,vol_id = self._parse_install_path(cmd.installPath)
        rsp = GetVolumeSizeRsp()
        rsp.size = self.surfs_mgr.get_vol_size(vol_id)
        rsp.actualSize = self.surfs_mgr.get_vol_used_size(vol_id)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = PingRsp()
        rsp.fsid=self.fsid
        poolsmsg=''
        if cmd.testImagePath:
            rmsg=self.surfs_mgr.get_pool_msg()
            if rmsg is None:
                rsp.success = False
                rsp.operationFailure = True
                rsp.error = "can not do surfs connect"
                logger.debug("%s" % rsp.error)
            else:
                if len(rmsg)> 0:
                    for rsg in rmsg:
                        status='True'
                        if rsg['success'] is False:
                            rsp.success = True
                            rsp.operationFailure = False
                            rsp.error = "Surfs is ready,but pool is breaken"
                            status='false'
                            logger.debug("Surfs is ready,but pool is breaken")
                        if poolsmsg=='':
                            poolsmsg=rsg['class'] + ':' + str(rsg['total']) + ':' + str(rsg['free']) + ':' + status
                        else:
                            pools=poolsmsg.split(',')
                            tmpmsg=''
                            if rsg['class'] + ':' in poolsmsg:
                                for xl in pools:
                                    pl=xl.split(':')
                                    if rsg['class']== pl[0]:
                                        pl[1]=str(long(pl[1]) + rsg['total'])
                                        pl[2]=str(long(pl[2]) + rsg['free'])
                                        pl[3]=status
                                    if tmpmsg=='':
                                        tmpmsg=pl[0] + ':' + pl[1]  + ':' + pl[2]  + ':' + pl[3]
                                    else:
                                        tmpmsg=tmpmsg + pl[0] + ':' + pl[1]  + ':' + pl[2]  + ':' + pl[3]
                                poolsmsg=tmpmsg
                            else:
                                poolsmsg=poolsmsg + ',' + rsg['class'] + ':' + str(rsg['total']) + ':' + str(rsg['free']) + ':' + status
                    rsp.poolclsmsg=poolsmsg     
                else:
                    rsp.success = False
                    rsp.operationFailure = True
                    rsp.error = "Surfs is ready,but pool is Null"
                    logger.debug("Surfs is ready,but pool is Null") 

        return jsonobject.dumps(rsp)
    

    def _parse_install_path(self, path):
        return self._normalize_install_path(path).split('/')       

    def _set_capacity_to_response(self, rsp):
        cmdstr='surfs connect'
        total = 0
        used = 0
        rmsg=self.surfs_mgr.get_pool_msg()
        for pl in rmsg:
            if pl["success"] is True:
                total=total + pl["total"]
                used=used + pl["used"]
        rsp.totalCapacity = total
        rsp.availableCapacity = total - used

    def _get_file_size(self, path):
        pass

    def _get_file_actual_size(self, path):
        pass

    @replyerror
    def get_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetFactsRsp()
        rsp.fsid = self.fsid
        return jsonobject.dumps(rsp)
    
    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    def _normalize_install_path(self, path):
        return path.lstrip('surfs:').lstrip('//')


class SurfsDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(SurfsDaemon, self).__init__(pidfile)

    def run(self):
        self.agent = SurfsAgent()
        self.agent.http_server.start()

