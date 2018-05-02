#!/bin/bash

pypi_source_file=$1
pypi_patch_file=$2

extension="${pypi_source_file##*.}"
file_name="${pypi_source_file%.*}"

if [ "$extension" = "zip" ];then
   unzip $pypi_source_file
   patch -p0 < patch/$pypi_patch_file
   rm -f $pypi_source_file
   zip -r $pypi_source_file $file_name
   rm -rf ${file_name}
else
  echo ">>> unsupported file format to patch"
fi