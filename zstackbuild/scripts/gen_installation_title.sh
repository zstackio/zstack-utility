product=${1^^}
version=$2
output_file=$3

which figlet
if [ $? -eq 0 ]; then
    # handle long product name
    # only works for zstack-enterprise etc.
    figlet -w 80 `echo $product | sed 's/-/\n/g'` |tee -a $output_file
    figlet -w 80 v $version |tee -a $output_file
    figlet -w 80 INSTALLATION |tee -a $output_file
fi
