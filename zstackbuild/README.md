Preparation:
-------------
The following dependencies and installation packages need to be installed before building:

**Ant, Golang, Apache-Maven and Python2 need to be installed.**

```
# other necessary dependencies: 
yum install -y \
    java-1.8.0-openjdk \
    java-1.8.0-openjdk-devel \
    sudo \
    git \
    make \
    unzip \
    figlet \
    which \
    zip \
    gcc \
    iproute \
    openssl \
    libpcap \
    libpcap-devel \
    bzip2 \
    patch \
    dmidecode \
    python-setuptools; \
yum install -y --setopt=tsflags=nodocs \
    epel-release \
    mariadb \
    mariadb-server \
    bind-utils \
    pwgen \
    psmisc \
    hostname \
    bc; \
```

**Version Note :** 

MySQL version is: Ver 15.1 Distrib 5.5.68-MariaDB, for Linux (x86_64) using readline 5.1



## Building:

Now we can start building the package: 


### **Build zstack.war:**

    ant -propertyfile build.oss.properties \
        -buildfile build.oss.xml \
        -Dzstack_build_root=/your/path/to/zstack-repos \
        -Dbuild.zstack.ui.war=false \
        build-war



### **Build all-in-one installer:**

```
cd /your/path/to/zstack-repos;

wget -c https://archive.apache.org/dist/tomcat/tomcat-8/v8.5.78/bin/apache-tomcat-8.5.78.zip
```



    ant -propertyfile build.oss.properties \
        -buildfile build.oss.xml \
        -Dzstack_build_root=/your/path/to/zstack-repos \
        -Dbuild.zstack.ui.war=false \
        all-in-one

 &nbsp; 



The following instructions has dependency on repositories not publicly released yet.

#### Build zstack.war:

#ant build-war

#### Build zstack-woodpecker testing libs and config files:
#ant build-woodpecker

#### Build all:
#ant all

#### Build all-in-one package with special build name, e.g. rc1 :
#ant -Dzstack_build_root=/root/zstackorg/ -Dbuild.num=rc1 all-in-one

#### Build all-in-one package with special build name, e.g. rc1 :

#ant -Dzstack_build_root=/root/zstackorg/ -Dbuild.num=rc1 -Dbin.version=1.0.1-rc1 all-in-one

#### Build all-in-one offline binary installer for CentOS6 (need to install figlet):

#ant -Dzstack_build_root=/root/zstackorg/ offline-centos6

#### Build all-in-one offline binary installer for CentOS7 (need to install figlet):
#ant -Dzstack_build_root=/root/zstackorg/ offline-centos7

#### Build all-in-one offline binary installer for CentOS6 and CentOS7 (need to install figlet):
#ant -Dzstack_build_root=/root/zstackorg/ offline-centos-all

#### Build all-in-one offline binary installer for CentOS6 and CentOS7, with specific branch version:

#ant -Dzstack_build_root=/root/zstackorg/ offline-centos-all

#### Build all-in-one package with 1.2.x branch
#ant -Dzstack_build_root=/root/zstackorg/ -Dzstack.build_version=1.2.x -Dzstack-utiltiy.build_version=1.2.x all-in-one