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

    def add_flow(self, dpid, match, actions, priority=1):
        """Add a new flow rule to a switch."""
        url = f"{self.base_url}/stats/flowentry/add"
        data = {
            "dpid": dpid,
            "priority": priority,
            "match": match,
            "actions": actions
        }
        response = requests.post(url, json=data)
        return response.status_code == 200

    def delete_dst_flow_match(self, priority, dpid, ip):
        """Delete a flow rule from a switch."""
        url = f"{self.base_url}/stats/flowentry/delete"
        data = {
            "dpid": dpid,
            "match": {
                "priority": priority,
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
                    #       "DB_ADDED", "DB_DELETED", "DB_INIT", "DB_GET"
                    #       "SW_STAT", "SW_BYPASS", "SW_COUNTER", "SW_BACKUP"
    dpid: Optional[str] = None
    ip: Optional[str] = None
    ipv6: Optional[str] = None
    services: Optional[List] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# Define an EventBus using Redis Pub/Sub
class EventBus:
    """Event bus using Redis Pub/Sub for decoupled event handling."""
    def __init__(self):
        self.redis_client = Redis(host="redis", port=6379)
    async def publish(self, channel, event):
        event_id = str(uuid.uuid4())
        event_data = {**event.__dict__, "event_id": event_id}
        response_channel = f"response_{event_id}"
        """Publish an event to a Redis channel."""
        await self.redis_client.publish(channel, json.dumps(event_data))
        # self.redis_client.publish(channel, event)
        # Wait for response
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(response_channel)
        async for message in pubsub.listen():
            if message["type"] == "message":
                response_data = json.loads(message["data"])
                await pubsub.unsubscribe(response_channel)
                return response_data
    async def subscribe(self, channel):
        """Subscribe to a Redis channel."""
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(channel)
        return pubsub
# Define a FlowEventHandler to process flow events
class FlowEventHandler:
    """Handles events related to flow changes in the SDN."""
    def __init__(self, event_bus):
        self.event_bus = event_bus
    async def listen(self):
        """Continuously listen for flow events."""
        pubsub = await self.event_bus.subscribe("flow_events")
        print("[INFO] Class FlowEventHandler: start Listening for flow events...")
        async for message in pubsub.listen():
            if message["type"] == "message":
                event_data = json.loads(message["data"])
                await self.process_event(event_data)
    async def process_event(self, event_data):
        response_channel = f"response_{event_data['event_id']}"
        """Process received events: 'FLOW_ADDED', 'FLOW_DELETED', 'FLOW_INIT', 'FLOW_GET', 'FLOW_GET_ALL'"""
        if event_data["event_type"] == "FLOW_ADDED":
            status = {"flow": "added", "dpid": event_data["dpid"]}
            await self.event_bus.redis_client.publish(response_channel, json.dumps(status))
            print(f"✅ Flow added for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "FLOW_DELETED":
            status = {"flow": "delete", "dpid": event_data["dpid"]}
            await self.event_bus.redis_client.publish(response_channel, json.dumps(status))
            print(f"✅ Flow removed for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "FLOW_INIT":
            status = {"flow": "init", "dpid": event_data["dpid"]}
            await self.event_bus.redis_client.publish(response_channel, json.dumps(status))
            print(f"✅ Flow initialize for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "FLOW_GET":
            # status = {"flow": "get", "dpid": event_data["dpid"]}
            Ryu = SDNController()
            print(type(event_data['dpid']))
            # print(event_data['ip'])
            # status = Ryu.get_src_flows_match('66817','192.168.1.1/32')
            status_src = Ryu.get_src_flows_match(event_data['dpid'],event_data['ip'])
            print(type(status_src))
            status_dst = Ryu.get_dst_flows_match(event_data['dpid'],event_data['ip'])
            print(type(status_dst))
            status = {key: status_src.get(key, []) + status_dst.get(key, []) for key in set(status_src) | set(status_dst)}

            # status = status_src[str(event_data['dpid'])].extend(status_dst[str(event_data['dpid'])])
            await self.event_bus.redis_client.publish(response_channel, json.dumps(status))
            # print(f"✅ Flow get for {event_data['dpid']}: {status}")
        else:
            print(f"❌ Error")
class SwitchEventHandler:
    def __init__(self, event_bus):
        self.event_bus = event_bus
    async def listen(self):
        """Continuously listen for switch events."""
        pubsub = await self.event_bus.subscribe("switch_events")
        print("[INFO] Class SwitchEventHandler: start Listening for switch events...")
        async for message in pubsub.listen():
            if message["type"] == "message":
                event_data = json.loads(message["data"])
                await self.process_event(event_data)
    async def process_event(self, event_data):
        response_channel = f"response_{event_data['event_id']}"
        """Process received events:'SW_STAT', 'SW_BYPASS', 'SW_COUNTER', 'SW_BACKUP'"""
        if event_data["event_type"] == "SW_STAT":
            status = {"status": "normal", "dpid": event_data["dpid"]}
            await self.event_bus.redis_client.publish(response_channel, json.dumps(status))
            print(f"✅ Switch Status for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "SW_BYPASS":
            status = {"status": "bypass", "dpid": event_data["dpid"]}
            await self.event_bus.redis_client.publish(response_channel, json.dumps(status))
            print(f"✅ Switch Status for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "SW_COUNTER":
            status = {"status": "monitor", "dpid": event_data["dpid"]}
            await self.event_bus.redis_client.publish(response_channel, json.dumps(status))
            print(f"✅ Switch Status for {event_data['dpid']}: {status}")
        elif event_data["event_type"] == "SW_BACKUP":
            status = {"status": "backup", "dpid": event_data["dpid"]}
            await self.event_bus.redis_client.publish(response_channel, json.dumps(status))
            print(f"✅ Switch Status for {event_data['dpid']}: {status}")
        else:
            print(f"❌ Error")

# class DatabaseEventHandler:
#     def __init__(self, event_bus):
#         self.event_bus = event_bus
#         self.pubsub = self.event_bus.subscribe("database_events")
#     def listen(self):
#         """Continuously listen for database events."""
#         print("Listening for database events...")
#     def process_event(self, event_data):

# Initialize Flask app and EventBus
app = Flask(__name__)
# redis = Redis(host='redis', port=6379)
event_bus = EventBus()

# default homepage
@app.route('/')
def hello():
    redis.incr('hits')
    counter = str(redis.get('hits'),'utf-8')
    return "This webpage has been viewed "+counter+" time(s)"

@app.route('/test')
def test():
    return "~~~lalala~~~"

# @app.route('/user/initialize', methods=['POST'])
# def user_initialize():
#     """
#     // HTTP request
#     curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/user/initialize -d
#     '{
#         "type":"clear",
#         "dpid":"0000000000010501",
#         "ip":"192.168.0.1/32"
#     }'

#     // HTTP response. if success, reponse client with following
# 	Result:
# 	Success
#     """
#     # Add a flow entry and publish an event.
#     data = request.json
#     event = Event("FLOW_INIT", dpid=data['dpid'], ip=data['ip'])
#     # return event.timestamp
#     # Publish event and get result
#     response = async_to_sync(event_bus.publish)("flow_events", event)
#     return jsonify(response), 201

# @app.route('/user/book', methods=['POST'])
# def user_book():
#     """
#     // HTTP request from HiOSS
#     curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/user/book -d
#     '{
#         "dpid":"0000000000010502", 
#         "ip":"61.222.79.172/32",
#         "services":[{"inport":"1280","outport":"1536","priority":"400"}]
#     }'

#     // HTTP response to HiOSS
# 	Sucess
#     """
#     # Add a flow entry and publish an event.
#     data = request.json
#     event = Event("FLOW_ADDED", dpid=data['dpid'], ip=data['ip'], services=data['services'])
#     response = async_to_sync(event_bus.publish)("flow_events", event)
#     return jsonify(response), 201
#     # Add a flow entry and publish an event.
@app.route('/user/get', methods=['POST'])
def user_get():
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
    event = Event("FLOW_GET", '66817', ip=data['ip'])
    response = async_to_sync(event_bus.publish)("flow_events", event)
    return jsonify(response), 201
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
    # Add a flow entry and publish an event.
    data = request.json
    event = Event("FLOW_GET", int(data['dpid'],16), ip=data['ip'])
    # event = Event("FLOW_GET", "66817", ip=data['ip'])
    response = async_to_sync(event_bus.publish)("flow_events", event)
    return jsonify(response), 201
@app.route('/flowentry/check', methods=['POST'])
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
    # Add a flow entry and publish an event.
    data = request.json
    event = Event("FLOW_GET", int(data['dpid'],16), ip=data['ip'])
    response = async_to_sync(event_bus.publish)("flow_events", event)
    print(type(response))
    return jsonify(response), 201
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
#     event = Event("SW_BYPASS", dpid=data['dpid'])
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
#     event = Event("SW_COUNTER", dpid=data['dpid'], ip=data['ip'])
#     response = async_to_sync(event_bus.publish)("switch_events", event)
#     return jsonify(response), 201
@app.route('/dpid/status/get', methods=['POST'])
def swich_status_get():
    """
    // HTTP request
    curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/dpid/status/get -d '{"dpid":"0000000000010504"}'

    Result:
	{"status":"normal"}
    """
    # Get switch status and publish an event.
    data = request.json
    event = Event("SW_STAT", dpid=data['dpid'])
    # Publish event and get result
    # await event_bus.publish("switch_events", event)
    response = async_to_sync(event_bus.publish)("switch_events", event)
    return jsonify(response), 201

# Define a route to add a flow, publishing a "FLOW_ADDED" event
# @app.route('/add_flow', methods=['POST'])
# def add_flow():
#     """Add a flow entry and publish an event."""
#     data = request.json
#     event = Event("FLOW_ADDED", data)
#     # Publish event
#     event_bus.publish("flow_events", event)
#     return jsonify({"message": "Flow added event published"}), 201

async def main():
    # Start the FlowEventHandler in a separate thread
    flow_handler = FlowEventHandler(event_bus)
    switch_handler = SwitchEventHandler(event_bus)
    # database_handler = DatabaseEventHandler(event_bus)
    # threading.Thread(target=flow_handler.listen, daemon=True).start()
    # await flow_handler.listen()
    # Start the SwitchEventHandler in a separate thread
    # await switch_handler.listen()
    # Start the DatabaseEventHandler in a separate thread
    # await database_handler.listen()

    await asyncio.gather(
        flow_handler.listen(),
        switch_handler.listen()
        # database_handler.listen()
    )

threading.Thread(target=asyncio.run, args=(main(),), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
