import socket
import json
import uuid
import time
import random
import zlib
from collections import deque
from enum import Enum, auto
from header import *

class ClientState(Enum):
    WAIT_FOR_JOIN = 1
    WAIT_FOR_READY = 2
    WAIT_FOR_STARTGAME = 3
    IN_GAME_LOOP = 4
    GAME_OVER = 5


TICK = 0.05
JOIN_RESEND = 0.25
READY_RESEND = 0.25
ACQUIRE_RESEND = 0.06
START_TIMEOUT = 2.0


class ClientHeaders:
    def __init__(self, color="red", position=(0, 0)):
      
        self.my_id = None
        self.color = color
        self.position = position
        self.score = 0
        self.start_time = None
        

    def start_timer(self):
        self.start_time = time.time()

    def time_elapsed(self):
        return time.time() - self.start_time if self.start_time else 0


class ClientFSM:
    def __init__(self, socket, client_headers, server_address):
        self.sock = socket
        self.server_addr = server_address
        self.headers = client_headers
        self.state = ClientState.WAIT_FOR_JOIN
        self.grid = [[0 for _ in range(20)] for _ in range(20)]
        self.last_snapshot_id = 0
        self.my_id = None  
        

        self.last_send_time = 0
        self.last_ack_time = 0
        self.last_acquire_time = 0
        self.last_snapshot = 0
        self.last_acquire_request={}
        self.snapshot_buffer = deque(maxlen=10)
        self.recent_transition = 0
        self.pending_acquire = None
        self.running = True
        self.sock.setblocking(False)

    def transition(self, new_state):
        print(f" Transition: {self.state.name} → {new_state.name}")
        self.state = new_state
        self.recent_transition = 1

    def send_packet(self, msg_type, payload=b"", snapshot_id=0, seq_num=0):
        packet = make_packet(msg_type, payload=payload, snapshot_id=snapshot_id, seq_num=seq_num)
        self.sock.sendto(packet, self.server_addr)

    def recv_packet(self, block=True):
     
        try:
            data, _ = self.sock.recvfrom(4096)
            packet_len = len(data) 
            header, payload = parse_packet(data)
            return header, payload,packet_len
        except (socket.timeout, BlockingIOError):
            if block:
                return None, None,0
            else:
                raise TimeoutError
        except Exception as e:
            print(f"Error while parsing packet: {e}")
            return None, None,0

    def run(self):
        print(f"client: starting...")
        print(f"client: state: {self.state.name}")
        while self.running:
            if self.state == ClientState.WAIT_FOR_JOIN:
                self.handle_join()
            elif self.state == ClientState.WAIT_FOR_READY:
                self.handle_ready()
            elif self.state == ClientState.WAIT_FOR_STARTGAME:
                self.handle_start_game()
            elif self.state == ClientState.IN_GAME_LOOP:
                self.handle_game_loop()
            elif self.state == ClientState.GAME_OVER:
                self.handle_game_over()

            time.sleep(0.001)

    def handle_join(self):
        now = time.time()

        if self.recent_transition or now - self.last_send_time >= JOIN_RESEND:
            self.recent_transition = 0
            self.send_packet(MSG_JOIN_REQ, payload=b"")
            print("Sent JOIN_REQ")
            self.last_send_time = now

        header, payload,packet_len = self.recv_packet()
        if header and header["msg_type"] == MSG_JOIN_ACK:
     
            try:
                payload_dict = json.loads(payload.decode())
                self.my_id = payload_dict.get("player_id")
                if self.my_id is None:
                    print("ERROR: Server JOIN_ACK did not contain player_id")
                    self.running = False
                    return

                self.headers.my_id = self.my_id
                print(f"JOIN_ACK received. ID: {self.my_id}")
                self.transition(ClientState.WAIT_FOR_READY)
            except Exception as e:
                print(f"Error parsing JOIN_ACK: {e}")
                self.running = False

    def handle_ready(self):
        now = time.time()

        if self.recent_transition or now - self.last_send_time >= READY_RESEND:
            self.recent_transition = 0
            self.send_packet(MSG_READY_REQ, payload=b"")
            print("→ Sent READY_REQ")
            self.last_send_time = now

        header, payload,packet_len = self.recv_packet()
        if header and header["msg_type"] == MSG_READY_ACK:
            print("READY_ACK received. Waiting for start snapshot.")
            self.transition(ClientState.WAIT_FOR_STARTGAME)

    def handle_start_game(self):
        header, payload,packet_len = self.recv_packet()
        now = time.time()

        if header and header["msg_type"] == MSG_SNAPSHOT_FULL:
            snap_id = header["snapshot_id"]
            self.last_snapshot_id = snap_id
            print(f"Received full snapshot #{snap_id}")

            payload=zlib.decompress(payload)
            self.apply_full_snapshot(json.loads(payload.decode()))
   
            self.send_packet(MSG_SNAPSHOT_ACK, snapshot_id=snap_id)
            self.transition(ClientState.IN_GAME_LOOP)

        elif now - self.last_send_time >= START_TIMEOUT or self.recent_transition == 1:
            self.recent_transition = 0
            # FIX 3: Send an empty payload.
            self.send_packet(MSG_READY_REQ, payload=b"")
            print("Waiting for full snapshot")
            self.last_send_time = now



    def handle_game_loop(self):
        #buffer to handle many messages
        buffer = deque()
        while True:
            try:
                header, payload,packet_len = self.recv_packet(block=False)
                if header:
                    buffer.append((header, payload,packet_len))
            except TimeoutError:
                break
            except Exception:
                break
        while buffer:
            header, payload,packet_len = buffer.popleft()
            now = time.time()
            msg_type = header["msg_type"]
            snapshot_id = header["snapshot_id"]

            if msg_type in (MSG_SNAPSHOT_FULL, MSG_SNAPSHOT_DELTA):
                if snapshot_id <= self.last_snapshot_id:
                    print(f"Ignored outdated snapshot #{snapshot_id} (last={self.last_snapshot_id})")
                    continue

            
            if msg_type == MSG_SNAPSHOT_FULL:
                payload=zlib.decompress(payload)
                state = json.loads(payload.decode())
                self.apply_full_snapshot(state)
                print(f"Applied full snapshot #{snapshot_id}")

                # Logging for the metrics collection script
                print(f"SNAPSHOT recv_time={time.time()} server_ts={header['timestamp']} snapshot_id={snapshot_id} seq={header['seq_num']} bytes={packet_len}")
                self.last_snapshot_id = snapshot_id
                self.last_ack_time = now
                #self.pending_acquire = None
                self.send_packet(MSG_SNAPSHOT_ACK, snapshot_id=snapshot_id)

          
            elif msg_type == MSG_SNAPSHOT_DELTA:
                delta = json.loads(payload.decode())
                self.apply_delta_snapshot(delta)
                print(f"Applied delta snapshot #{snapshot_id}")

                print(f"SNAPSHOT recv_time={time.time()} server_ts={header['timestamp']} snapshot_id={snapshot_id} seq={header['seq_num']} bytes={packet_len}" )
                self.last_snapshot_id = snapshot_id
                self.last_ack_time = now
                #self.pending_acquire = None
                self.send_packet(MSG_SNAPSHOT_ACK, snapshot_id=snapshot_id)
            
            elif msg_type == MSG_ACQUIRE_ACK:
                ack=json.loads(payload.decode())
                
                if self.last_acquire_request and ack["x"]==self.last_acquire_request["x"] and ack["y"]==self.last_acquire_request["y"]:
                    print(f"Received ACK for ({ack['x']},{ack['y']}) recv_time={time.time()}")
                    self.last_acquire_request = {}
                    self.pending_acquire = None 


            elif msg_type == MSG_LEADERBOARD:
                print("Game Over message received (Leaderboard)")
                try:
                    lb = json.loads(payload.decode())
                    results = lb.get("results", [])
                    print("Leaderboard:")
                    for entry in results:
                        rank = entry.get("rank")
                        pid = entry.get("player_id")
                        score = entry.get("score")
                        print(f"  {rank}. player {pid} — score {score}")
                except Exception as e:
                    print(f"Failed to parse leaderboard payload: {e}")

                self.transition(ClientState.GAME_OVER)
                return

            else:
                print(f"Unrecognized message type {msg_type}")
                continue


        now = time.time()
        
        if not self.pending_acquire:
            if random.random() < (TICK / random.uniform(3, 8)):
                x = random.randint(0, 19)
                y = random.randint(0, 19)
                if self.grid[y][x] ==0:
                    payload_dictionary = {"x": x, "y": y}
                    payload = json.dumps(payload_dictionary).encode()

                    self.send_packet(MSG_ACQUIRE_EVENT, payload=payload)
                    self.pending_acquire = payload
                    self.last_acquire_time = now
                    self.last_acquire_request={"x":x,"y":y,"time":time.time()}
                    print(f"Sent ACQUIRE event ({x},{y}) AT {self.last_acquire_time}")
                    print(f"POS_CLIENT x={x} y={y} ts={time.time()}")
        
        elif self.pending_acquire and now-self.last_acquire_time> ACQUIRE_RESEND:
            payload_dictionary = {"x": self.last_acquire_request["x"], "y": self.last_acquire_request["y"]}
            payload = json.dumps(payload_dictionary).encode()
            self.last_acquire_time = now
            self.send_packet(MSG_ACQUIRE_EVENT, payload=payload)
            print(f"Sent ACQUIRE event ({self.last_acquire_request['x']},{self.last_acquire_request['y']})")
                

    def handle_game_over(self):
        print("Game Over! Finalizing session...")
        
        self.send_packet(MSG_END_GAME, payload=b"ACK")
        print("Sent game over acknowledgment to server.")
        time.sleep(1)
        self.sock.close()
        self.running = False
        print("Client session ended.")

    def apply_full_snapshot(self, state):
        self.grid = state["grid"]
        self.last_snapshot_id = state["snapshot_id"]
        print(f"[FULL] Applied full snapshot #{self.last_snapshot_id}")
        # Placeholder for position error (Required for 2% Loss Test)
        #print(f"POSITION_ERR error=0.0 recv_time={time.time()}")

    def apply_delta_snapshot(self, delta):
        if not hasattr(self, "grid"):
            print("No base grid, ignoring delta snapshot.")
            return
        changes_list = delta.get("changes")
        if changes_list is None:
            print("Delta snapshot missing 'changes' key.")
            return

        for (y, x, new_val) in changes_list:
            self.grid[y][x] = new_val

        self.last_snapshot_id = delta["snapshot_id"]
        print(f"[DELTA] Applied {len(changes_list)} changes (snapshot #{self.last_snapshot_id})")



def main():
    server_address = ("127.0.0.1", 8888)
    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    clientSocket.settimeout(TICK)

    headers = ClientHeaders()
    fsm = ClientFSM(clientSocket, headers, server_address)

    print(f"Client started.")
    print(f"Initial state: {fsm.state.name}")

    fsm.run()


if __name__ == "__main__":
    main()
