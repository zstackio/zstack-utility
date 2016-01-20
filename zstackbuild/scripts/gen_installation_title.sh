product=$1
version=$2
output_file=$3

which figlet
if [ $? -eq 0 ]; then
    figlet -w 80 $product v$version INSTALLATION |tee -a $output_file
fi
