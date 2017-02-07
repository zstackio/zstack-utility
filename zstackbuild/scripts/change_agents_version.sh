zstackutility_folder=$1
zstack_folder=$2
find $zstackutility_folder -name setup.py -exec sed -i "s#version = '1.8'#version = '1.9'#" {} \;

#after executing the script, you need to double check 'git diff' to make sure all changes are correct. Then use git commit in zstack folder and premium folder.
find $zstack_folder -name pom.xml -exec sed -i "s/1.8.0/1.9.0/g" {} \;
find $zstack_folder -name *.java -exec sed -i 's/1.8.tar.gz/1.9.tar.gz/g' {} \;

