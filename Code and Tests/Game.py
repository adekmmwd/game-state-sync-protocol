
import socket
import threading
import time
import json
import argparse
import pygame
import sys

try:   
    from client import ClientFSM, ClientState, ClientHeaders, MSG_ACQUIRE_EVENT
    client_available = True
except ImportError:
    client_available = False


class GridClashGUI:
    def __init__(self, server_host):
        self.server_host = server_host
        self.port = 8888
        self.grid_size = 20
        
        # Game state
        self.grid = [[0 for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        self.player_id = None
        self.score = 0
        self.running = True
        self.state = ClientState.WAIT_FOR_JOIN
        
        # Leaderboard from server
        self.leaderboard = None
        

        if client_available:
            self.fsm_thread = threading.Thread(target=self.run_fsm_client, daemon=True)
            self.fsm_thread.start()
        else:
            print("No client available")
        
    def run_fsm_client(self):
        
        try:
            # Create socket and client 
            server_address = (self.server_host, self.port)
            clientSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            clientSocket.settimeout(0.05)
            
            headers = ClientHeaders()
            self.fsm = ClientFSM(clientSocket, headers, server_address)
            self.fsm.run()
            
        except Exception as e:
            print(f"Error in client: {e}")
            import traceback
            traceback.print_exc()
    
    def get_game_state(self):
       
        if not client_available or not hasattr(self, 'fsm'):
            return self.grid, None, 0, ClientState.WAIT_FOR_JOIN, None
        
        try:
            # Get grid from FSM
            grid = self.fsm.grid
            
            # Get player ID
            player_id = self.fsm.my_id
            
            # Calculate score
            score = 0
            if player_id:
                for row in grid:
                    for cell in row:
                        if cell == player_id:
                            score += 1
            
    
            state = self.fsm.state
            leaderboard_data = None
            if hasattr(self.fsm, 'leaderboard'):
                leaderboard_data = self.fsm.leaderboard
            elif hasattr(self.fsm, '_leaderboard'):
                leaderboard_data = self.fsm._leaderboard
            elif hasattr(self.fsm, 'scores'):
                leaderboard_data = self.fsm.scores

            if state == ClientState.GAME_OVER and leaderboard_data is None:
                player_scores = {}
                for y in range(len(grid)):
                    for x in range(len(grid[y])):
                        player = grid[y][x]
                        if player > 0:
                            player_scores[str(player)] = player_scores.get(str(player), 0) + 1
                if player_scores:
                    leaderboard_data = player_scores
            
            return grid, player_id, score, state, leaderboard_data
            
        except Exception as e:
            print(f"Error getting game state: {e}")
            return self.grid, self.player_id, self.score, ClientState.WAIT_FOR_JOIN, self.leaderboard
    
    def send_acquire(self, x, y):
        if not client_available or not hasattr(self, 'fsm'):
            print(f"Cannot acquire cell: client not available")
            return False
        
        try:
            if self.fsm.state != ClientState.IN_GAME_LOOP:
                return False
            
            payload_dictionary = {"x": x, "y": y}
            payload = json.dumps(payload_dictionary).encode()
            
            self.fsm.send_packet(MSG_ACQUIRE_EVENT, payload=payload)
            return True
            
        except Exception as e:
            print(f"Error sending acquire: {e}")
            return False
    
    def send_ready(self):
        
        if not client_available or not hasattr(self, 'fsm'):
            print("Cannot send ready: client not available")
            return False
        
        try:
            if self.fsm.state == ClientState.WAIT_FOR_READY:
                self.fsm.transition(ClientState.WAIT_FOR_STARTGAME)
                return True
            return False
        except:
            return False


def run_pygame_gui(gui_client):
    pygame.init()
    

    WINDOW_WIDTH = 1300
    WINDOW_HEIGHT = 800
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Grid Clash")
    
    COLOR_MAP = {
        0: (60, 60, 60),
        1: (255, 80, 80),
        2: (80, 220, 80),
        3: (80, 150, 255),
        4: (255, 220, 80),
        5: (220, 80, 220),
        6: (80, 220, 220),
        7: (255, 180, 80),
        8: (180, 180, 255),
    }
    
    def get_color(player_id):
        return COLOR_MAP.get(player_id, (180, 180, 180))

    font = pygame.font.SysFont(None, 32)
    small_font = pygame.font.SysFont(None, 24)
    large_font = pygame.font.SysFont(None, 36)
    title_font = pygame.font.SysFont(None, 48)
    
    clock = pygame.time.Clock()
    is_fullscreen = False
    
    while gui_client.running:
        # Get current game state from FSM
        grid, player_id, score, state, leaderboard_data = gui_client.get_game_state()
        
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                gui_client.running = False
                if hasattr(gui_client, 'fsm'):
                    gui_client.fsm.running = False
                
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    gui_client.running = False
                    if hasattr(gui_client, 'fsm'):
                        gui_client.fsm.running = False
                elif event.key == pygame.K_F11:
                    # Toggle fullscreen
                    is_fullscreen = not is_fullscreen
                    if is_fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
                        
            elif event.type == pygame.VIDEORESIZE:
                if not is_fullscreen:
                    WINDOW_WIDTH, WINDOW_HEIGHT = event.size
                    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
                    
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    mx, my = event.pos
                    
                    # Calculate grid position
                    current_width, current_height = screen.get_size()
                    GRID_AREA = min(current_width - 100, current_height - 200)
                    CELL_SIZE = max(20, GRID_AREA // 20)
                    GRID_X = (current_width - CELL_SIZE * 20) // 2
                    GRID_Y = (current_height - CELL_SIZE * 20) // 2
                    
                    grid_x = (mx - GRID_X) // CELL_SIZE
                    grid_y = (my - GRID_Y) // CELL_SIZE
                    
                    if 0 <= grid_x < 20 and 0 <= grid_y < 20:
                        if state == ClientState.WAIT_FOR_READY:
                            gui_client.send_ready()
                        elif state == ClientState.IN_GAME_LOOP:
                            gui_client.send_acquire(grid_x, grid_y)
        
        # Clear screen
        screen.fill((25, 25, 25))
        
        # Get window size
        current_width, current_height = screen.get_size()
        
        # Calculate unclaimed cells
        unclaimed_count = sum(1 for row in grid for cell in row if cell == 0)
        
        # Draw status
        status_text = state.name.replace('_', ' ') if state else "Unknown"
        if player_id and state == ClientState.IN_GAME_LOOP:
            status_text = f"Player {player_id} - Score: {score} - Unclaimed: {unclaimed_count}"
        
        status_surface = large_font.render(status_text, True, (255, 255, 255))
        screen.blit(status_surface, (current_width // 2 - status_surface.get_width() // 2, 20))

        GRID_AREA = min(current_width - 100, current_height - 200)
        CELL_SIZE = max(20, GRID_AREA // 20)
        GRID_X = (current_width - CELL_SIZE * 20) // 2
        GRID_Y = (current_height - CELL_SIZE * 20) // 2 + 50
        
        pygame.draw.rect(screen, (35, 35, 35), 
                        (GRID_X, GRID_Y, CELL_SIZE * 20, CELL_SIZE * 20))
        
        for y in range(20):
            for x in range(20):
                cell_value = grid[y][x] if y < len(grid) and x < len(grid[y]) else 0
                cell_color = get_color(cell_value)
                
                rect = pygame.Rect(
                    GRID_X + x * CELL_SIZE,
                    GRID_Y + y * CELL_SIZE,
                    CELL_SIZE,
                    CELL_SIZE
                )
                
                pygame.draw.rect(screen, cell_color, rect)
                
                # Border
                border_color = (90, 90, 90) if cell_value == 0 else (40, 40, 40)
                pygame.draw.rect(screen, border_color, rect, 1)
                
                # Player number
                if cell_value > 0 and CELL_SIZE > 15:
                    cell_text = small_font.render(str(cell_value), True, (255, 255, 255))
                    text_rect = cell_text.get_rect(center=rect.center)
                    screen.blit(cell_text, text_rect)

        panel_width = min(300, current_width // 3)
        panel_x = current_width - panel_width - 20
        panel_y = 80
        panel_height = 220
        
        pygame.draw.rect(screen, (40, 40, 40), (panel_x, panel_y, panel_width, panel_height))
        pygame.draw.rect(screen, (80, 80, 80), (panel_x, panel_y, panel_width, panel_height), 3)
        
        info_lines = [
            f"Player ID: {player_id if player_id else 'None'}",
            f"Your Score: {score}",
            f"Cells Left: {unclaimed_count}/400",
            "",
            "Controls:",
            "• Click: Ready/Claim",
            "• F11: Fullscreen",
            "• ESC: Exit"
        ]
        
        for i, line in enumerate(info_lines):
            color = (220, 220, 220)
            if "Your Score:" in line and player_id:
                color = get_color(player_id)
            elif "Controls:" in line:
                color = (220, 220, 100)
                
            text = small_font.render(line, True, color)
            screen.blit(text, (panel_x + 10, panel_y + 10 + i * 22))
        
       
        if state == ClientState.GAME_OVER:
        
            overlay = pygame.Surface((current_width, current_height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            screen.blit(overlay, (0, 0))
            lb_width = 600
            lb_height = 500
            lb_x = (current_width - lb_width) // 2
            lb_y = (current_height - lb_height) // 2
            
            pygame.draw.rect(screen, (30, 30, 40), (lb_x, lb_y, lb_width, lb_height))
            pygame.draw.rect(screen, (100, 100, 150), (lb_x, lb_y, lb_width, lb_height), 4)
            
            title = title_font.render("GAME OVER", True, (255, 100, 100))
            screen.blit(title, (current_width // 2 - title.get_width() // 2, lb_y + 30))
            
            if leaderboard_data:
                # Display leaderboard header
                subtitle = large_font.render("FINAL LEADERBOARD", True, (255, 200, 100))
                screen.blit(subtitle, (current_width // 2 - subtitle.get_width() // 2, lb_y + 90))
                
                # Draw column headers
                header_y = lb_y + 140
                headers = ["Rank", "Player", "Score", "Cells"]
                column_widths = [100, 200, 150, 150]
                
                x_pos = lb_x + 50
                for i, header in enumerate(headers):
                    header_text = font.render(header, True, (200, 220, 255))
                    screen.blit(header_text, (x_pos, header_y))
                    x_pos += column_widths[i]
                
                pygame.draw.line(screen, (100, 100, 150), 
                               (lb_x + 40, header_y + 30), 
                               (lb_x + lb_width - 40, header_y + 30), 2)
                
                entry_y = header_y + 50
                max_display = 8
                sorted_leaderboard = sorted(leaderboard_data.items(), 
                                          key=lambda x: x[1], 
                                          reverse=True)[:max_display]
                
                for rank, (player_id_entry, player_score) in enumerate(sorted_leaderboard, 1):
                    # Calculate player's cells from grid
                    player_cells = 0
                    if player_id_entry.isdigit():
                        player_num = int(player_id_entry)
                        for row in grid:
                            for cell in row:
                                if cell == player_num:
                                    player_cells += 1
                    else:
                        player_cells = player_score
                    
     
                    text_color = (255, 255, 255)
                    if player_id and str(player_id) == str(player_id_entry):
                        text_color = (255, 255, 100)
        
                    rank_text = font.render(f"{rank}.", True, text_color)
                    screen.blit(rank_text, (lb_x + 60, entry_y))
                    if player_id_entry.isdigit():
                        player_color = get_color(int(player_id_entry))
                    else:
                        player_color = (180, 180, 180)
                    
                    pygame.draw.circle(screen, player_color, (lb_x + 180, entry_y + 12), 8)
                    player_text = font.render(f"Player {player_id_entry}", True, text_color)
                    screen.blit(player_text, (lb_x + 200, entry_y))
                    
     
                    score_text = font.render(str(player_score), True, text_color)
                    screen.blit(score_text, (lb_x + 330, entry_y))
                    
              
                    cells_text = font.render(str(player_cells), True, text_color)
                    screen.blit(cells_text, (lb_x + 450, entry_y))
                    
                    entry_y += 40
                
                if player_id and all(str(player_id) != str(pid) for pid, _ in sorted_leaderboard[:max_display]):
                    all_sorted = sorted(leaderboard_data.items(), 
                                      key=lambda x: x[1], 
                                      reverse=True)
                    player_rank = next((i+1 for i, (pid, _) in enumerate(all_sorted) 
                                      if str(pid) == str(player_id)), None)
                    
                    if player_rank:
                        separator_y = entry_y + 10
                        pygame.draw.line(screen, (150, 150, 150), 
                                       (lb_x + 40, separator_y), 
                                       (lb_x + lb_width - 40, separator_y), 1)
                        
                        your_rank_y = separator_y + 20
                        your_rank_text = font.render(f"Your rank: #{player_rank}", True, (255, 200, 100))
                        screen.blit(your_rank_text, (current_width // 2 - your_rank_text.get_width() // 2, your_rank_y))
                        
                        your_score = leaderboard_data.get(str(player_id), 0)
                        your_cells = sum(1 for row in grid for cell in row if cell == player_id)
                        your_stats = font.render(f"Score: {your_score}, Cells: {your_cells}", True, (200, 200, 200))
                        screen.blit(your_stats, (current_width // 2 - your_stats.get_width() // 2, your_rank_y + 30))
            else:
                message = large_font.render("Leaderboard Data Unavailable", True, (255, 150, 150))
                screen.blit(message, (current_width // 2 - message.get_width() // 2, lb_y + 180))
            
          
            instruction = font.render("Press ESC to exit", True, (200, 200, 200))
            screen.blit(instruction, (current_width // 2 - instruction.get_width() // 2, lb_y + lb_height - 60))
        
        
        pygame.display.flip()
        clock.tick(60)
    

    pygame.quit()

def run_your_server():
    try:
        from server import GameServer
        server = GameServer()
        server.run()
    except ImportError:
        print("Error: Could not import server.py")
    except KeyboardInterrupt:
        print("\nServer stopped")


def main():
    parser = argparse.ArgumentParser(description="Grid Clash Game")
    parser.add_argument("--mode", choices=["server", "client"], required=True,
                       help="Run as server or GUI client")
    parser.add_argument("--host", default="127.0.0.1",
                       help="Server IP (for client mode)")
    
    args = parser.parse_args()
    
    if args.mode == "server":
        run_your_server()
    elif args.mode == "client":
        gui_client = GridClashGUI(args.host)
        try:
            run_pygame_gui(gui_client)
        except KeyboardInterrupt:
            print("\nClient stopped")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()