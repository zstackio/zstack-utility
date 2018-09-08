#!/bin/bash
ZSTACK_SOURCE=$1
PYTHON_APIS_DIR=$2
if [ -d ${ZSTACK_SOURCE}/premium/test-premium ]; then
    cd ${ZSTACK_SOURCE}/premium/test-premium
else
    cd ${ZSTACK_SOURCE}/test
fi

mvn test -Dtest=TestGenerateApiPythonClassAndJsonTemplate -DpythonApisDir=${PYTHON_APIS_DIR}
