1. 文件说明
ioControl     二进制后台程序
host.json     Host上的配置文件格式
detect.json   违规外联探测地址
net.json      违规外联上报地址
inetv.tpl     违规外联上报模板
netHelper.tpl 自定义违规外联报警日志模板（暂未使用）

2. 参数说明
  -V virtual （  -V 、-virtual  使用参数开启虚拟机模式，不使用参数使用物理机模式。）
    	used by virtual computer
  -a alarm  （  -a 、-alarm  使用参数开启bmj告警，不使用参数关闭bmj告警。）
    	enable inetv alarm
  -d debug（  -d 、-debug  使用参数写日志文件，不使用终端输出。）
    	enable write debug log file
  -h help （  -h 、-help  查看帮助。）
    	show help
  -m mode（  -m 、-mode  使用参数增加TEST标识为测试告警模式，不使用参数为标准告警模式。）
    	disable inetv audit test mode
  -n net （  -n 、-net  配置违规外联上报地址。）
    	set net configuration file (default "./net.json")
  -s host（  -s 、-host  zstack提供的配置文件供本程序读取。）
    	set host configuration file (default "./host.json")
  -t detect（  -t 、-detect   违规外联探测地址。）
    	set detect configuration file (default "./detect.json")
  -v version（  -v 、-version  查看程序版本。）
    	show version and exit