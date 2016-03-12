product=${1^^}
version=$2
output_file=$3

which figlet
if [ $? -eq 0 ]; then
    figlet -w 80 $product |tee -a $output_file
    figlet -w 80 v $version |tee -a $output_file
    figlet -w 80 INSTALLATION |tee -a $output_file
fi
