from flask import Flask, request, jsonify
from redis import Redis
from dataclasses import dataclass, field
from typing import List, Optional
import json
import threading
from datetime import datetime



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
    def publish(self, channel, event):
        """Publish an event to a Redis channel."""
        self.redis_client.publish(channel, json.dumps(event.__dict__))
        # self.redis_client.publish(channel, event)
    def subscribe(self, channel):
        """Subscribe to a Redis channel."""
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe(channel)
        return pubsub
# Define a FlowEventHandler to process flow events
class FlowEventHandler:
    """Handles events related to flow changes in the SDN."""
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.pubsub = self.event_bus.subscribe("flow_events")
    def listen(self):
        """Continuously listen for flow events."""
        print("[INFO] Class FlowEventHandler: start Listening for flow events...")
        for message in self.pubsub.listen():
            if message["type"] == "message":
                event_data = json.loads(message["data"])
                self.process_event(event_data)
    def process_event(self, event_data):
        """Process received events."""
        if event_data["event_type"] == "FLOW_ADDED":
            print(f"✅ Flow added: {event_data['data']}")
        elif event_data["event_type"] == "FLOW_DELETED":
            print(f"❌ Flow removed: {event_data['data']}")

class SwitchEventHandler:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.pubsub = self.event_bus.subscribe("switch_events")
    def listen(self):
        """Continuously listen for switch events."""
        print("[INFO] Class SwitchEventHandler: start Listening for switch events...")
        for message in self.pubsub.listen():
            if message["type"] == "message":
                event_data = json.loads(message["data"])
                self.process_event(event_data)
    def process_event(self, event_data):
        """Process received events:'SW_STAT', 'SW_BYPASS', 'SW_COUNTER', 'SW_BACKUP'"""
        if event_data["event_type"] == "SW_STAT":
            print(f"✅ Switch STAT: {event_data}")
        elif event_data["event_type"] == "":
            print(f"❌ Flow removed: {event_data['data']}")
        elif event_data["event_type"] == "":
            print()
        elif event_data["event_type"] == "":
            print()
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
redis = Redis(host='redis', port=6379)
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

@app.route('/user/initialize', methods=['POST'])
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
    event = Event("FLOW_INIT", dpid=data['dpid'], ip=data['ip'])
    return event.timestamp
    # Publish event
    # event_bus.publish("flow_events", event)
    # return jsonify({"message": "Flow added event published"}), 201

@app.route('/user/book', methods=['POST'])
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
    event = Event("FLOW_ADDED", dpid=data['dpid'], ip=data['ip'], services=data['services'])
    return event.timestamp
    # Add a flow entry and publish an event.
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
    event = Event("FLOW_GET", ip=data['ip'])
    return event.timestamp
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
    event = Event("FLOW_GET", dpid=data['dpid'], ip=data['ip'])
    return event.timestamp
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
    event = Event("FLOW_GET", dpid=data['dpid'], ip=data['ip'])
    return event.timestamp
@app.route('/flowentry/default', methods=['POST'])
def flowentry_default():
    """
    // HTTP request
    curl -X POST -H "Content-Type:application/json" http://10.250.28.181:9000/flowentry/default -d 
    '{
        "dpid":"0000000000010504"
    }'

    // HTTP response
    Success
    */
    """
    # Add a flow entry and publish an event.
    data = request.json
    event = Event("SW_BYPASS", dpid=data['dpid'])
    return event.timestamp
@app.route('/traffic', methods=['POST'])
def traffic():
    """
    // HTTP request
    curl -X POST -H "Content-Type:application/json" http://10.250.31.71:9000/traffic -d 
    '{
        "dpid":"0000000000010504", 
        "ip": "192.168.0.1/32"
    }'

    // HTTP response
    {"data": [{"in_port": 1536,"byte_count": 0,"packet_count": 0,"actions": ["EXPERIMENTER: {experimenter:4278190082, data:/wAABgOAABgAgAAWAIAAFAAAAAAAAAAA}","OUTPUT:512"]},
              {"in_port": 256,"byte_count": 0,"packet_count": 0,"actions": ["EXPERIMENTER: {experimenter:4278190082, data:/wAABgOAABgAgAAWAIAAFAAAAAAAAAAA}","OUTPUT:1280"]},
              {"in_port": 512,"byte_count": 0,"packet_count": 0,"actions": ["EXPERIMENTER: {experimenter:4278190082, data:/wAABgOAABgAgAAWAIAAFAAAAAAAAAAA}","OUTPUT:1536"]},
              {"in_port": 1280,"byte_count": 0,"packet_count": 0,"actions": ["EXPERIMENTER: {experimenter:4278190082, data:/wAABgOAABgAgAAWAIAAFAAAAAAAAAAA}","OUTPUT:256"]}]}
    """
    # Add a flow entry and publish an event.
    data = request.json
    event = Event("SW_COUNTER", dpid=data['dpid'], ip=data['ip'])
    return event.timestamp
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
    # Publish event
    event_bus.publish("switch_events", event)
    return jsonify({"message": "Switch status is..."}), 201

# Define a route to add a flow, publishing a "FLOW_ADDED" event
# @app.route('/add_flow', methods=['POST'])
# def add_flow():
#     """Add a flow entry and publish an event."""
#     data = request.json
#     event = Event("FLOW_ADDED", data)
#     # Publish event
#     event_bus.publish("flow_events", event)
#     return jsonify({"message": "Flow added event published"}), 201

# Start the FlowEventHandler in a separate thread
# flow_handler = FlowEventHandler(event_bus)
# threading.Thread(target=flow_handler.listen, daemon=True).start()

# Start the SwitchEventHandler in a separate thread
switch_handler = SwitchEventHandler(event_bus)
threading.Thread(target=switch_handler.listen, daemon=True).start()

# Start the DatabaseEventHandler in a separate thread
# database_handler = DatabaseEventHandler(event_bus)
# threading.Thread(target=database_handler.listen, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
