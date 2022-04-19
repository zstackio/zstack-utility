#!/bin/bash
echo "modify my.cnf"
if [ -f /etc/mysql/mariadb.conf.d/50-server.cnf ]; then
    #ubuntu 16.04
    mysql_conf=/etc/mysql/mariadb.conf.d/50-server.cnf
elif [ -f /etc/mysql/my.cnf ]; then
    # Ubuntu 14.04
    mysql_conf=/etc/mysql/my.cnf
elif [ -f /etc/my.cnf.d/mariadb-server.cnf ]; then
    # MariaDB 10.3.9 CentOS.8/Kylin.V10
    mysql_conf=/etc/my.cnf.d/mariadb-server.cnf
elif [ -f /etc/my.cnf ]; then
    # centos
    mysql_conf=/etc/my.cnf
fi

sed -i 's/^bind-address/#bind-address/' $mysql_conf
sed -i 's/^skip-networking/#skip-networking/' $mysql_conf
sed -i 's/^bind-address/#bind-address/' $mysql_conf

grep 'binlog_format=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "binlog_format=mixed"
    sed -i '/\[mysqld\]/a binlog_format=mixed\' $mysql_conf
fi

grep 'log_bin_trust_function_creators=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "log_bin_trust_function_creators=1"
    sed -i '/\[mysqld\]/a log_bin_trust_function_creators=1\' $mysql_conf
fi

grep 'expire_logs=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "expire_logs=30"
    sed -i '/\[mysqld\]/a expire_logs=30\' $mysql_conf
fi

grep 'max_binlog_size=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "max_binlog_size=500m"
    sed -i '/\[mysqld\]/a max_binlog_size=500m\' $mysql_conf
fi

grep 'log-bin=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "log-bin=mysql-binlog"
    sed -i '/\[mysqld\]/a log-bin=mysql-binlog\' $mysql_conf
fi

# Fixes ZSTAC-24460
# if max_allowed_packet is not configured, then update from default value 1M to 4M
grep 'max_allowed_packet' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "max_allowed_packet=4M"
    sed -i '/\[mysqld\]/a max_allowed_packet=4M\' $mysql_conf
fi

# wanted_files = 10+max_connections+table_open_cache*2
# 'table_open_cache' is default to 400 as of 5.5.x
grep 'max_connections' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "max_connections=400"
    sed -i '/\[mysqld\]/a max_connections=400\' $mysql_conf
else
    echo "max_connections=400"
    sed -i 's/max_connections.*/max_connections=400/g' $mysql_conf
fi

grep 'interactive_timeout' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "interactive_timeout=100"
    sed -i '/\[mysqld\]/a interactive_timeout=100\' $mysql_conf
fi

grep 'wait_timeout' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "wait_timeout=100"
    sed -i '/\[mysqld\]/a wait_timeout=100\' $mysql_conf
fi

grep 'slave_net_timeout=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "slave_net_timeout=60"
    sed -i '/\[mysqld\]/a slave_net_timeout=60\' $mysql_conf
fi

mkdir -p /etc/systemd/system/mariadb.service.d/
echo -e "[Service]\nLimitNOFILE=2048" > /etc/systemd/system/mariadb.service.d/limits.conf
systemctl daemon-reload || true

grep '^character-set-server' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "binlog_format=mixed"
    sed -i '/\[mysqld\]/a character-set-server=utf8\' $mysql_conf
fi
grep '^skip-name-resolve' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    sed -i '/\[mysqld\]/a skip-name-resolve\' $mysql_conf
fi

grep 'tmpdir' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    mysql_tmp_path="/var/lib/zstack-mysql-tmp"
    if [ ! -x "$mysql_tmp_path" ]; then
        mkdir "$mysql_tmp_path"
        chown mysql:mysql "$mysql_tmp_path"
        chmod 1777 "$mysql_tmp_path"
    fi
    echo "tmpdir=$mysql_tmp_path"
    sed -i "/\[mysqld\]/a tmpdir=$mysql_tmp_path" $mysql_conf
fi
systemctl restart mariadb