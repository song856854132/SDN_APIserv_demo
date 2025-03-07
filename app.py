from flask import Flask, request, jsonify
from aioredis import Redis
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from asgiref.sync import async_to_sync
import json
import threading
import uuid
import asyncio
import requests
import logging
import mysql.connector
from mysql.connector import Error

class DBconnector:
    def __init__(self):
        """Initialize a connection to the MySQL database."""
        try:
            self.connection = mysql.connector.connect(
                host="db", user="operator", password="operator", database="security", auth_plugin='mysql_native_password', ssl_disabled=True
            )
            if self.connection.is_connected():
                print("✅ Connected to MySQL database")
        except Error as e:
            print("❌ Error while connecting to MySQL:", e)
            self.connection = None

    def fetch(self, query, params=(), single=False):
        """execute SELECT queries."""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(query, params)
        result = cursor.fetchone() if single else cursor.fetchall()
        cursor.close()
        return result

    def execute(self, query, params=()):
        """execute INSERT/UPDATE/DELETE queries."""
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        self.connection.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected

    def get_UserList_by_ip(self, input_ip, order_by_priority=False):
        """Fetch users by IP, optionally ordered by priority descending."""
        query = "SELECT * FROM UserList WHERE ip = %s"
        if order_by_priority:
            query += " ORDER BY priority DESC"
        return self.fetch(query, (input_ip))
    
    def del_UserList_by_ip(self, input_ip, input_dpid=None):
        """Delete users by IP, optionally filtering by DPID."""
        query = "DELETE FROM UserList WHERE ip = %s"
        params = [input_ip]
        if input_dpid:
            query += " AND dpid = %s"
            params.append(input_dpid)
        return self.execute(query, (params))

    def add_UserList_by_ip(self, input_ip, input_dpid, in_port, out_port, priority, use_ipv6=0, input_ipv6=None, mirror_downlink=0):
        """Add users by IP, DPID, src_port, dst_port"""
        service_port = in_port + ',' + out_port
        query = "INSERT INTO UserList VALUE(%s,%s,%s,%s,%s,%s,%s)"
        params = [input_ip,input_dpid,service_port,priority,use_ipv6,input_ipv6,mirror_downlink]
        if not use_ipv6:
            return self.execute(query, (params))

    def get_EntryList_by_ip(self, input_ip, input_dpid=None):
        """Fetch entries by IP, optionally filtering by DPID."""
        query = "SELECT * FROM EntryList WHERE ip = %s"
        params = [input_ip]
        if input_dpid:
            query += " AND dpid = %s"
            params.append(input_dpid)
        return self.fetch(query, params)

    def del_EntryList_by_ip(self, input_ip, input_dpid=None):
        """Delete entries by IP, optionally filtering by DPID."""
        query = "DELETE FROM EntryList WHERE ip = %s"
        params = [input_ip]
        if input_dpid:
            query += " AND dpid = %s"
            params.append(input_dpid)
        return self.execute(query, (params))

    def add_EntryList_by_ip(self, input_ip, input_dpid, in_port, out_port, network, use_ipv6=0, input_ipv6=None):
        """Add entries by IP, DPID, src_port, dst_port"""
        query = "INSERT INTO EntryList VALUE(%s,%s,%s,%s,%s,%s,%s)"
        params = [input_dpid,input_ip,network,in_port,out_port,use_ipv6,input_ipv6]
        if not use_ipv6:
            return self.execute(query, (params))    

    def count_EntryList(self, input_dpid, use_ipv6=None):
        """Count entries by DPID, optionally filtering by IPv6 usage."""
        query = "SELECT COUNT(*) as cnt FROM EntryList WHERE dpid = %s"
        params = [input_dpid]
        if use_ipv6 is not None:
            query += " AND use_ipv6 = %s"
            params.append(use_ipv6)
        result = self.fetch(query, params, single=True)
        return result["cnt"] if result else 0

    def update_DpidStatus(self, dpid, dpid_ip, status):
        """Insert or update DPID status."""
        query = """
        INSERT INTO DpidStatus (dpid, dpid_ip, status)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE status = %s
        """
        return self.execute(query, (dpid, dpid_ip, status, status))

    def get_DpidStatus(self, dpid):
        """Fetch the status of a given DPID."""
        query = "SELECT status FROM DpidStatus WHERE dpid = %s"
        result = self.fetch(query, (dpid,), single=True)
        return result["status"] if result else None

    def close(self):
        """Close the database connection."""
        if self.connection and self.connection.is_connected():
            self.connection.close()

