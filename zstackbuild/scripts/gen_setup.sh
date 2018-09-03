#!/bin/bash
cat >$4 <<EOF
#!/bin/bash
line=\`wc -l \$0|awk '{print \$1}'\`
line=\`expr \$line - 18\`
tmpdir=\`mktemp\`
/bin/rm -f \$tmpdir
mkdir -p \$tmpdir
tail -n \$line \$0 |tar x -C \$tmpdir
cd \$tmpdir
(
  flock -n 9
  if [ \$? -ne 0 ]; then
    echo "There is another ZStack installation progress running."
    exit 1;
  fi
  PRODUCT_NAME=$1 PRODUCT_VERSION=$2 CHECK_REPO_VERSION=$3 bash ./install.sh -o -f zstack*.tgz \$*
) 9>/tmp/zstack_lock_file
ret=\$?
rm -rf \$tmpdir /tmp/zstack_lock_file
exit \$ret
EOF
