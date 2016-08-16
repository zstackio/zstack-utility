zstackutility=$1
find $zstackutility -name setup.py -exec sed -i "s#version = '1.5'#version = '1.6'#" {} \;

#find /root/zstackorg/zstack -name pom.xml -exec sed -i "s/1.5.0/1.6.0/g" {} \;
#find /root/zstackorg/zstack -name *.java -exec sed -i 's/1.5.tar.gz/1.6.tar.gz/g' {} \;

