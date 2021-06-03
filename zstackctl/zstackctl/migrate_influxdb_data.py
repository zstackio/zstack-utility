# -*- coding: UTF-8 -*-
import sys

sys.path.append("/var/lib/zstack/virtualenv/zstackctl/lib/python2.7/site-packages/")
sys.path.append("/var/lib/zstack/virtualenv/zstackcli/lib/python2.7/site-packages/")
sys.path.append("/usr/lib/python2.7/site-packages/")
sys.path.append("/usr/lib64/python2.7/site-packages/")

import os
import socket
import json
import MySQLdb
import time
import datetime
import base64
import traceback
from commands import getstatusoutput
import logging
from threading import Thread
from Crypto.Cipher import AES
from Crypto.Util.py3compat import *
from hashlib import md5

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


logger = logging.getLogger()
logger.setLevel(logging.INFO)
log_name = "/var/log/zstack/migrate_influxdb.log"
logfile = log_name
fh = logging.FileHandler(logfile, mode='a')
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)

client = InfluxDBClient(host='localhost', port=8086, database='zstack', timeout=60)

MigrateIns = {
    "zstack.zstack.audits": "AuditsVO",
    "zstack.messages.events": "EventRecordsVO",
    "zstack.messages.alarms": "AlarmRecordsVO",
    "zstack.zstack.events": "EventRecordsVO",
    "zstack.zstack.alarms": "AlarmRecordsVO"
}


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


def dict_to_obj(func):
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


class DBUtil:
    def __init__(self):
        self.host = None
        self.port = 3306
        self.user = None
        self.password = None

    def init_mysql_info(self, passwd=None, host=None):
        if passwd is not None:
            self.host = host if host else '127.0.0.1'
            self.user = 'root'
            self.password = passwd
        else:
            import getpass
            if getpass.getuser() == "root":
                from zstackctl.ctl import Ctl
                ctl = Ctl()
                ctl.locate_zstack_home()
                self.host, self.port, self.user, self.password = ctl.get_live_mysql_portal()
            else:
                self.host, self.port, self.user, self.password = self.get_db_info_by_properties()

    @staticmethod
    def _get_db_info_by_properties():
        class Properties:

            def __init__(self):
                self.zstack_home = '/usr/local/zstack/apache-tomcat/webapps/zstack/'
                self.file_name = os.path.join(self.zstack_home, 'WEB-INF/classes/zstack.properties')
                self.properties = {}

                with open(self.file_name, 'r') as fd:
                    for line in fd.read():
                        line = line.strip()
                        if line.find('=') > 0 and not line.startswith('#'):
                            strs = line.split('=')
                            self.properties[strs[0].strip()] = strs[1].strip()

            def has_key(self, key):
                return key in self.properties

            def get(self, key, default_value=''):
                if key in self.properties:
                    return self.properties[key]
                return default_value

        properties = Properties()
        db_user = properties.get("DB.user")
        db_password = properties.get("DB.password")
        cipher = AESCipher()
        if cipher.is_encrypted(db_password):
            db_password = cipher.decrypt(db_password)
        host = socket.gethostname().replace('-', ".")
        port = '3306'
        return host, port, db_user, db_password

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

    @dict_to_obj
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

    def get_max_allowed_packet(self):
        res = self.do_select_fetchall("show global variables like 'max_allowed_packet'")
        if len(res) > 0:
            return int(res[0].Value)
        return 0

    def set_max_allowed_packet(self, size=67108864):
        try:
            self.do_execute("set global max_allowed_packet=%d" % size)
        except MySQLdb.Error as e:
            print_red(u"修改mysql参数出错 %s,请指定root密码执行 -p 查看帮助-h" % str(e))
            exit(1)

    def rollback_max_allowed_packet(self):
        if os.path.exists(".mysql_max_allowed_packet"):
            with open('.mysql_max_allowed_packet') as f:
                mysql_max_allowed_packet_config = f.readline()
                self.set_max_allowed_packet(int(mysql_max_allowed_packet_config))


