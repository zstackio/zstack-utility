# -*- coding: UTF-8 -*-
import sys
sys.path.append("/var/lib/zstack/virtualenv/zstackctl/lib/python2.7/site-packages/")
sys.path.append("/usr/lib/python2.7/site-packages/")
sys.path.append("/usr/lib64/python2.7/site-packages/")

try:
    from influxdb import InfluxDBClient
except ImportError:
    import importlib
    try:
        importlib.import_module('influxdb==5.1.0')
    except ImportError:
        import pip
        pip.main(['install', 'influxdb==5.1.0'])
    finally:
        globals()['influxdb'] = importlib.import_module('influxdb')
        from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError
import base64
import os
import threading
from threading import Thread
from Crypto.Cipher import AES
from Crypto.Util.py3compat import *
from hashlib import md5
import socket
import json
import MySQLdb
import time
import datetime
from commands import getstatusoutput
# pip install influxdb==5.1.0


client = InfluxDBClient(host='localhost', port=8086, database='zstack')

MigrateIns = {"zstack.zstack.audits": "AuditsVO", "zstack.messages.events": "EventRecordsVO",
              "zstack.messages.alarms": "AlarmRecordsVO", "zstack.zstack.events": "EventRecordsVO",
              "zstack.zstack.alarms": "AlarmRecordsVO"}


class Params(dict):
    def __init__(self, *args, **kw):
        dict.__init__(self, *args, **kw)

    def __getattr__(self, key):
        if key not in self:
            return None
        value = self[key]
        if isinstance(value, dict):
            value = Params(value)
        if isinstance(value, list):
            value = [Params(item) if isinstance(item, dict) else item for item in value]
        return value

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        del self[key]


def dicttoobj(func):
    def convert(d):
        if isinstance(d, (list, tuple)):
            return [Params(i) for i in d]
        if not isinstance(d, dict):
            return d
        return Params(d)

    def warp(*args, **kwargs):
        res = func(*args, **kwargs)
        return convert(res)

    return warp


class DBInfo(object):
    __species = None
    __first_init = True

    def __init__(self, passwd=None, host=None):
        if self.__first_init:
            if passwd is not None:
                self.host = host if host else '127.0.0.1'
                self.user = 'root'
                self.passwd = passwd
                self.port = '3306'
            else:
                self.init_mysql()
            self.__class__.__first_init = False

    def __new__(cls, *args, **kwargs):
        if cls.__species == None:
            cls.__species = object.__new__(cls)
        return cls.__species

    def init_mysql(self):
        import getpass
        if getpass.getuser() == "root":
            print "get db info by zstack-ctl way!"
            from zstackctl.ctl import Ctl
            ctl = Ctl()
            ctl.locate_zstack_home()
            self.host, self.port, self.user, self.passwd = ctl.get_live_mysql_portal()
        else:
            print "get db info by script way!"
            self.host, self.port, self.user, self.passwd = get_db_info()

    @property
    def get_mysql_info(self):
        return self.host, self.port, self.user, self.passwd


class DBUtil:
    def __init__(self):
        self.host, self.port, self.user, self.password = DBInfo().get_mysql_info

    def _connection(self):
        conn = MySQLdb.connect(host=self.host, port=int(self.port), user=self.user, passwd=self.password,
                               charset="utf8", connect_timeout=5)
        return conn

    def ping(self):
        try:
            self.do_select_fetchone("select 1")
        except MySQLdb.Error as e:
            print_red(u"连接mysql失败 :%s " % str(e))
            raise e

    @dicttoobj
    def do_select_fetchall(self, sqlstr, args=None, as_dict=True):
        result = []
        conn = self._connection()
        try:
            if as_dict:
                cursor = conn.cursor(MySQLdb.cursors.DictCursor)
            else:
                cursor = conn.cursor()
            cursor.execute(sqlstr, args)
            rows = cursor.fetchall()
            for row in rows:
                result.append(row)
            cursor.close()
        finally:
            if conn:
                conn.close()
        return result

    def do_select_fetchone(self, sqlstr, args=None):
        result = None
        conn = self._connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sqlstr, args)
            row = cursor.fetchone()
            if row is not None and len(row) > 0:
                result = row[0]
            cursor.close()
        except MySQLdb.Error as e:
            print_red(str(e))
            raise e
        finally:
            if conn:
                conn.close()
        return result

    def do_execute(self, sqlstr):
        conn = self._connection()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        try:
            cursor.execute(sqlstr)
            conn.commit()
            cursor.close()
        except MySQLdb.Error as e:
            raise e
        finally:
            if conn:
                conn.close()

    def do_execute_safely(self, sqlstr, args=None):
        conn = self._connection()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        try:
            cursor.execute(sqlstr, args)
            conn.commit()
            cursor.close()
        except MySQLdb.Error as e:
            print e.message
            raise e
        finally:
            if conn:
                conn.close()

    def do_batch_insert(self, conn, cursor, sqlstr, args=None):
        try:
            cursor.executemany(sqlstr, args)
            conn.commit()
        except MySQLdb.Error as e:
            print e.message
            raise e