class SDNController:
    def __init__(self, base_url="http://10.250.28.182:8080"):
        self.base_url = base_url

    def get_switches(self):
        """Retrieve a list of switches connected to the controller."""
        url = f"{self.base_url}/v1.0/topology/switches"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else None

    def get_flows(self, dpid):
        """Retrieve flow table for a given switch."""
        url = f"{self.base_url}/stats/flow/{dpid}"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else None

    def get_src_flows_match(self, dpid, ip):
        url = f"{self.base_url}/stats/flow/{dpid}"
        data = {
            "dpid": dpid,
            "match": {
                "dl_type": "2048",
                "nw_src": ip
            }
        }
        response = requests.get(url, json=data)
        # print(response.json())
        return response.json() if response.status_code == 200 else None

    def get_dst_flows_match(self, dpid, ip):
        url = f"{self.base_url}/stats/flow/{dpid}"
        data = {
            "dpid": dpid,
            "match": {
                "dl_type": "2048",
                "nw_dst": ip
            }
        }
        response = requests.get(url, json=data)
        # print(response.json())
        return response.json() if response.status_code == 200 else None

    def exp_add_dst_flow_hashfield(self, dpid, ip, in_port, out_port, priority="1"):
        """Add a new flow rule to a switch via experimenter hashfield: Hashmap(ipv4_dst,ipv4_src,ip_proto) collision value go to same physical interface"""
        """Because traditional /stats/flow/add will cause the packet out of order due to the LACP aggregation hapzardly redistributing the traffic"""
        url = f"{self.base_url}/novi/flow_mod"
        data = {
            "priority":priority,
            "dpid":dpid,
            "command":"add",
            "table_id":1,
            "instructions":[{"type":"apply","actions":[{"type":"experimenter","exp_type":"hash_fields","fields":["ipv4_dst","ipv4_src","ip_proto"]},{"type":"output","port":out_port}]}],
            "match":{"eth_type": 2048,"ipv4_dst": ip,"in_port": in_port}
        }
        response = requests.post(url, json=data)
        # print(response.status_code)
        # print(response.text)
        return response.status_code == 200

    def exp_add_src_flow_hashfield(self, dpid, ip, in_port, out_port, priority="1"):
        """Add a new flow rule to a switch."""
        url = f"{self.base_url}/novi/flow_mod"
        data = {
            "priority":priority,
            "dpid":dpid,
            "command":"add",
            "table_id":1,
            "instructions":[{"type":"apply","actions":[{"type":"experimenter","exp_type":"hash_fields","fields":["ipv4_dst","ipv4_src","ip_proto"]},{"type":"output","port":out_port}]}],
            "match":{"eth_type": 2048,"ipv4_src": ip,"in_port": in_port}
        }
        response = requests.post(url, json=data)
        # print(response.status_code)
        # print(response.text)
        return response.status_code == 200

    def delete_dst_flow_match(self, priority, dpid, ip):
        """Delete a flow rule from a switch."""
        url = f"{self.base_url}/stats/flowentry/delete"
        data = {
            "priority": priority,
            "dpid": dpid,
            "table_id": 1,
            "match": {
                "dl_type": "2048",
                "nw_dst": ip
            }
        }
        response = requests.post(url, json=data)
        return response.status_code == 200

    def delete_src_flow_match(self, priority, dpid, ip):
        """Delete a flow rule from a switch."""
        url = f"{self.base_url}/stats/flowentry/delete"
        data = {
            "priority": priority,
            "dpid": dpid,
            "table_id": 1,
            "match": {
                "dl_type": "2048",
                "nw_src": ip
            }
        }
        response = requests.post(url, json=data)
        return response.status_code == 200

