zstackutility=$1
find $zstackutility -name setup.py -exec sed -i "s#version = '1.0'#version = '1.1'#" {} \;

#find /root/zstack -name pom.xml -exec sed -i "s/1.0.0/1.1.0/g" {} \;
#find /root/zstack -name *.java -exec sed -i 's/1.0.tar.gz/1.1.tar.gz/g' {} \;

