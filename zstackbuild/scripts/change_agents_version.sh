zstackutility=$1
find $zstackutility -name setup.py -exec sed -i "s#version = '1.7'#version = '1.8'#" {} \;

find /root/zstackorg/zstack -name pom.xml -exec sed -i "s/1.7.0/1.8.0/g" {} \;
find /root/zstackorg/zstack -name *.java -exec sed -i 's/1.7.tar.gz/1.8.tar.gz/g' {} \;