# Define a base Event class
@dataclass
class Event:
    """unify event format for SDN API server."""
    # {
    #     "event_type": "<string>",  
    #     "dpid": "<string>",
    #     "ip": "<string>",
    #     "ipv6": "<string>",
    #     "services": [
    #         {
    #             "in_port": "<integer>",
    #             "out_port": "<integer>",
    #             "priority": "<integer>"
    #         }
    #     ],
    #     "timestamp": "<ISO 8601 timestamp>"
    # }
    event_type: str # e.g., "FLOW_ADDED", "FLOW_DELETED", "FLOW_INIT", "FLOW_GET"
                    #       "DB_ADDED_USER", "DB_DELETED_USER", "DB_INIT_USER", "DB_GET_USER", "DB_GET_ENTRY", "DB_COUNT_ENTRY"
                    #       "SW_STAT", "SW_BYPASS", "SW_COUNTER", "SW_BACKUP"
    dpid: Optional[str] = None
    ip: Optional[str] = None
    ipv6: Optional[str] = None
    services: Optional[List] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

# Define an EventBus using Redis Pub/Sub
class EventBus:
    def __init__(self):
        pass  # No persistent client to avoid event loop issues

    async def publish(self, channel, event):
        redis_client = None
        try:
            redis_client = await Redis(host="redis", port=6379, decode_responses=True)
            event_id = str(uuid.uuid4())
            event_data = {**event.__dict__, "event_id": event_id}
            response_channel = f"response_{event_id}"
            await redis_client.publish(channel, json.dumps(event_data))
            pubsub = redis_client.pubsub()  # No await here
            await pubsub.subscribe(response_channel)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    response_data = json.loads(message["data"])
                    await pubsub.unsubscribe(response_channel)
                    return response_data
        except Exception as e:
            print(f"❌ Error in publish: {e}")
            raise e
        finally:
            if redis_client:
                await redis_client.close()

    async def publish_response(self, channel, data):
        redis_client = None
        try:
            redis_client = await Redis(host="redis", port=6379, decode_responses=True)
            await redis_client.publish(channel, json.dumps(data))
        except Exception as e:
            print(f"❌ Error in publish_response: {e}")
            raise e
        finally:
            if redis_client:
                await redis_client.close()

    async def subscribe(self, channel):
        redis_client = await Redis(host="redis", port=6379, decode_responses=True)
        pubsub = redis_client.pubsub()  # No await here
        await pubsub.subscribe(channel)
        return pubsub
        