mysql_client = DBUtil()


def parse_utc_str_to_timestamp(utc_str):
    try:
        datetime_obj = datetime.datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        datetime_obj = datetime.datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ")
    return long(time.mktime(datetime_obj.timetuple()) * 1000.0 + datetime_obj.microsecond / 1000.0)


def safe_str(obj):
    try:
        return str(obj)
    except UnicodeEncodeError:
        return obj.encode('ascii', 'ignore').decode('ascii')


class AuditsVO:

    def __init__(self, influxdb):
        self.influxdb = influxdb
        self.mysqldb = "zstack.AuditsVO"
        self.sql_tmpl_safe = """insert into zstack.AuditsVO (`createTime`, `apiName`, `clientBrowser`, `clientIp`, 
                             `duration`, `error`, `operator`, `requestDump`,`resourceType`,`resourceUuid`,`requestUuid`,
                             `operatorAccountUuid`, `responseDump`, `success`) 
                             values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        self.column = ['createTime', 'apiName', 'clientBrowser', 'clientIp', 'duration', 'error', 'operator',
                       'requestDump', 'resourceType', 'resourceUuid', 'requestUuid',
                       'operatorAccountUuid', 'responseDump', 'success']

    def process_influxdb_data(self, data):
        if data.has_key("requestDump"):
            req_data = json.loads(data.get('requestDump'))
            if req_data.has_key("headers"):
                req_data.pop("headers")
            data['requestDump'] = safe_str(json.dumps(req_data))
        if data.has_key("responseDump"):
            res_data = json.loads(data.get('responseDump'))
            if res_data.has_key("headers"):
                res_data.pop("headers")
            data['responseDump'] = safe_str(json.dumps(res_data))
        if not data.get("clientBrowser"):
            data['clientBrowser'] = ""
        if not data.get("clientIp"):
            data['clientIp'] = ""
        if data.has_key("success"):
            data['success'] = int(data.get("success") == "success")
        if not data.get("success"):
            data['success'] = 1
        if data.has_key("time"):
            data['createTime'] = parse_utc_str_to_timestamp(data.get('time'))
        return data

    def process_mysql_data(self, mysql_columns):
        return


class EventRecordsVO:

    def __init__(self, influxdb):
        self.influxdb = influxdb
        self.mysqldb = "zstack.EventRecordsVO"
        self.column = ['createTime', 'accountUuid', 'dataUuid', 'emergencyLevel', 'name', 'error', 'labels',
                       'namespace', 'readStatus', 'resourceId', 'resourceName', 'subscriptionUuid']
        self.sql_tmpl_safe = """insert into zstack.EventRecordsVO (`createTime`, `accountUuid`, 
                                `dataUuid`, `emergencyLevel`, `name`, `error`, 
                                `labels`, `namespace`,`readStatus`,`resourceId`,`resourceName`, 
                                `subscriptionUuid`, `hour`) 
                                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

    def process_influxdb_data(self, data):
        label_map = {i: data[i] for i in data if ':::' in i and data[i] != None}
        if len(label_map) > 0:
            label_map = {i.split(':::')[-1]: label_map[i] for i in label_map}
            data['label'] = safe_str(json.dumps(label_map))
        if data.has_key("readStatus"):
            data['readStatus'] = int(data.get("readStatus") == "Read")
        if data.has_key("time"):
            data['createTime'] = parse_utc_str_to_timestamp(data.get('time'))
        return data

    def process_mysql_data(self, mysql_columns):
        for columns in mysql_columns[:]:
            subscription_uuid = columns[self.column.index('subscriptionUuid')]
            if not subscription_uuid:
                mysql_columns.remove(columns)

        for columns in mysql_columns:
            create_time = columns[self.column.index('createTime')]
            hour = create_time / 3600000 * 3600
            columns.append(hour)


