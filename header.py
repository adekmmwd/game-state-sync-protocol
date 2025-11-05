import struct
import time


# Protocol information
PROTOCOL_ID = b'VAP1'       
VERSION = 1                 
HEADER_FORMAT = "!4s B B I I d H"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

#join
MSG_JOIN_REQ   = 1    
MSG_JOIN_ACK   = 2  

#ready
MSG_READY_REQ  = 3   
MSG_READY_ACK  = 4   

#game
MSG_START_GAME = 5  #useless
MSG_SNAPSHOT_FULL   = 6  
MSG_SNAPSHOT_DELTA   = 7  
MSG_SNAPSHOT_ACK = 8  

#events
MSG_ACQUIRE_EVENT =  9 

#termination
MSG_END_GAME   = 10
MSG_LEADERBOARD = 11
MSG_TERMINATE  = 12



# HEADER PACKING / UNPACKING


def pack_header(msg_type, snapshot_id=0, seq_num=0, payload_len=0):

    timestamp = time.monotonic()  # Monotonic clock for reliable time deltas
    return struct.pack(
        HEADER_FORMAT,
        PROTOCOL_ID,
        VERSION,
        msg_type,
        snapshot_id,
        seq_num,
        timestamp,
        payload_len
    )


def unpack_header(data):

    if len(data) < HEADER_SIZE:
        raise ValueError("Data too short to contain valid header")

    fields = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])

    return {
        "protocol_id": fields[0],
        "version": fields[1],
        "msg_type": fields[2],
        "snapshot_id": fields[3],
        "seq_num": fields[4],
        "timestamp": fields[5],
        "payload_len": fields[6],
    }




def make_packet(msg_type, payload=b"", snapshot_id=0, seq_num=0):
    
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("Payload must be bytes")

    header = pack_header(
        msg_type=msg_type,
        snapshot_id=snapshot_id,
        seq_num=seq_num,
        payload_len=len(payload)
    )
    return header + payload


def parse_packet(data):
   
    header = unpack_header(data)
    payload_start = HEADER_SIZE
    payload_end = HEADER_SIZE + header["payload_len"]
    payload = data[payload_start:payload_end]
    return header, payload