class FlowEventHandler:
    def __init__(self, event_bus):
        self.event_bus = event_bus

    async def listen(self):
        pubsub = await self.event_bus.subscribe("flow_events")
        print("[INFO] FlowEventHandler: Listening for flow events...")
        async for message in pubsub.listen():
            if message["type"] == "message":
                event_data = json.loads(message["data"])
                await self.process_event(event_data)

    async def process_event(self, event_data):
        response_channel = f"response_{event_data['event_id']}"
        if event_data["event_type"] == "FLOW_ADDED":
            Ryu = SDNController()
            sorted_services = sorted(event_data['services'], key=lambda s: int(s["priority"]), reverse=True)
            inner = [x for service in sorted_services for x in (int(service["inport"]), int(service["outport"]))]
            service_chain = [256] + inner + [512]
            for x in range(0, len(service_chain), 2):
                status_src = Ryu.exp_add_dst_flow_hashfield(dpid=event_data['dpid'], ip=event_data['ip'], in_port=int(service_chain[x+1]), out_port=int(service_chain[x]), priority="32768")
                status_dst = Ryu.exp_add_src_flow_hashfield(dpid=event_data['dpid'], ip=event_data['ip'], in_port=int(service_chain[x]), out_port=int(service_chain[x+1]), priority="32768")
                print(f"✅ src = {status_src} and dst = {status_dst} ✅")
            status = {"flow": "added", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ Flow added for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "FLOW_DELETED":
            Ryu = SDNController()
            status_src_del = Ryu.delete_src_flow_match(priority="32768", dpid=event_data['dpid'], ip=event_data['ip'])
            status_dst_del = Ryu.delete_dst_flow_match(priority="32768", dpid=event_data['dpid'], ip=event_data['ip'])
            print(f"✅ src = {status_src_del} and dst = {status_dst_del} ✅")
            status = {"flow": "delete", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ Flow removed for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "FLOW_INIT":
            Ryu = SDNController()
            status_src_add = Ryu.exp_add_src_flow_hashfield(dpid=event_data['dpid'], ip=event_data['ip'], in_port=256, out_port=512, priority="32768")
            status_dst_add = Ryu.exp_add_dst_flow_hashfield(dpid=event_data['dpid'], ip=event_data['ip'], in_port=512, out_port=256, priority="32768")
            print(f"✅ src = {status_src_add} and dst = {status_dst_add} ✅")
            status = {"flow": "init", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ Flow initialized for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "FLOW_GET":
            Ryu = SDNController()
            status_src = Ryu.get_src_flows_match(dpid=event_data['dpid'], ip=event_data['ip'])
            status_dst = Ryu.get_dst_flows_match(dpid=event_data['dpid'], ip=event_data['ip'])
            status = {key: status_src.get(key, []) + status_dst.get(key, []) for key in set(status_src) | set(status_dst)}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ Flow retrieved for {event_data['dpid']}")

class SwitchEventHandler:
    def __init__(self, event_bus):
        self.event_bus = event_bus
    async def listen(self):
        """Continuously listen for switch events."""
        pubsub = await self.event_bus.subscribe("switch_events")
        print("[INFO] SwitchEventHandler: Listening for switch events...")
        async for message in pubsub.listen():
            if message["type"] == "message":
                event_data = json.loads(message["data"])
                await self.process_event(event_data)
    async def process_event(self, event_data):
        response_channel = f"response_{event_data['event_id']}"
        """Process received events:'SW_STAT', 'SW_BYPASS', 'SW_COUNTER', 'SW_BACKUP'"""
        if event_data["event_type"] == "SW_STAT":
            status = {"status": "normal", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ Switch Status for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "SW_BYPASS":
            status = {"status": "bypass", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ Switch Status for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "SW_COUNTER":
            status = {"status": "monitor", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ Switch Status for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "SW_BACKUP":
            status = {"status": "backup", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ Switch Status for {event_data['dpid']}: {status}")
        else:
            print(f"❌ Error")

class DatabaseEventHandler:
    def __init__(self, event_bus):
        self.event_bus = event_bus
    async def listen(self):
        """Continuously listen for database events."""
        pubsub = await self.event_bus.subscribe("database_events")
        print("[INFO] DatabaseEventHandler: Listening for database events...")
        async for message in pubsub.listen():
            if message["type"] == "message":
                event_data = json.loads(message["data"])
                await self.process_event(event_data)
    async def process_event(self, event_data):
        response_channel = f"response_{event_data['event_id']}"
        """"Process received events : 'DB_ADDED_USER', 'DB_DELETED_USER', 'DB_INIT_USER', 'DB_GET_USER'"""
        if event_data["event_type"] == "DB_INIT_USER":
            MySQL = DBconnector()
            status_dst = MySQL.add_EntryList_by_ip(input_ip=event_data['ip'], input_dpid=event_data['dpid'], in_port='512', out_port='256', network='dst')
            status_src = MySQL.add_EntryList_by_ip(input_ip=event_data['ip'], input_dpid=event_data['dpid'], in_port='256', out_port='512', network='src')
            # status = {"status": "normal", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status_dst)
            await self.event_bus.publish_response(response_channel, status_src)
            print(f"✅ DataBase Status: {status_dst} 🚀 {status_src}")
        elif event_data["event_type"] == "DB_ADDED_USER":
            MySQL = DBconnector()
            for x in range(0, len(event_data['services'])):
                status_user = MySQL.add_UserList_by_ip(input_dpid=event_data['dpid'], input_ip=event_data['ip'], in_port=event_data['services'][x]['inport'], out_port=event_data['services'][x]['outport'], priority=event_data['services'][x]['priority'])
                print(f"✅ status_user = {status_user}")
            sorted_services = sorted(event_data['services'], key=lambda s: int(s["priority"]), reverse=True)
            inner = [x for service in sorted_services for x in (int(service["inport"]), int(service["outport"]))]
            service_chain = [256] + inner + [512]
            for x in range(0, len(service_chain), 2):
                # add_EntryList_by_ip(input_ip, input_dpid, in_port, out_port, network):
                status_src = MySQL.add_EntryList_by_ip(input_dpid=event_data['dpid'], input_ip=event_data['ip'], in_port=service_chain[x+1], out_port=service_chain[x], network='dst')
                status_dst = MySQL.add_EntryList_by_ip(input_dpid=event_data['dpid'], input_ip=event_data['ip'], in_port=service_chain[x], out_port=service_chain[x+1], network='src')
                print(f"✅ src = {status_src} and dst = {status_dst} ✅")
            status = {"entrylist": "added", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ DataBase Status: {status}")
        elif event_data["event_type"] == "DB_DELETED_USER":
            MySQL = DBconnector()
            status_entry = MySQL.del_EntryList_by_ip(input_ip=event_data['ip'],input_dpid=event_data['dpid'])
            status_user = MySQL.del_UserList_by_ip(input_ip=event_data['ip'],input_dpid=event_data['dpid'])
            # status = {"status": "backup", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status_entry)
            await self.event_bus.publish_response(response_channel, status_user)
            print(f"✅ DataBase Status: {status_entry} 🚀 {status_user}")
        elif event_data["event_type"] == "DB_GET_USER":
            MySQL = DBconnector()
            status = MySQL.get_UserList_by_ip(input_ip=event_data['ip'])
            # status = {"status": "monitor", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ DataBase Status: {status}")
        elif event_data["event_type"] == "DB_GET_ENTRY":
            MySQL = DBconnector()
            status = MySQL.get_EntryList_by_ip(input_ip=event_data['ip'],input_dpid=event_data['dpid'])
            # status = {"status": "monitor", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ DataBase Status: {status}")
        elif event_data["event_type"] == "DB_COUNT_ENTRY":
            MySQL = DBconnector()
            status = MySQL.count_EntryList(input_ip=event_data['ip'])
            # status = {"status": "monitor", "dpid": event_data["dpid"]}
            await self.event_bus.publish_response(response_channel, status)
            print(f"✅ DataBase Status: {status}")
        else:
            print(f"❌ Error")


# Initialize Flask app and EventBus
app = Flask(__name__)

event_bus = EventBus()
# logging.getLogger("aioredis").setLevel(logging.DEBUG)
# default homepage
# @app.route('/')
# def hello():
#     redis.incr('hits')
#     counter = str(redis.get('hits'),'utf-8')
#     return "This webpage has been viewed "+counter+" time(s)"

@app.route('/user/delete', methods=['POST']) ### FINISH ###
def user_delete():
    """
    // HTTP request
    curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/user/initialize -d
    '{
        "type":"delete",
        "dpid":"0000000000010501",
        "ip":"192.168.0.1/32"
    }'

    // HTTP response. if success, reponse client with following
	Result:
	Success
    """
    data = request.json
    # Add a flow entry and publish an event.
    event1 = Event("DB_DELETED_USER", dpid=data['dpid'], ip=data['ip'])
    event2 = Event("FLOW_DELETED", dpid=int(data['dpid'],16), ip=data['ip'])
    response_db = async_to_sync(event_bus.publish)("database_events", event1)
    response_ryu = async_to_sync(event_bus.publish)("flow_events", event2)

    # checking completely purge
    event3 = Event("DB_GET_ENTRY", dpid=data['dpid'], ip=data['ip'])
    event4 = Event("FLOW_GET", dpid=int(data['dpid'],16), ip=data['ip'])
    response_db_tmp = async_to_sync(event_bus.publish)("database_events", event3)
    response_ryu_tmp = async_to_sync(event_bus.publish)("flow_events", event4)
    # print(response_db_tmp)
    # print(response_ryu_tmp)
    flow_num_db = len(response_db_tmp)
    flow_num_sw = len(response_ryu_tmp[str(int(data['dpid'],16))])
    if not (flow_num_db or flow_num_sw):
        return jsonify(response_ryu), 201
    else:
        return "Failed", 501
 
@app.route('/user/initialize', methods=['POST']) ### FINISH ###
def user_initialize():
    """
    // HTTP request
    curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/user/initialize -d
    '{
        "type":"clear",
        "dpid":"0000000000010501",
        "ip":"192.168.0.1/32"
    }'

    // HTTP response. if success, reponse client with following
	Result:
	Success
    """
    # Add a flow entry and publish an event.
    data = request.json
    event1 = Event("FLOW_DELETED", dpid=int(data['dpid'],16), ip=data['ip'])
    event2 = Event("FLOW_INIT", dpid=int(data['dpid'],16), ip=data['ip'])
    event3 = Event("DB_DELETED_USER", dpid=data['dpid'], ip=data['ip'])
    event4 = Event("DB_INIT_USER", dpid=data['dpid'], ip=data['ip'])
    event5 = Event("DB_GET_ENTRY", dpid=data['dpid'], ip=data['ip'])
    event6 = Event("FLOW_GET", dpid=int(data['dpid'],16), ip=data['ip'])

    response1 = async_to_sync(event_bus.publish)("flow_events", event1)
    response2 = async_to_sync(event_bus.publish)("flow_events", event2)
    response3 = async_to_sync(event_bus.publish)("database_events", event3)
    response4 = async_to_sync(event_bus.publish)("database_events", event4)

    response_db_tmp = async_to_sync(event_bus.publish)("database_events", event5)
    response_ryu_tmp = async_to_sync(event_bus.publish)("flow_events", event6)

    flow_num_db = len(response_db_tmp)
    flow_num_sw = len(response_ryu_tmp[str(int(data['dpid'],16))])
    if (flow_num_db == 2 and flow_num_sw == 2):
        return "Success", 201
    else:
        return "Failed", 501

@app.route('/user/book', methods=['POST']) ### FINISH ###
def user_book():
    """
    // HTTP request from HiOSS
    curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/user/book -d
    '{
        "dpid":"0000000000010502", 
        "ip":"61.222.79.172/32",
        "services":[{"inport":"1280","outport":"1536","priority":"400"}]
    }'

    // HTTP response to HiOSS
	Sucess
    """
    # Add a flow entry and publish an event.
    data = request.json
    event1 = Event("FLOW_DELETED", dpid=int(data['dpid'],16), ip=data['ip'])
    event2 = Event("FLOW_ADDED", dpid=int(data['dpid'],16), ip=data['ip'], services=data['services'])
    event3 = Event("DB_DELETED_USER", dpid=data['dpid'], ip=data['ip'])
    event4 = Event("DB_ADDED_USER", dpid=data['dpid'], ip=data['ip'], services=data['services'])
    event5 = Event("DB_GET_ENTRY", dpid=data['dpid'], ip=data['ip'])
    event6 = Event("FLOW_GET", dpid=int(data['dpid'],16), ip=data['ip'])

    response1 = async_to_sync(event_bus.publish)("flow_events", event1)
    response2 = async_to_sync(event_bus.publish)("flow_events", event2)
    response3 = async_to_sync(event_bus.publish)("database_events", event3)
    response4 = async_to_sync(event_bus.publish)("database_events", event4)

    response_db_tmp = async_to_sync(event_bus.publish)("database_events", event5)
    response_ryu_tmp = async_to_sync(event_bus.publish)("flow_events", event6)

    flow_num_db = len(response_db_tmp)
    flow_num_sw = len(response_ryu_tmp[str(int(data['dpid'],16))])
    if (flow_num_db == 2 and flow_num_sw == 2):
        return "Success", 201
    else:
        return "Failed", 501

@app.route('/user/get', methods=['POST']) ### FINISH ###
def DB_GET_user():
    """
    // HTTP request
    curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/user/get -d 
    '{
        "ip":"192.168.0.1/32"
    }'
    // HTTP response
    {"book":[{"dpid":"0000000000010504","service_ports":"1280,1536","priority":"400"},
             {"dpid":"0000000000010504","service_ports":"768,1024","priority":"200"}]}               
    */
    """
    # Add a flow entry and publish an event.
    data = request.json
    event = Event("DB_GET_USER", ip=data['ip'])
    response = async_to_sync(event_bus.publish)("database_events", event)
    
    keys_to_remove = {"ip", "ipv6", "mirror_downlink", "use_ipv6"}
    cleaned_data = {
        "book": [
        {k: v for k, v in entry.items() if k not in keys_to_remove}
        for entry in response
    ]}

    return jsonify(cleaned_data)

@app.route('/flowentry', methods=['POST'])
def flowentry_printall():
    """
    // HTTP request
    curl -X POST -H "Content-Type:application/json" http://10.250.31.71:9000/flowentry -d 
    '{
        "dpid":"0000000000010504", 
        "ip":"192.168.0.1/32",
        "type": "controller"
    }'
    
    // HTTP response, API Result
    {"66820":[{"match":{"dl_type":2048,"nw_src":"192.168.0.1/255.255.255.255","in_port":1536},"actions":{"OUTPUT":"512"}},
              {"match":{"dl_type":2048,"nw_src":"192.168.0.1/255.255.255.255","in_port":256},"actions":{"OUTPUT":"1280"}},
              {"match":{"dl_type":2048,"nw_dst":"192.168.0.1/255.255.255.255","in_port":512},"actions":{"OUTPUT":"1536"}},
              {"match":{"dl_type":2048,"nw_dst":"192.168.0.1/255.255.255.255","in_port":1280},"actions":{"OUTPUT":"256"}}]}
    """
    data = request.json
    # Add a flow entry and publish an event.
    event1 = Event("DB_GET_ENTRY", dpid=data['dpid'], ip=data['ip'])
    event2 = Event("FLOW_GET", dpid=int(data['dpid'],16), ip=data['ip'])
    response_db = async_to_sync(event_bus.publish)("database_events", event1)
    # print(f"DATABASE RESULT ------X-X----->{response_db}<------X-X-----")
    response_ryu = async_to_sync(event_bus.publish)("flow_events", event2)
    
    # List of keys to remove (like using `sed` to delete fields)
    keys_to_remove = {"byte_count", "cookie", "duration_nsec", "duration_sec", "flags",
                  "hard_timeout", "idle_timeout", "length", "packet_count", "priority", "table_id"}
    # Process and clean JSON
    cleaned_data = {
        data['dpid']: [
            {k: [a for a in v if a.startswith("OUTPUT:")] if k == "actions" else v
            for k, v in entry.items() if k not in keys_to_remove}
            for entry in response_ryu[str(int(data['dpid'],16))]
        ]
    }

    # exam the comfirmation
    # if DataFormat(response_ryu) == DataFormat(response_db)
    flow_num_db = len(response_db)
    flow_num_sw = len(response_ryu[str(int(data['dpid'],16))])
    if (flow_num_db == flow_num_sw):
        return jsonify(cleaned_data)
    else:
        return "SW Flow and DB Flow Mismatch", 501
    
    # return jsonify(response), 201

@app.route('/flowentry/check', methods=['POST']) ### FINISH ###
def flowentry_printnumber():
    """
    // HTTP request
    curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/flowentry/check -d 
    '{
        "dpid":"0000000000010504", 
        "ip":"192.168.0.1/32"
    }'

    // HTTP response Result of API to HiOSS client:
	{"check":"Success","flow_num_db":"4","flow_num_sw":"4"}
    """
    data = request.json
    # Add a flow entry and publish an event.
    event1 = Event("DB_GET_ENTRY", dpid=data['dpid'], ip=data['ip'])
    event2 = Event("FLOW_GET", dpid=int(data['dpid'],16), ip=data['ip'])
    response_db = async_to_sync(event_bus.publish)("database_events", event1)
    response_ryu = async_to_sync(event_bus.publish)("flow_events", event2)
    # print(response_db)
    # print(response_ryu)
    flow_num_db = len(response_db)
    flow_num_sw = len(response_ryu[str(int(data['dpid'],16))])
    return jsonify({"check": "Success" if flow_num_db == flow_num_sw else "Fail","flow_num_db": flow_num_db,"flow_num_sw": flow_num_sw})
    # return jsonify(response), 201

# @app.route('/flowentry/default', methods=['POST'])
# def flowentry_default():
#     """
#     // HTTP request
#     curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/flowentry/default -d 
#     '{
#         "dpid":"0000000000010504"
#     }'

#     // HTTP response
#     Success
#     */
#     """
#     # Add a flow entry and publish an event.
#     data = request.json
#     event = Event("SW_BYPASS", dpid=int(data['dpid'],16))
#     response = async_to_sync(event_bus.publish)("switch_events", event)
#     return jsonify(response), 201

# @app.route('/traffic', methods=['POST'])
# def traffic():
#     """
#     // HTTP request
#     curl -X POST -H "Content-Type:application/json" http://10.250.31.71:9000/traffic -d 
#     '{
#         "dpid":"0000000000010504", 
#         "ip": "192.168.0.1/32"
#     }'

#     // HTTP response
#     {"data": [{"in_port": 1536,"byte_count": 0,"packet_count": 0,"actions": ["EXPERIMENTER: {experimenter:4278190082, data:/wAABgOAABgAgAAWAIAAFAAAAAAAAAAA}","OUTPUT:512"]},
#               {"in_port": 256,"byte_count": 0,"packet_count": 0,"actions": ["EXPERIMENTER: {experimenter:4278190082, data:/wAABgOAABgAgAAWAIAAFAAAAAAAAAAA}","OUTPUT:1280"]},
#               {"in_port": 512,"byte_count": 0,"packet_count": 0,"actions": ["EXPERIMENTER: {experimenter:4278190082, data:/wAABgOAABgAgAAWAIAAFAAAAAAAAAAA}","OUTPUT:1536"]},
#               {"in_port": 1280,"byte_count": 0,"packet_count": 0,"actions": ["EXPERIMENTER: {experimenter:4278190082, data:/wAABgOAABgAgAAWAIAAFAAAAAAAAAAA}","OUTPUT:256"]}]}
#     """
#     # Add a flow entry and publish an event.
#     data = request.json
#     event = Event("SW_COUNTER", dpid=int(data['dpid'],16), ip=data['ip'])
#     response = async_to_sync(event_bus.publish)("switch_events", event)
#     return jsonify(response), 201

# @app.route('/dpid/status/get', methods=['POST'])
# def swich_status_get():
#     """
#     // HTTP request
#     curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/dpid/status/get -d '{"dpid":"0000000000010504"}'

#     Result:
# 	{"status":"normal"}
#     """
#     # Get switch status and publish an event.
#     data = request.json
#     event = Event("SW_STAT", dpid=int(data['dpid'],16))
#     # Publish event and get result
#     # await event_bus.publish("switch_events", event)
#     response = async_to_sync(event_bus.publish)("switch_events", event)
#     return jsonify(response), 201


async def main():
    # Start the FlowEventHandler in a separate thread
    flow_handler = FlowEventHandler(event_bus)
    switch_handler = SwitchEventHandler(event_bus)
    database_handler = DatabaseEventHandler(event_bus)

    await asyncio.gather(
        flow_handler.listen(),
        switch_handler.listen(),
        database_handler.listen()
    )

threading.Thread(target=asyncio.run, args=(main(),), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