class AlarmRecordsVO:

    def __init__(self, influxdb):
        self.influxdb = influxdb
        self.mysqldb = "zstack.AlarmRecordsVO"
        self.column = ['createTime', 'accountUuid', 'alarmName', 'alarmStatus', 'alarmUuid', 'comparisonOperator',
                       'context', 'dataUuid', 'emergencyLevel', 'labels', 'metricName', 'metricValue', 'namespace',
                       'period', 'readStatus', 'resourceType', 'resourceUuid', 'threshold']
        self.sql_tmpl_safe = """insert into zstack.AlarmRecordsVO (`createTime`, `accountUuid`, `alarmName`, 
                             `alarmStatus`, `alarmUuid`, `comparisonOperator`, `context`, `dataUuid`, 
                             `emergencyLevel`,`labels`,`metricName`, `metricValue`, `namespace`, `period`, 
                             `readStatus`, `resourceType`, `resourceUuid`, `threshold`, `hour`) 
                             values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

    def process_influxdb_data(self, data):
        if data.has_key("requestDump"):
            req_data = json.loads(data.get('requestDump'))
            if req_data.has_key("headers"):
                req_data.pop("headers")
            data['requestDump'] = safe_str(json.dumps(req_data))
        if data.has_key("responseDump"):
            res_data = json.loads(data.get('responseDump'))
            if res_data.has_key("headers"):
                res_data.pop("headers")
            data['responseDump'] = safe_str(json.dumps(res_data))
        if data.has_key("readStatus"):
            data['readStatus'] = int(data.get("readStatus") == "Read")
        if data.has_key("time"):
            data['createTime'] = parse_utc_str_to_timestamp(data.get('time'))
        return data

    def process_mysql_data(self, mysql_columns):
        for columns in mysql_columns:
            create_time = columns[0]
            hour = create_time / 3600000 * 3600
            columns.append(hour)


class MigrateAction(Thread):

    def __init__(self, obj, query_num, dry_run):
        super(MigrateAction, self).__init__()
        self.mysql_obj = obj
        self.query_num = query_num
        self.errorInfo = ""
        self.finish = ""
        self.queue = []
        self.dry_run = dry_run
        self.startTime = mysql_client.do_select_fetchone(
            "select minCreateTime from zstack.MigrateInfluxDB where tableName='%s'" % self.mysql_obj.influxdb)
        self.endTime = mysql_client.do_select_fetchone(
            "select maxCreateTime from zstack.MigrateInfluxDB where tableName='%s'" % self.mysql_obj.influxdb)
        self.rangeTime = parse_utc_str_to_timestamp(self.endTime) - parse_utc_str_to_timestamp(self.startTime)
        self.baseTime = parse_utc_str_to_timestamp(self.startTime)

    def __repr__(self):
        return "MigrateAction-Thread-%s" % self.mysql_obj.__class__.__name__

    def calculate_process(self, last_time):
        if self.rangeTime == 0:
            return float("%.4f" % 100)
        return float("%.4f" % (float((parse_utc_str_to_timestamp(last_time) - self.baseTime)) / self.rangeTime)) * 100

    def run(self):
        print "%s thread run...." % self.mysql_obj.__class__.__name__
        conn = mysql_client._connection()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        start_time = time.time()
        count = 0
        while self.errorInfo == "" and self.finish != "done":
            last_time = mysql_client.do_select_fetchone(
                "select lastMigrateDataCreateTime from zstack.MigrateInfluxDB where tableName='%s'" % self.mysql_obj.influxdb)
            print_blue("migrate influxdb table %s to mysql table %s percentage completion  %d%%" % (
                self.mysql_obj.influxdb, self.mysql_obj.mysqldb, self.calculate_process(last_time)))
            latest_influxdb_sql = "SELECT * FROM %s WHERE time > '%s' ORDER BY time LIMIT %d" % (
                self.mysql_obj.influxdb, last_time, self.query_num)
            if count == 0:
                latest_influxdb_sql = "SELECT * FROM %s WHERE time >= '%s' ORDER BY time LIMIT %d" % (
                    self.mysql_obj.influxdb, last_time, self.query_num)
            try:
                prepare_migrate_influxdb_data = client.query(latest_influxdb_sql)
            except InfluxDBClientError as e:
                print "query influxdb %s error : %s" % (self.mysql_obj.influxdb, str(e))
                exc_type, exc_value, exc_obj = sys.exc_info()
                logger.error(str(traceback.format_exc(exc_obj)))
                self.errorInfo = str(e)
                self.finish = "error"
                break

            count += 1
            if len(self.queue) == 0:
                if 'series' in prepare_migrate_influxdb_data.raw and \
                        len(prepare_migrate_influxdb_data.raw['series'][0]['values']) > 0:
                    for data in prepare_migrate_influxdb_data.get_points():
                        data = self.mysql_obj.process_influxdb_data(data)
                        self.queue.append(data)
                else:
                    retry = client.query(latest_influxdb_sql)
                    if 'series' not in retry.raw:
                        mysql_client.do_execute("update zstack.MigrateInfluxDB set migrateStatus='%s'where tableName='%s'"
                                            % ("done", self.mysql_obj.influxdb))
                        self.finish = "done"
            else:
                last_success_record = self.queue[len(self.queue) - 1]
                many_args = list(([i.get(j) for j in self.mysql_obj.column] for i in self.queue))
                self.mysql_obj.process_mysql_data(many_args)
                if self.dry_run:
                    print "%s %s" % (self.mysql_obj.sql_tmpl_safe, many_args)
                else:
                    try:
                        mysql_client.do_batch_insert(conn, cursor, self.mysql_obj.sql_tmpl_safe, many_args)
                    except MySQLdb.Error as e:
                        print_red("insert %s data error: %s" % (self.mysql_obj.__class__.__name__, str(e)))
                        exc_type, exc_value, exc_obj = sys.exc_info()
                        logger.error(traceback.print_tb(exc_obj))
                        self.errorInfo = str(e)
                        break
                self.queue = []

                if self.dry_run:
                    break

                print "#" * 20
                if self.errorInfo:
                    print self.errorInfo
                    print (
                        last_success_record['time'], json.dumps(last_success_record), self.errorInfo,
                        self.mysql_obj.influxdb)
                    mysql_client.do_execute_safely(
                        "update zstack.MigrateInfluxDB set lastMigrateDataCreateTime=%s,lastMigrateDataRecord=%s,"
                        "error=%s where tableName=%s",
                        (last_success_record['time'], json.dumps(last_success_record), self.errorInfo,
                         self.mysql_obj.influxdb))
                else:
                    mysql_client.do_execute_safely(
                        "update zstack.MigrateInfluxDB set lastMigrateDataCreateTime=%s,lastMigrateDataRecord=%s "
                        "where tableName=%s",
                        (last_success_record['time'], json.dumps(last_success_record), self.mysql_obj.influxdb))

        if conn:
            cursor.close()
            conn.close()
        if self.errorInfo:
            mysql_client.do_execute_safely("update zstack.MigrateInfluxDB set error=%s where tableName=%s",
                                       (self.errorInfo, self.mysql_obj.influxdb))
        end_time = time.time()
        print "total time: %d" % (end_time - start_time)


def init(args):
    logger.info("start init migrate task info!")
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
        mysql_client.do_execute(create_table_sql)

    def init_mysql_meta_table(start):
        sql_templ = """insert into zstack.MigrateInfluxDB (`tableName`, `maxCreateTime`, `minCreateTime`,
                    `lastMigrateDataCreateTime`) values (%s, %s, %s, %s)"""
        for table in MigrateIns:
            max_time_record = client.query("SELECT * FROM %s ORDER BY time DESC LIMIT 1" % table)
            max_time = [i['time'] for i in max_time_record.get_points()][0]
            min_time_record = client.query("SELECT * FROM %s ORDER BY time LIMIT 1" % table)
            min_time = [i['time'] for i in min_time_record.get_points()][0]
            if start == "full":
                mysql_client.do_execute_safely(sql_templ, (table, max_time, min_time, min_time))
            else:
                last_migrate_date = (datetime.datetime.utcnow() - datetime.timedelta(days=int(start))).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ")
                if last_migrate_date > max_time:
                    print_red(u"迁移指定的influxdb历史数据开始时间不能晚于influxdb中最近一条记录的创建时间")
                    mysql_client.do_execute("drop table zstack.MigrateInfluxDB")
                    exit(1)
                mysql_client.do_execute_safely(sql_templ, (table, max_time, last_migrate_date, last_migrate_date))

    result = mysql_client.do_select_fetchone(
        "SELECT table_name FROM information_schema.TABLES WHERE table_name ='MigrateInfluxDB'")
    if result is None:
        create_mysql_meta_table()
        init_mysql_meta_table(args.start)
    check_init_success()


def check_init_success():
    flag = True
    for table in MigrateIns:
        try:
            result = mysql_client.do_select_fetchone(
                "select tableName from zstack.MigrateInfluxDB where tableName='%s'" % table)
            if result is None:
                print_red(u"迁移记录表influx table: %s 数据初始化未成功! 请执行初始化步骤 -h 查看帮助 " % table)
                flag = False
        except MySQLdb.Error as e:
            print_red(u"查询迁移记录表zstack.MigrateInfluxDB出错: %s ,请执行初始化步骤 -h 查看帮助" % str(e))
            exit(1)
    if not flag:
        exit(1)
    print_green(u"迁移记录表数据初始化完成!")


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
            # print_red(str(e))
            MigrateIns.pop(table)
            continue


def rollback():
    logger.info("start rollback migrated mysql data!")
    result = mysql_client.do_select_fetchone(
        "SELECT table_name FROM information_schema.TABLES WHERE table_name ='MigrateInfluxDB'")
    if result is None:
        print_green(u"未迁移过influxdb数据，不需要回滚!")
        exit(0)
    for influx_table, mysql_table in MigrateIns.iteritems():
        influx_last_time = mysql_client.do_select_fetchone(
            "select maxCreateTime from zstack.MigrateInfluxDB where tableName='%s'" % influx_table)
        assert influx_last_time != "", print_red(u"获取influxdb迁移历史数据最近时间失败")
        last_time_stamp = parse_utc_str_to_timestamp(influx_last_time)
        mysql_client.do_execute("DELETE FROM zstack.%s where createTime <= %d " % (mysql_table, last_time_stamp))
        print_green(u"删除 %s 表中迁移过来的历史数据" % mysql_table)
        count = mysql_client.do_select_fetchone(
            "select count(*) from zstack.%s where createTime <= %d " % (mysql_table, last_time_stamp))
        assert count == 0, print_red(u"删除influxdb迁移完成数据失败")
    mysql_client.do_execute("drop table zstack.MigrateInfluxDB")
    print_green(u"回滚迁移的influxdb历史数据完成")


def calculate_allow_batch_insert(num, origin_global_config):
    if int(num) * 4096 > origin_global_config:
        print_red(u"你现在指定的单批插入次大于mysql配置的max_allowed_packet上限，容易迁移失败，"
                  u"请调整-n参数或者指定-p mysql root 密码, -h 查看帮助")
        exit(1)


def migrate(args):
    logger.info("start migrate influx history data to mysql!")
    mysql_client.ping()
    # size: B
    origin_global_config = mysql_client.get_max_allowed_packet()

    if not args.num:
        args.num = origin_global_config / 4096

    if args.passwd:
        if origin_global_config < 67108864:  # 64m
            if not os.path.exists(".mysql_max_allowed_packet"):
                with open(".mysql_max_allowed_packet", "w") as f:
                    f.write(str(origin_global_config))
            mysql_client.set_max_allowed_packet()
    else:
        if not args.dry:
            calculate_allow_batch_insert(args.num, origin_global_config)

    if args.init:
        if args.start is None:
            print_red(u"请添加参数 -s=${输入数字，或者full} -h help查看帮助")
            exit(1)
        init(args)
    else:
        check_init_success()

    get_migrate_time(int(args.num))
    migrate_objs = mysql_client.do_select_fetchall("select * from zstack.MigrateInfluxDB")
    logger.info("MigrateInfluxDB: %s" % migrate_objs)

    migrate_list = []
    for obj in migrate_objs:
        if obj.tableName in MigrateIns.keys() and obj.migrateStatus != 'done':
            migrate_list.append(MigrateAction(eval(MigrateIns[obj.tableName])(obj.tableName), int(args.num),
                                             args.dry))
    logger.info("migrate_list: %s" % migrate_list)
    if len(migrate_list) > 0:
        for t in migrate_list:
            t.setDaemon(True)
            t.start()
        for j in migrate_list:
            j.join()
    if os.path.exists(".mysql_max_allowed_packet"):
        mysql_client.set_max_allowed_packet(origin_global_config)
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
        exc_type, exc_value, exc_obj = sys.exc_info()
        logger.error(str(traceback.format_exc(exc_obj)))
    except Exception as e:
        print e.message
    if len(count_list) > 0:
        max_table_count = max(count_list)
        print_green(u"本次迁移任务最大记录: %d " % max_table_count)
        print_green(u"指定单次迁移 %d 条，预估迁移时间: %d 秒" % (size, 1 if (max_table_count / size) < 10 else (max_table_count / size)))


def check_db_status():
    assert status_influxdb(), "influxdb server status is not running, please check !"
    print_green(u"Influx db 服务状态正常!")
    assert status_mysql(), "mysql server status is not running, please check !"
    print_green(u"MySQL db 服务状态正常!")


def check():
    code, influxdb_data_size = getstatusoutput("du -sh -k /var/lib/zstack/influxdb/data/zstack | awk '{print $1}'")
    can_calculate = True
    logger.info("start check migrate influxdb data")
    try:
        print_green(u"influx db数据总量: %d kb" % int(influxdb_data_size))
    except ValueError:
        can_calculate = False
        print_red("获取influx db数据总量失败: %s" % safe_str(influxdb_data_size))
    code1, mysql_available = getstatusoutput("df -hl -k /var/lib/mysql/ | awk '{print $4}' | sed -n '2p'")
    try:
        print_green(u"mysql 所在盘可用空间: %d kb" % int(mysql_available))
    except ValueError:
        can_calculate = False
        print_red("获取mysql所在盘可用空间失败: %s" % safe_str(mysql_available))
    if can_calculate:
        if int(influxdb_data_size) * 1.5 > int(mysql_available):
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
            exc_type, exc_value, exc_obj = sys.exc_info()
            logger.error(str(traceback.format_exc(exc_obj)))
            if not str(e).startswith("retention policy not found"):
                print_red("获取influxdb count 数出错！%s" % str(e))
        except Exception as e:
            print e.message
        if len(count_list) > 0:
            max_table_count = max(count_list)
            print_green(u"本次迁移任务最大记录: %d " % max_table_count)
            print_green(u"当指定单次迁移1000条时候，预估迁移时间: %d 秒" % (max_table_count / 1000))
            print_green(u"当指定单次迁移5000条时候，预估迁移时间: %d 秒" % (max_table_count / 5000))
        else:
            try:
                migrate_total_time = float(influxdb_data_size) / 3 * 0.001
                print_green(u"根据磁盘容量预估迁移时间: %d " % migrate_total_time)
            except ValueError:
                pass
    try:
        migrate_list = mysql_client.do_select_fetchall("SELECT * FROM zstack.MigrateInfluxDB")
        if len(migrate_list) > 0:
            for record in migrate_list:
                if record.migrateStatus == 'done':
                    print_green(u"influxdb table: %s 已经迁移完成" % record.tableName)
                    continue
                if record.error is not None:
                    print_green(u"influxdb table: %s 迁移至 %d%% 出错, 错误信息: %s" %
                                (record.tableName, calculate_process(record.minCreateTime, record.maxCreateTime,
                                                                     record.lastMigrateDataCreateTime), record.error))
                    continue
                migrate_status = record.migrateStatus if record.migrateStatus else 'not_done'
                print_green(u"influxdb table: %s 现在迁移状态 %s 迁移进度: %d%% " %
                            (record.tableName, migrate_status, calculate_process(record.minCreateTime,
                                                                                       record.maxCreateTime,
                                                                                       record.lastMigrateDataCreateTime)))
    except MySQLdb.Error as e:
        print e
        print u"还未进行初始化，继续迁移执行 init 或者 migrate -i 初始化"
    print_green(u"检查完毕")


def calculate_process(start, end, last_time):
    base = parse_utc_str_to_timestamp(start)
    time_range = parse_utc_str_to_timestamp(end) - parse_utc_str_to_timestamp(start)
    if start == end and time_range == 0:
        return float("%.4f" % 100)
    return float("%.4f" % (float((parse_utc_str_to_timestamp(last_time) - base)) / time_range)) * 100


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
    logger.error(strs)
    print ("\033[31;1m %s \033[0m" % strs)


def print_green(strs):
    logger.info(strs)
    print ("\033[32;1m %s \033[0m" % strs)


def print_blue(strs):
    logger.info(strs)
    print ("\033[34;1m %s \033[0m" % strs)


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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    sub_parser = parser.add_subparsers(dest="action", help='action')

    check_parser = sub_parser.add_parser('check', help="check influxdb data size and migrate status")
    check_parser.add_argument("-p", "--mysql-password", dest="passwd", help=u"mysql root 密码")
    check_parser.add_argument("-H", "--mysql-host", dest="host", help=u"mysql host 连接地址")

    def valid_start_time(s):
        if s != "full":
            int(s)
        return s

    init_parser = sub_parser.add_parser('init', help="init migrate meta table")
    init_parser.add_argument("-s", "--start-time", required=True, type=valid_start_time, dest="start",
                             help=u"influxdb migrate data start time, eg:-s=full 全量迁移 -s=1 迁移当前时间前一天的数据")
    init_parser.add_argument("-p", "--mysql-password", dest="passwd", help=u"mysql root 密码")
    init_parser.add_argument("-H", "--mysql-host", dest="host", help=u"mysql host 连接地址")

    migrate_parser = sub_parser.add_parser('migrate', help="init migrate meta table and migrate influxdb data")
    migrate_parser.add_argument("-s", "--start-time", dest="start", type=valid_start_time, help="influxdb migrate data start time")
    migrate_parser.add_argument("-i", "--init", dest="init", action="store_true", help="init migrate meta table")
    migrate_parser.add_argument("-n", "--num", dest="num", type=int, help=u"迁移时批量数据大小")
    migrate_parser.add_argument("-p", "--mysql-password", dest="passwd", help=u"mysql root 密码")
    migrate_parser.add_argument("-H", "--mysql-host", dest="host", help=u"mysql host 连接地址")
    migrate_parser.add_argument("-d", "--dry-run", dest="dry", action="store_true", help=u"迁移测试dry run模式")
    migrate_parser.add_argument("-it", "--influxdb-timeout", dest="influxdb_timeout", default=60,
                                help=u"influxdb请求创建连接到客户端的timeout秒数")

    rollback_parser = sub_parser.add_parser('rollback',
                                            help="delete migrate data in mysql, just for remigrate data from influxdb")
    rollback_parser.add_argument("-p", "--mysql-password", dest="passwd", help=u"mysql root 密码")
    rollback_parser.add_argument("-H", "--mysql-host", dest="host", help=u"mysql host 连接地址")

    args = parser.parse_args()

    check_db_status()
    mysql_client.init_mysql_info(args.passwd, args.host)
    init_influxdb_info()

    if args.action == "check":
        check()
        return

    if args.action == "init":
        init(args)
    elif args.action == "migrate":
        check()
        migrate(args)
    elif args.action == "rollback":
        rollback()


if __name__ == '__main__':
    main()
