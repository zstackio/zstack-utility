import httplib
import json
import time

# return a dict containing API return value
def api_call(session_uuid, api_id, api_content):
    conn = httplib.HTTPConnection("localhost", 8080)
    headers = {"Content-Type": "application/json"}

    if session_uuid:
        api_content["session"] = {"uuid": session_uuid}

    api_body = {api_id: api_content}

    conn.request("POST", "/zstack/api", json.dumps(api_body))
    response = conn.getresponse()

    if response.status != 200:
        raise Exception("failed to make an API call, %s, %s" % (response.status, response.reason))

    rsp_body = response.read()

    rsp = json.loads(rsp_body)

    if rsp["state"] == "Done":
        return json.loads(rsp["result"])

    job_uuid = rsp["uuid"]
    def query_until_done():
        conn.request("GET", "/zstack/api/result/%s" % job_uuid)
        response = conn.getresponse()
        if response.status != 200:
            raise Exception("failed to query API result, %s, %s" % (response.status, response.reason))

        rsp_body = response.read()
        rsp = json.loads(rsp_body)
        if rsp["state"] == "Done":
            return json.loads(rsp["result"])

        time.sleep(1)
        print "Job[uuid:%s] is still in processing" % job_uuid
        return query_until_done()

    return query_until_done()



def error_if_fail(rsp):
    success = rsp.values()[0]["success"]
    if not success:    
        error = rsp.values()[0]["error"]
        raise Exception("failed to login, %s" % json.dumps(error))

def login():
    content = {
            "accountName": "admin",
            "password": "b109f3bbbc244eb82441917ed06d618b9008dd09b3befd1b5e07394c706a8bb980b1d7785e5976ec049b46df5f1326af5a2ea6d103fd07c95385ffab0cacbc86"
    }
    rsp = api_call(None, "org.zstack.header.identity.APILogInByAccountMsg", content)
    error_if_fail(rsp)

    session_uuid = rsp.values()[0]["inventory"]["uuid"]

    print "successfully login, session uuid is: %s" % session_uuid
    return session_uuid


def create_zone(session_uuid):
    content = {"name": "zone1"}

    rsp = api_call(session_uuid, "org.zstack.header.zone.APICreateZoneMsg", content)
    error_if_fail(rsp)

    print "successfully created zone1"


def logout(session_uuid):
    content = {"sessionUuid": session_uuid}
    rsp = api_call(None, "org.zstack.header.identity.APILogOutMsg", content)
    error_if_fail(rsp)

    print "successfully logout"


session_uuid = login()
create_zone(session_uuid)
logout(session_uuid)