def parseUTCStrToTimestamp(utcStr):
    try:
        datetime_obj = datetime.datetime.strptime(utcStr, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        datetime_obj = datetime.datetime.strptime(utcStr, "%Y-%m-%dT%H:%M:%SZ")
    return long(time.mktime(datetime_obj.timetuple()) * 1000.0 + datetime_obj.microsecond / 1000.0)

def safe_str(obj):
    try:
        return str(obj)
    except UnicodeEncodeError:
        return obj.encode('ascii', 'ignore').decode('ascii')
    return ""


class AuditsVO:

    def __init__(self, influxdb):
        self.influxdb = influxdb
        self.mysqldb = "zstack.AuditsVO"
        self.sql_tmpl_safe = "insert into zstack.AuditsVO (`createTime`, `apiName`, `clientBrowser`, `clientIp`, `duration`, `error`, `operator`, `requestDump`,`resourceType`,`resourceUuid`,`responseDump`, `success`)" \
                   " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        self.column = ['createTime', 'apiName', 'clientBrowser', 'clientIp', 'duration', 'error', 'operator', 'requestDump','resourceType','resourceUuid','responseDump', 'success']

    def process_influxdb_data(self, data):
        if data.has_key("requestDump"):
            reqData = json.loads(data.get('requestDump'))
            if reqData.has_key("headers"):
                reqData.pop("headers")
            data['requestDump'] = safe_str(json.dumps(reqData))
        if data.has_key("responseDump"):
            resData = json.loads(data.get('responseDump'))
            if resData.has_key("headers"):
                resData.pop("headers")
            # if resData.get("error"):
            #     if resData.get("error").get("details"):
            #         resData['error']['details'] = resData['error']['details'].replace("'", "\\'")
                #resData['error'] = {k: v.replace("'", "\\\'").replace("\"", "\\\"") for k, v in resData['error'].iteritems()}
                #resData['error'] = resData['error'].replace("'", "\\\'").replace("\"", "\\\"")
            data['responseDump'] = safe_str(json.dumps(resData))
        if data.has_key("success"):
            data['success'] = int(data.get("success") == "success")
        if data.has_key("time"):
            data['createTime'] = parseUTCStrToTimestamp(data.get('time'))
        # if data.has_key("error"):
        #     data['error'] = safe_str(data['error']).replace("'", "\\\'").replace("\"", "\\\"")
            #data['error'] = safe_str(data['error']).replace("'", "\"")
        return data


class EventRecordsVO:

    def __init__(self, influxdb):
        self.influxdb = influxdb
        self.mysqldb = "zstack.EventRecordsVO"
        self.column = ['createTime', 'accountUuid', 'dataUuid', 'emergencyLevel', 'name', 'error', 'labels', 'namespace', 'readStatus', 'resourceId', 'resourceName', 'subscriptionUuid']
        self.sql_tmpl_safe = "insert into zstack.EventRecordsVO (`createTime`, `accountUuid`, `dataUuid`, `emergencyLevel`, `name`, `error`, `labels`, `namespace`,`readStatus`,`resourceId`,`resourceName`, `subscriptionUuid`)" \
                   " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"

    def process_influxdb_data(self, data):
        label_map = {i : data[i] for i in data if ':::' in i and data[i] != None}
        if len(label_map) > 0:
            label_map = {i.split(':::')[-1]: label_map[i] for i in label_map}
            data['label'] = safe_str(json.dumps(label_map))
        if data.has_key("readStatus"):
            data['readStatus'] = int(data.get("readStatus") == "Read")
        if data.has_key("time"):
            data['createTime'] = parseUTCStrToTimestamp(data.get('time'))
        # if data.has_key("error"):
        #     data['error'] = safe_str(data['error']).replace("'", "\\\'").replace("\"", "\\\"")
            #data['error'] = safe_str(data['error']).replace("'", "\"")
        return data


class AlarmRecordsVO:

    def __init__(self, influxdb):
        self.influxdb = influxdb
        self.mysqldb = "zstack.AlarmRecordsVO"
        self.column = ['createTime', 'accountUuid', 'alarmName', 'alarmStatus', 'alarmUuid', 'comparisonOperator', 'context', 'dataUuid','emergencyLevel','labels','metricName', 'metricValue', 'namespace', 'period', 'readStatus', 'resourceType', 'resourceUuid', 'threshold']
        self.sql_tmpl_safe = "insert into zstack.AlarmRecordsVO (`createTime`, `accountUuid`, `alarmName`, `alarmStatus`, `alarmUuid`, `comparisonOperator`, `context`, `dataUuid`,`emergencyLevel`,`labels`,`metricName`, `metricValue`, `namespace`, `period`, `readStatus`, `resourceType`, `resourceUuid`, `threshold`)" \
                   " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"

    def process_influxdb_data(self, data):
        if data.has_key("requestDump"):
            reqData = json.loads(data.get('requestDump'))
            if reqData.has_key("headers"):
                reqData.pop("headers")
            data['requestDump'] = safe_str(json.dumps(reqData))
        if data.has_key("responseDump"):
            resData = json.loads(data.get('responseDump'))
            if resData.has_key("headers"):
                resData.pop("headers")
            # if resData.get("error"):
            #     if resData.get("error").get("details"):
            #         resData['error']['details'] = resData['error']['details'].replace("'", "\\'")
                #resData['error'] = {k: v.replace("'", "\\\'").replace("\"", "\\\"") for k, v in resData['error'].iteritems()}
                #resData['error'] = resData['error'].replace("'", "\\\'").replace("\"", "\\\"")
            data['responseDump'] = safe_str(json.dumps(resData))
        if data.has_key("readStatus"):
            data['readStatus'] = int(data.get("readStatus") == "Read")
        if data.has_key("time"):
            data['createTime'] = parseUTCStrToTimestamp(data.get('time'))
        # if data.has_key("error"):
        #     data['error'] = safe_str(data['error']).replace("'", "\\\'").replace("\"", "\\\"")
            #data['error'] = safe_str(data['error']).replace("'", "\"")
        return data


class Controller(object):
    _instance_lock = threading.Lock()

    def __init__(self):
        self.status = ""

    def __new__(cls, *args, **kwargs):
        if not hasattr(Controller, "_instance"):
            with Controller._instance_lock:
                if not hasattr(Controller, "_instance"):
                    Controller._instance = object.__new__(cls)
        return Controller._instance

    def start(self):
        self.status = "start"

    def stop(self):
        self.status = "stop"

    def pause(self):
        self.status = "stop"

    def error(self):
        self.status = "stop"


class MigrateAction(Thread):

    def __init__(self, obj, controller, query_num, dry_run):
        super(MigrateAction, self).__init__()
        self.mysql_obj = obj
        self.query_num = query_num
        self.controller = controller
        self.errorInfo = ""
        self.finish = ""
        self.queue = []
        self.dry_run = dry_run
        self.startTime = DBUtil().do_select_fetchone("select minCreateTime from zstack.MigrateInfluxDB where tableName='%s'" % self.mysql_obj.influxdb)
        self.endTime = DBUtil().do_select_fetchone("select maxCreateTime from zstack.MigrateInfluxDB where tableName='%s'" %  self.mysql_obj.influxdb)
        self.rangeTime = parseUTCStrToTimestamp(self.endTime) - parseUTCStrToTimestamp(self.startTime)
        self.baseTime = parseUTCStrToTimestamp(self.startTime)

    def __repr__(self):
        return "MigrateAction-Thread-%s" % self.mysql_obj.__class__.__name__

    def caclulate_process(self, last_time):
        return float("%.4f" % (float((parseUTCStrToTimestamp(last_time) - self.baseTime)) / self.rangeTime)) * 100

    def run(self):
        print "%s tread run!!!!" % self.mysql_obj.__class__.__name__
        conn = DBUtil()._connection()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        start_time = time.time()
        count = 0
        while self.controller.status == "start" and self.errorInfo == "" and self.finish != "done":
            last_time = DBUtil().do_select_fetchone("select lastMigrateDataCreateTime from zstack.MigrateInfluxDB where tableName='%s'" % self.mysql_obj.influxdb)
            print_blue("migrate influxdb table %s to mysql table %s percentage completion  %d%%" % (
            self.mysql_obj.influxdb, self.mysql_obj.mysqldb, self.caclulate_process(last_time)))
            latest_influxdb_sql = "SELECT * FROM %s WHERE time > '%s' ORDER BY time LIMIT %d" % (
                self.mysql_obj.influxdb, last_time, self.query_num)
            if count == 0:
                latest_influxdb_sql = "SELECT * FROM %s WHERE time >= '%s' ORDER BY time LIMIT %d" % (
                self.mysql_obj.influxdb, last_time, self.query_num)
            try:
                prepare_migrate_influxdb_data = client.query(latest_influxdb_sql)
            except InfluxDBClientError as e:
                print "query influxdb %s error : %s" % (self.mysql_obj.influxdb, str(e))
                self.errorInfo = str(e)
                self.finish = "error"
                break
            # prepare_migrate_influxdb_data = client.query("SELECT * FROM %s WHERE time > '%s' ORDER BY time  LIMIT %d" % (self.mysql_obj.influxdb, last_time, 10))
            count += 1
            if len(self.queue) == 0:
                if 'series' in prepare_migrate_influxdb_data.raw and \
                        len(prepare_migrate_influxdb_data.raw['series'][0]['values']) > 0:
                    print "get influxdb data length %d" % len(prepare_migrate_influxdb_data.raw['series'][0]['values'])
                    for data in prepare_migrate_influxdb_data.get_points():
                    #for data in prepare_migrate_influxdb_data.get():
                        data = self.mysql_obj.process_influxdb_data(data)
                        #print data
                        #mysql_sql_str = self.mysql_obj.sql_tmpl.format(**data)
                        #self.queue.append([mysql_sql_str, data])
                        self.queue.append(data)
                else:
                    retry = client.query(latest_influxdb_sql)
                    if 'series' not in retry.raw:
                        DBUtil().do_execute("update zstack.MigrateInfluxDB set migrateStatus='%s'where tableName='%s'"
                                            % ("done", self.mysql_obj.influxdb))
                        self.finish = "done"
                print "producer new mysql data %d" % len(self.queue)
            else:
                lastSuccessRecord = self.queue[len(self.queue)-1]
                many_args = ([i.get(j) for j in self.mysql_obj.column] for i in self.queue)
                print_green(u"insert mysql数据占用内存大小 %d" % sys.getsizeof(many_args))
                if self.dry_run:
                    print "%s %s" % (self.mysql_obj.sql_tmpl_safe, many_args)
                else:
                    try:
                        DBUtil().do_batch_insert(conn, cursor, self.mysql_obj.sql_tmpl_safe, many_args)
                    except MySQLdb.Error as e:
                        print_red("insert %s data error: %s" % (self.mysql_obj.__class__.__name__, str(e)))
                        self.errorInfo = str(e)
                        break
                # for idx, influxPointData in enumerate(self.queue):
                #     try:
                #         args = [influxPointData.get(i) for i in self.mysql_obj.column]
                #         DBUtil().do_execute_safely(self.mysql_obj.sql_tmpl_safe, args)
                #     except MySQLdb.Error as e:
                #         print "error insert data info"
                #         print e
                #         print influxPointData
                #         lastSuccessRecord = influxPointData
                #         if idx > 0:
                #             lastSuccessRecord = self.queue[idx-1]
                #         self.errorInfo = e.message
                #         print "migrate influxdb record error : "+e.message
                #         break
                self.queue = []
                #print "the lastest insert success InfluxDB data:" + json.dumps(lastSuccessRecord)
                print "#"*20
                # print type(lastSuccessRecord['time'])
                # print "update zstack.MigrateInfluxDB set lastMigrateDataCreateTime='%s',lastMigrateDataRecord='%s' where tableName='%s'"%(lastSuccessRecord['time'], json.dumps(lastSuccessRecord), self.mysql_obj.influxdb)
                # updateSQL =  "update zstack.MigrateInfluxDB set lastMigrateDataCreateTime='%s',lastMigrateDataRecord='%s' where tableName='%s'"%(lastSuccessRecord['time'], json.dumps(lastSuccessRecord), self.mysql_obj.influxdb)
                if self.errorInfo:
                    print self.errorInfo
                    # updateSQL = "update zstack.MigrateInfluxDB set lastMigrateDataCreateTime='%s',lastMigrateDataRecord='%s',error='%s' where tableName='%s'" % (
                    # lastSuccessRecord['time'], json.dumps(lastSuccessRecord), self.errorInfo[0], self.mysql_obj.influxdb)
                    print (lastSuccessRecord['time'], json.dumps(lastSuccessRecord), self.errorInfo, self.mysql_obj.influxdb)
                    DBUtil().do_execute_safely(
                        "update zstack.MigrateInfluxDB set lastMigrateDataCreateTime=%s,lastMigrateDataRecord=%s,error=%s where tableName=%s",
                        (lastSuccessRecord['time'], json.dumps(lastSuccessRecord), self.errorInfo, self.mysql_obj.influxdb))
                else:
                    DBUtil().do_execute_safely("update zstack.MigrateInfluxDB set lastMigrateDataCreateTime=%s,lastMigrateDataRecord=%s where tableName=%s", (lastSuccessRecord['time'], json.dumps(lastSuccessRecord), self.mysql_obj.influxdb))

            #time.sleep(1)
        if conn:
            cursor.close()
            conn.close()
        if self.errorInfo:
            DBUtil().do_execute_safely("update zstack.MigrateInfluxDB set error=%s where tableName=%s",
                (self.errorInfo, self.mysql_obj.influxdb))
        end_time = time.time()
        print "total time: %d" % (end_time - start_time)


def init(args):
    result = DBUtil().do_select_fetchone("SELECT table_name FROM information_schema.TABLES WHERE table_name ='MigrateInfluxDB'")
    if result is None:
        create_mysql_meta_table()
        init_mysql_meta_table(args.start)
    check_init_success()


def create_mysql_meta_table():
    create_table_sql = '''
                CREATE TABLE IF NOT EXISTS `zstack`.`MigrateInfluxDB` (
                    `tableName` varchar(64) DEFAULT NULL,
                    `maxCreateTime` varchar(256)  NOT NULL comment "最新记录时间",
                    `minCreateTime` varchar(256)  NOT NULL comment "最老记录时间",
                    `lastMigrateDataCreateTime` varchar(256)  NOT NULL,
                    `lastMigrateDataRecord` text,
                    `migrateStatus` varchar(64) DEFAULT NULL,
                    `error` text
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8;
            '''
    DBUtil().do_execute(create_table_sql)


def init_mysql_meta_table(start):
    sql_templ = "insert into zstack.MigrateInfluxDB (`tableName`, `maxCreateTime`, `minCreateTime`, `lastMigrateDataCreateTime`) values (%s, %s, %s, %s)"
    for table in MigrateIns:
        max_time_record = client.query("SELECT * FROM %s ORDER BY time DESC LIMIT 1" % table)
        max_time = [i['time'] for i in max_time_record.get_points()][0]
        min_time_record = client.query("SELECT * FROM %s ORDER BY time LIMIT 1" % table)
        min_time = [i['time'] for i in min_time_record.get_points()][0]
        if start == "full":
            DBUtil().do_execute_safely(sql_templ, (table, max_time, min_time, min_time))
        else:
            lastMigrateDate = (datetime.datetime.utcnow() - datetime.timedelta(days=int(start))).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ")
            if lastMigrateDate > max_time:
                print_red(u"迁移指定的influxdb历史数据开始时间不能晚于influxdb中最近一条记录的创建时间")
                DBUtil().do_execute("drop table zstack.MigrateInfluxDB")
                exit(1)
            DBUtil().do_execute_safely(sql_templ, (table, max_time, lastMigrateDate, lastMigrateDate))


def init_influxdb_info():
    from copy import deepcopy
    base_influxdb_map = deepcopy(MigrateIns)
    for table in base_influxdb_map:
        try:
            res = client.query("SELECT COUNT(*) FROM %s ORDER BY time DESC LIMIT 1" % table)
            if len(res.keys()) == 0:
                MigrateIns.pop(table)
                continue
        except InfluxDBClientError as e:
            print_red(str(e))
            MigrateIns.pop(table)
            continue


def check_init_success():
    flag = True
    for table in MigrateIns:
        try:
            result = DBUtil().do_select_fetchone("select tableName from zstack.MigrateInfluxDB where tableName='%s'" % table)
            if result is None:
                print_red(u"迁移记录表influx table: %s 数据初始化未成功! 请执行初始化步骤 -h 查看帮助 " % table)
                flag = False
        except MySQLdb.Error as e:
            print_red(u"查询迁移记录表zstack.MigrateInfluxDB出错: %s ,请执行初始化步骤 -h 查看帮助" % str(e))
            exit(1)
    if not flag:
        exit(1)
    print_green(u"迁移记录表数据初始化完成!")


def rollback():
    result = DBUtil().do_select_fetchone(
        "SELECT table_name FROM information_schema.TABLES WHERE table_name ='MigrateInfluxDB'")
    if result is None:
        print_green(u"未迁移过influxdb数据，不需要回滚!")
        exit(0)
    for influx_table, mysql_table in MigrateIns.iteritems():
        influx_last_time = DBUtil().do_select_fetchone("select maxCreateTime from zstack.MigrateInfluxDB where tableName='%s'" % influx_table)
        assert influx_last_time != "", print_red(u"获取influxdb迁移历史数据最近时间失败")
        last_time_stamp = parseUTCStrToTimestamp(influx_last_time)
        DBUtil().do_execute("DELETE FROM zstack.%s where createTime <= %d " % (mysql_table, last_time_stamp))
        print_green(u"删除 %s 表中迁移过来的历史数据" % mysql_table)
        count = DBUtil().do_select_fetchone("select count(*) from zstack.%s where createTime <= %d " % (mysql_table, last_time_stamp))
        assert count == 0, print_red(u"删除influxdb迁移完成数据失败")
    DBUtil().do_execute("drop table zstack.MigrateInfluxDB")
    print_green(u"回滚迁移的influxdb历史数据完成")


def get_max_allowed_packet():
    res = DBUtil().do_select_fetchall("show global variables like 'max_allowed_packet'")
    if len(res) > 0:
        return int(res[0].Value)
    return 0


def set_max_allowed_packet(size=67108864):
    try:
        DBUtil().do_execute("set global max_allowed_packet=%d" % size)
    except MySQLdb.Error as e:
        print_red(u"修改mysql参数出错 %s,请指定root密码执行 -p 查看帮助-h" % str(e))
        exit(1)

def rollback_max_allowed_packet():
    if os.path.exists(".mysql_max_allowed_packet"):
        with open('.mysql_max_allowed_packet') as f:
            myqsl_max_allowed_packet_config = f.readline()
        set_max_allowed_packet(int(myqsl_max_allowed_packet_config))


def caculate_allow_batch_insert(num, origin_global_config):
    if float(num)/(origin_global_config/1024/1024) > 400:
        print_red(u"你现在指定的单批插入次大于mysql配置的max_allowed_packet上限，容易迁移失败，"
                  u"请调整-n参数或者指定-p mysql root 密码, -h 查看帮助")
        exit(1)


def migrate(args):
    DBInfo(args.passwd, args.host)
    DBUtil().ping()
    origin_global_config = get_max_allowed_packet()
    if args.passwd:
        if origin_global_config < 67108864: #64m
            if not os.path.exists(".mysql_max_allowed_packet"):
                with open(".mysql_max_allowed_packet", "w") as f:
                    f.write(str(origin_global_config))
            set_max_allowed_packet()
    else:
        if not args.dry:
            caculate_allow_batch_insert(args.num, origin_global_config)
    if args.init:
        if args.start is None:
            print_red(u"请添加参数 -s=${输入数字，或者full} -h help查看帮助")
            exit(1)
        init(args)
    else:
        check_init_success()
    get_migrate_time(int(args.num))
    controler = Controller()
    controler.start()
    migrateObjs = DBUtil().do_select_fetchall("select * from zstack.MigrateInfluxDB")
    print migrateObjs
    migratelist = []
    for obj in migrateObjs:
        if obj.tableName in MigrateIns.keys() and obj.migrateStatus != 'done':
            migratelist.append(MigrateAction(eval(MigrateIns[obj.tableName])(obj.tableName), controler, int(args.num),
                                             args.dry))
    print migratelist
    if len(migratelist) > 0:
        for t in migratelist:
            t.setDaemon(True)
            t.start()
        for j in migratelist:
            j.join()
    if os.path.exists(".mysql_max_allowed_packet"):
        set_max_allowed_packet(origin_global_config)
        os.remove(".mysql_max_allowed_packet")
    print_green("finish migrating!")


def get_migrate_time(size):
    count_list = []
    try:
        for db in MigrateIns:
            count = client.query("SELECT count(*) FROM %s" % db)
            if len(count) > 0:
                count_list.append(max([i for i in count._get_series()[0]['values'][0] if type(i) == int]))
    except InfluxDBClientError as e:
        print str(e)
    except Exception as e:
        print e.message
    if len(count_list) > 0:
        max_table_count = max(count_list)
        print_green(u"本次迁移任务最大记录: %d " % max_table_count)
        print_green(u"指定单次迁移 %d 条，预估迁移时间: %d 秒" % (size , max_table_count/size))


def check():
    if not status_influxdb():
        start_influxdb()
    assert status_influxdb(), "influxdb server status is not running, please check !"
    print_green(u"Influx db 服务状态正常!")
    assert status_mysql(), "mysql db server status is not running, please check !"
    print_green(u"MySQL db 服务状态正常!")
    code, influxdb_data_size = getstatusoutput("du -sh -k /var/lib/zstack/influxdb/data/zstack | awk '{print $1}'")
    can_caculate = True
    try:
        print_green(u"influx db数据总量: %d kb" % int(influxdb_data_size))
    except ValueError:
        can_caculate = False
        print_red("获取influx db数据总量失败: %s" % safe_str(influxdb_data_size))
    code1, mysqlavailable = getstatusoutput("df -hl -k /var/lib/mysql/ | awk '{print $4}' | sed -n '2p'")
    try:
        print_green(u"mysql 所在盘可用空间: %d kb" % int(mysqlavailable))
    except ValueError:
        can_caculate = False
        print_red("获取mysql所在盘可用空间失败: %s" % safe_str(mysqlavailable))
    if can_caculate:
        if int(influxdb_data_size) * 1.5 > int(mysqlavailable):
            print_red(u"迁移容量检查失败! mysql 剩余空间不足以迁移influxdb全量历史数据,请检查")
            exit(1)
        print_green(u"迁移容量检查通过!")
    else:
        print_red(u"迁移容量数据获取失败!")
    if code == 0:
        count_list = []
        try:
            for db in MigrateIns:
                count = client.query("SELECT count(*) FROM %s" % db)
                if len(count) > 0:
                    count_list.append(max([i for i in count._get_series()[0]['values'][0] if type(i) == int]))
        except InfluxDBClientError as e:
            print str(e)
            print_red("获取influxdb count 数出错！")
        except Exception as e:
            print e.message
        if len(count_list) > 0:
            max_table_count = max(count_list)
            print_green(u"本次迁移任务最大记录: %d " % max_table_count)
            print_green(u"当指定单次迁移1000条时候，预估迁移时间: %d 秒" % (max_table_count / 1000))
            print_green(u"当指定单次迁移5000条时候，预估迁移时间: %d 秒" % (max_table_count / 5000))
        else:
            try:
                migrate_total_time = float(influxdb_data_size)/3*0.001
                print_green(u"根据磁盘容量预估迁移时间: %d " % migrate_total_time)
            except ValueError:
                pass
    try:
        migrate_list = DBUtil().do_select_fetchall("SELECT * FROM zstack.MigrateInfluxDB")
        if len(migrate_list) > 0:
            for record in migrate_list:
                if record.migrateStatus == 'done':
                    print_green(u"influxdb table: %s 已经迁移完成" % record.tableName)
                    continue
                if record.error != "":
                    print_green(u"influxdb table: %s 迁移至 %d%% 出错, 错误信息: %s" %
                                (record.tableName, caclulate_process(record.minCreateTime, record.maxCreateTime,
                                                                     record.lastMigrateDataCreateTime), record.error))
                    continue
                print_green(u"influxdb table: %s 现在迁移状态 %s 迁移进度: %d%% " %
                            (record.tableName, record.migrateStatus, caclulate_process(record.minCreateTime,
                                                                                       record.maxCreateTime,
                                                                                       record.lastMigrateDataCreateTime)))
    except MySQLdb.Error as e:
        print e
        print u"还未进行初始化，继续迁移执行 init 或者 migrate -i 初始化"
    print_green(u"检查完毕")


def caclulate_process(start, end, last_time):
    base = parseUTCStrToTimestamp(start)
    time_range = parseUTCStrToTimestamp(end) - parseUTCStrToTimestamp(start)
    return float("%.4f" % (float((parseUTCStrToTimestamp(last_time) - base)) / time_range)) * 100


def status_mysql():
    code, out = getstatusoutput("systemctl status mariadb.service | grep 'Active: active (running)' | wc -l")
    if code == 0:
        return int(out) == 1


def status_influxdb():
    code, out = getstatusoutput("systemctl status influxdb-server | grep 'Active: active (running)' | wc -l")
    if code == 0:
        return int(out) == 1


def start_influxdb():
    code, out = getstatusoutput("systemctl restart influxdb-server")
    return code == 0


def print_red(strs):
    print ("\033[31;1m %s \033[0m" % strs)


def print_green(strs):
    print ("\033[32;1m %s \033[0m" % strs)


def print_blue(strs):
    print ("\033[34;1m %s \033[0m" % strs)


class Properties:

    def __init__(self):
        self.zstack_home = '/usr/local/zstack/apache-tomcat/webapps/zstack/'
        self.file_name = os.path.join(self.zstack_home, 'WEB-INF/classes/zstack.properties')
        self.properties = {}
        try:
            fopen = open(self.file_name, 'r')
            for line in fopen:
                line = line.strip()
                if line.find('=') > 0 and not line.startswith('#'):
                    strs = line.split('=')
                    self.properties[strs[0].strip()] = strs[1].strip()
        except Exception, e:
            raise e
        else:
            fopen.close()

    def has_key(self, key):
        return key in self.properties

    def get(self, key, default_value=''):
        if key in self.properties:
            return self.properties[key]
        return default_value


class AESCipher:

    def __init__(self, key='ZStack open source'):
        self.key = md5(key).hexdigest()
        self.cipher = AES.new(self.key, AES.MODE_ECB)
        self.prefix = "crypt_key_for_v1::"
        self.BLOCK_SIZE = 16

    # PKCS#7
    def _pad(self, data_to_pad, block_size):
        padding_len = block_size - len(data_to_pad) % block_size
        padding = bchr(padding_len) * padding_len
        return data_to_pad + padding

    # PKCS#7
    def _unpad(self, padded_data, block_size):
        pdata_len = len(padded_data)
        if pdata_len % block_size:
            raise ValueError("Input data is not padded")
        padding_len = bord(padded_data[-1])
        if padding_len < 1 or padding_len > min(block_size, pdata_len):
            raise ValueError("Padding is incorrect.")
        if padded_data[-padding_len:] != bchr(padding_len) * padding_len:
            raise ValueError("PKCS#7 padding is incorrect.")
        return padded_data[:-padding_len]

    def encrypt(self, raw):
        raw = self._pad(self.prefix + raw, self.BLOCK_SIZE)
        return base64.b64encode(self.cipher.encrypt(raw))

    def decrypt(self, enc):
        denc = base64.b64decode(enc)
        ret = self._unpad(self.cipher.decrypt(denc), self.BLOCK_SIZE).decode('utf8')
        return ret[len(self.prefix):] if ret.startswith(self.prefix) else enc

    def is_encrypted(self, enc):
        try:
            raw = self.decrypt(enc)
            return raw != enc
        except:
            return False


def get_db_info():
    db_user = Properties().get("DB.user")
    db_password = Properties().get("DB.password")
    cipher = AESCipher()
    if cipher.is_encrypted(db_password):
        db_password = cipher.decrypt(db_password)
    host = socket.gethostname().replace('-', ".")
    port = '3306'
    return host, port, db_user, db_password


def main():
    init_influxdb_info()
    import argparse
    parser = argparse.ArgumentParser()
    sub_parser = parser.add_subparsers(dest="action", help='action')
    # parser.add_argument("-a", "--action", choices=["check", "init", "migrate", "rollback"], help="action for migrate")
    migrate_parser = sub_parser.add_parser('migrate', help="init migrate meta table and migrate influxdb data")
    migrate_parser.add_argument("-s", "--start-time", dest="start", help="influxdb migrate data start time")
    migrate_parser.add_argument("-i", "--init", dest="init", action="store_true", help="init migrate meta table")
    migrate_parser.add_argument("-n", "--num", dest="num", default=5000, help=u"迁移时批量数据大小，默认5000条")
    migrate_parser.add_argument("-p", "--mysql-password", dest="passwd", help=u"mysql root 密码")
    migrate_parser.add_argument("-H", "--mysql-host", dest="host",  help=u"mysql host 连接地址")
    migrate_parser.add_argument("-d", "--dry-run", dest="dry", action="store_true", help=u"迁移测试dry run模式")
    init_parser = sub_parser.add_parser('init', help="init migrate meta table")
    init_parser.add_argument("-s", "--start-time", required=True, dest="start",
                             help=u"influxdb migrate data start time, eg:-s=full 全量迁移 -s=1 迁移当前时间前一天的数据")
    check_parser = sub_parser.add_parser('check', help="check influxdb data size and migrate status")
    rollback_parser = sub_parser.add_parser('rollback',
                                            help="delete migrate data in mysql, just for remigrate data from influxdb")
    args = parser.parse_args()
    if args.action == "init":
        init(args)
    elif args.action == "check":
        check()
    elif args.action == "migrate":
        migrate(args)
    elif args.action == "rollback":
        rollback()


if __name__ == '__main__':
    main()
