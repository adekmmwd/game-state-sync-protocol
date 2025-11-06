import select
from socket import *
import dataclasses
import enum
import time
import json
import numpy as np
from header import *


@dataclasses.dataclass
class Player:
    id: int
    address: tuple
    ready: bool = False
    last_update_time: float = 0
    last_snapshot_id: int = 0
    state_data: dict = dataclasses.field(default_factory=dict)
    score: int = 0


class ServerState(enum.Enum):
    WAITING_FOR_JOIN = 1
    WAITING_FOR_INIT = 2
    GAME_LOOP = 3
    GAME_OVER = 4


class GameServer:
    def __init__(self):
        # Server fields
        self.server_socket = socket(AF_INET, SOCK_DGRAM)
        self.server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.server_socket.bind(('', 8888))
        self.server_socket.setblocking(False)  # <-- CRITICAL: Set to non-blocking
        self.state = ServerState.WAITING_FOR_JOIN
        self.seq_num = 0

        # Game fields
        self.players = {}
        self.game_running = False
        self.ready_count = 0

        # Time fields
        self.interval = 0.05  # 20 ticks per second
        self.join_time_gap_allowed = 10
        self.join_start_time = time.time()
        self.game_start_time = 0
        self.last_broadcast_time = 0

        # Snapshot fields
        self.last_snapshot_deltas = []
        self.current_snapshot = {}
        self.previous_snapshot = {}
        self.snapshot_id = 0
        
        print("Server started. Waiting for players...")

    # --- Main Loop ---

    def run(self):
        """Main server loop."""
        while True:
            self.run_one_frame()
            # Sleep to prevent 100% CPU usage
            time.sleep(0.001)

    def run_one_frame(self):
        """Process all network events and update game state for one frame."""
        self.process_network_events()
        
        # --- State-specific time-based logic ---
        if self.state == ServerState.WAITING_FOR_JOIN:
            self.update_waiting_for_join()
        
        elif self.state == ServerState.WAITING_FOR_INIT:
            # This is a transitional state
            self.run_state_waiting_for_init()
        
        elif self.state == ServerState.GAME_LOOP:
            self.update_game_loop()
        
        elif self.state == ServerState.GAME_OVER:
            # This is also a transitional state
            self.run_state_game_over()

    # --- Network Handling ---

    def process_network_events(self):
        """Read all available packets from the socket using select."""
        inputs = [self.server_socket]
        
        # Poll for 1ms, then continue. This does not block.
        readable, _, _ = select.select(inputs, [], [], 0.001)

        for sock in readable:
            while True:
                try:
                    data, addr = sock.recvfrom(2048)
                    self.handle_packet(data, addr)
                except BlockingIOError:
                    # No more data to read from the buffer
                    break
                except Exception as e:
                    print(f"Socket read error: {e}")
                    break

    def handle_packet(self, data, addr):
        """Route an incoming packet to the correct handler based on state."""
        try:
            header, payload = parse_packet(data)
            msg_type = header["msg_type"]

            # Route based on current server state
            if self.state == ServerState.WAITING_FOR_JOIN:
                if msg_type == MSG_JOIN_REQ:
                    self.handle_join_req(addr)
                elif msg_type == MSG_READY_REQ:
                    self.handle_ready_req(addr)
            
            elif self.state == ServerState.GAME_LOOP:
                if msg_type == MSG_ACQUIRE_EVENT:
                    self.handle_acquire_event(addr, payload)
                elif msg_type == MSG_SNAPSHOT_ACK:
                    self.handle_snapshot_ack(addr, header)
            
            # Other states (INIT, GAME_OVER) don't process packets

        except Exception as e:
            print(f"Error handling packet: {e}")

    # --- Packet Handlers (Moved from async functions) ---

    def handle_join_req(self, addr):
        if addr in self.players:
            print(f"Ignoring duplicate join from {addr}")
            existing_player = self.players[addr]
            ack_payload = json.dumps({"player_id": existing_player.id}).encode()
            self.seq_num += 1
            ack_packet = make_packet(MSG_JOIN_ACK, payload=ack_payload, seq_num=self.seq_num)
            self.server_socket.sendto(ack_packet, addr)
            return

        new_id = len(self.players) + 1
        player = Player(id=new_id, address=addr)
        self.players[addr] = player
        print(f"Player {new_id} joined from {addr}")

        # Send join acknowledgment
        ack_payload = json.dumps({"player_id": new_id}).encode()
        self.seq_num += 1
        ack_packet = make_packet(MSG_JOIN_ACK, payload=ack_payload, seq_num=self.seq_num)
        self.server_socket.sendto(ack_packet, addr)

    def handle_ready_req(self, addr):
        if addr in self.players:
            if not self.players[addr].ready:
                self.players[addr].ready = True
                self.ready_count += 1
                print(f"Player {self.players[addr].id} is ready ({self.ready_count}/{len(self.players)})")
            
            self.seq_num += 1
            ack_packet = make_packet(MSG_READY_ACK, seq_num=self.seq_num)
            self.server_socket.sendto(ack_packet, addr)

    def handle_acquire_event(self, addr, payload):
        payload_dict = json.loads(payload.decode())
        cell_x, cell_y = payload_dict["x"], payload_dict["y"]
        player = self.players.get(addr)

        if player:
            if self.current_snapshot["grid"][cell_y][cell_x] == 0:
                self.current_snapshot["grid"][cell_y][cell_x] = player.id
                player.score += 1
                print(f"Player {player.id} acquired cell ({cell_x}, {cell_y})")
        #self.current_snapshot["timestamp"] = time.time()

    def handle_snapshot_ack(self, addr, header):
        snapshot_id = header["snapshot_id"]

        player = self.players.get(addr)
        if player:
            # Only update if this is a newer (or same) ack
            if snapshot_id >= player.last_snapshot_id:
                player.last_snapshot_id = snapshot_id
                player.last_update_time = time.time()
                # print(f"ACK from Player {player.id} for snapshot {snapshot_id}")

    # --- State Logic (Time-based and Transitional) ---

    def update_waiting_for_join(self):
        """Check time/ready conditions to start the game."""
        time_elapsed = time.time() - self.join_start_time
        
        # Condition 1: Time is up and we have at least 2 players
        time_condition = (time_elapsed >= self.join_time_gap_allowed and len(self.players) > 1)
        
        # Condition 2: Half the players are ready (and we have at least 1)
        ready_condition = (len(self.players) > 0 and self.ready_count >= len(self.players) / 2)

        if time_condition or ready_condition:
            print("Conditions met, moving to INIT state.")
            self.state = ServerState.WAITING_FOR_INIT

    def run_state_waiting_for_init(self):
        """Send the initial snapshot to all players."""
        print("Sending initial snapshot...")

        self.current_snapshot = {
            "grid": ([[0 for _ in range(20)] for _ in range(20)]),
            "timestamp": time.time(),
            "snapshot_id": self.snapshot_id
        }

        snapshot_payload = json.dumps(self.current_snapshot).encode()
        self.seq_num += 1
        snapshot_packet = make_packet(MSG_SNAPSHOT_FULL, payload=snapshot_payload, snapshot_id=self.snapshot_id, seq_num=self.seq_num)

        for player in self.players.values():
            self.server_socket.sendto(snapshot_packet, player.address)
            print(f"Sent initial snapshot to Player {player.id}")

        self.snapshot_id += 1
        self.game_running = True
        self.game_start_time = time.time()
        self.last_broadcast_time = time.time()  # <-- Start the broadcast timer
        
        # Transition to the next state
        self.state = ServerState.GAME_LOOP
        print("Entering GAME_LOOP...")

    def update_game_loop(self):
        """Check broadcast timer and game-over conditions."""
        current_time = time.time()
        
        # --- 1. Broadcast Snapshots on Interval ---
        if (current_time - self.last_broadcast_time) >= self.interval:
            self.broadcast_snapshots()
            self.last_broadcast_time = current_time  # Reset timer

        # --- 2. Check for Game Over Condition ---
        # (This check can be moved into broadcast_snapshots if preferred)
        grid_flat = np.array(self.current_snapshot["grid"]).flatten()
        if np.all(grid_flat != 0):
            print("All cells claimed — ending game.")
            self.game_running = False
            self.state = ServerState.GAME_OVER

    def broadcast_snapshots(self):
        """Send deltas or full snapshots to all players."""
        self.seq_num += 1
        server_snapshot_id = self.snapshot_id # Use a consistent ID for this batch
        
        # Compute delta from last snapshot
        if self.previous_snapshot and "grid" in self.previous_snapshot:
            old_grid = self.previous_snapshot["grid"]
        else:
            old_grid = [[0 for _ in range(20)] for _ in range(20)]

        new_grid = self.current_snapshot["grid"]

        old_arr = np.array(old_grid)
        new_arr = np.array(new_grid)
        diff_indices = np.argwhere(old_arr != new_arr)
        delta_changes = [(int(y), int(x), int(new_arr[y, x])) for y, x in diff_indices]

        # Only store delta if there *were* changes
        if delta_changes:
            delta_entry = {
                "snapshot_id": server_snapshot_id,
                "delta": delta_changes,
            }
            self.last_snapshot_deltas.append(delta_entry)
            # Keep only the last ~3 deltas
            if len(self.last_snapshot_deltas) > 3:
                self.last_snapshot_deltas.pop(0)

        # Update snapshot timestamp and ID
        #self.current_snapshot["timestamp"] = time.time()
        self.current_snapshot["snapshot_id"] = server_snapshot_id

        # Prepare full snapshot packet
        full_payload = json.dumps(self.current_snapshot).encode()
        full_packet = make_packet(MSG_SNAPSHOT_FULL, payload=full_payload,
                                  snapshot_id=server_snapshot_id, seq_num=self.seq_num)

        for player in self.players.values():
            diff = server_snapshot_id - player.last_snapshot_id

            if diff <= len(self.last_snapshot_deltas) and diff > 0 and self.last_snapshot_deltas:
                # Combine missed deltas
                missed = self.last_snapshot_deltas[-diff:]
                combined_changes = [cell for delta in missed for cell in delta["delta"]]

                delta_payload = json.dumps({
                    "snapshot_id": server_snapshot_id,
                    "changes": combined_changes
                }).encode()

                delta_packet = make_packet(MSG_SNAPSHOT_DELTA, payload=delta_payload,
                                           snapshot_id=server_snapshot_id, seq_num=self.seq_num)

                self.server_socket.sendto(delta_packet, player.address)
                # print(f"Sent DELTA snapshot to Player {player.id}")
            else:
                # Too far behind or no baseline → send full
                self.server_socket.sendto(full_packet, player.address)
                # print(f"Sent FULL snapshot to Player {player.id} (resync)")

            print(f"SNAPSHOT_SEND server_ts={time.time()} snapshot_id={server_snapshot_id} seq={self.seq_num}")
        
        # Store the just-sent snapshot as the previous one
        self.previous_snapshot = {
            "grid": [row.copy() for row in self.current_snapshot["grid"]],
            #"timestamp": self.current_snapshot["timestamp"],
            "snapshot_id": server_snapshot_id
        }
        
        self.snapshot_id += 1 # Increment for the *next* frame


    def run_state_game_over(self):
        """Calculate, send leaderboard, and reset the server."""
        print("\n--- GAME OVER ---")

        end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(f"Game ended at: {end_time}")

        duration = round(time.time() - self.game_start_time, 2)
        print(f"Total game duration: {duration} seconds")

        leaderboard = sorted(self.players.values(), key=lambda p: p.score, reverse=True)

        print("\n=== FINAL LEADERBOARD ===")
        for rank, player in enumerate(leaderboard, start=1):
            print(f"{rank}. Player {player.id} — Score: {player.score}")
        print("==========================\n")

        # --- Broadcast leaderboard ---
        leaderboard_data = {
            "type": "leaderboard",
            "results": [
                {"rank": rank, "player_id": player.id, "score": player.score}
                for rank, player in enumerate(leaderboard, start=1)
            ]
        }

        leaderboard_payload = json.dumps(leaderboard_data).encode()
        leaderboard_packet = make_packet(MSG_LEADERBOARD, payload=leaderboard_payload)

        for player in leaderboard:
            self.server_socket.sendto(leaderboard_packet, player.address)
            print(f"Leaderboard sent to Player {player.id}")

        # --- Reset server state for the next round ---
        self.reset_server_state()

    def reset_server_state(self):
        """Clear all game variables to prepare for a new session."""
        print("Game session ended. Server ready for next round.")
        
        self.players.clear()
        self.ready_count = 0
        self.seq_num = 0
        self.snapshot_id = 0
        self.last_snapshot_deltas.clear()
        self.current_snapshot = {}
        self.previous_snapshot = {}
        self.game_running = False
        
        # Reset state back to WAITING_FOR_JOIN
        self.state = ServerState.WAITING_FOR_JOIN
        self.join_start_time = time.time()


# --- Entry Point ---

if __name__ == "__main__":
    server = GameServer()
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nServer shutting down.")
        server.server_socket.close()