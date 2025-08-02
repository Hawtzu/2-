import pygame
import sys
import numpy as np
import random

# --- 定数定義 ---
PANEL_WIDTH = 280
BOARD_WIDTH = 720
SCREEN_WIDTH = BOARD_WIDTH + PANEL_WIDTH * 2
SCREEN_HEIGHT = 800
BOARD_SIZE = 9
CELL_SIZE = 80
BOARD_OFFSET_X = PANEL_WIDTH
BOARD_OFFSET_Y = 40
# 色
GRID_COLOR = (100, 100, 100); BLACK = (0, 0, 0); WHITE = (255, 255, 255)
P1_COLOR = (0, 100, 255); P2_COLOR = (255, 50, 50)
P1_PANEL_BG = (20, 20, 60); P2_PANEL_BG = (60, 20, 20)
STONE_COLOR = (128, 128, 128); RECOVERY_TILE_COLOR = (64, 224, 208)
BOMB_TILE_COLOR = (255, 128, 0); DRILL_COLOR = (220, 20, 60)
ICE_TILE_COLOR = (173, 216, 230)
# ハイライト色
MOVE_HIGHLIGHT_COLOR = (255, 255, 0, 128); FALL_HIGHLIGHT_COLOR = (255, 0, 0, 128)
PLACE_HIGHLIGHT_COLOR = (0, 255, 255, 128); FIGURE_BONUS_HIGHLIGHT_COLOR = (255, 215, 0, 200)
DRILL_TARGET_HIGHLIGHT_COLOR = (255, 0, 255, 180)

# --- マーカー定義 ---
STONE_MARKER = "S"; RECOVERY_MARKER = "R"; BOMB_MARKER = "B"; ICE_MARKER = "I"; EMPTY_MARKER = " "

# --- ヘルパー関数 ---
def _manhattan_distance(pos1, pos2):
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

# --- ゲーム状態を管理するクラス ---
class GameState:
    def __init__(self, size=BOARD_SIZE):
        self.board = np.full((size, size), EMPTY_MARKER, dtype=object)
        self.player_pos = {1: (size // 2, 0), 2: (size // 2, size - 1)}
        self.player_points = {1: 0, 2: 0}
        self.skill_costs = {'recovery': 100, 'bomb': 50, 'drill': 200, 'ice': 100}
        self.special_skill = {1: None, 2: None}
        self.selection_confirmed = {1: False, 2: False}
        self.current_phase = "skill_selection"
        self.current_turn_player = 1
        self.dice_roll = 0
        self.placement_type = 'stone'
        self.movable_tiles, self.placeable_tiles, self.fall_trigger_tiles, self.drill_target_tiles = [], [], [], []
        self.winner, self.win_reason = None, ""
        self.figure_bonus_tiles, self.figure_bonus_timer = [], 0

    def _setup_initial_board(self):
        p1_pos, p2_pos = self.player_pos[1], self.player_pos[2]
        p1_fountain_zone = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE // 2 - 1)]
        p1_valid_spots = [pos for pos in p1_fountain_zone if _manhattan_distance(p1_pos, pos) > 3]
        p1_fountain_pos = random.choice(p1_valid_spots); self.board[p1_fountain_pos] = RECOVERY_MARKER
        p2_fountain_zone = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE // 2 + 2, BOARD_SIZE)]
        p2_valid_spots = [pos for pos in p2_fountain_zone if _manhattan_distance(p2_pos, pos) > 3]
        p2_fountain_pos = random.choice(p2_valid_spots); self.board[p2_fountain_pos] = RECOVERY_MARKER
        dist1, dist2 = _manhattan_distance(p1_pos, p1_fountain_pos), _manhattan_distance(p2_pos, p2_fountain_pos)
        self.current_turn_player = 1 if dist1 > dist2 else 2 if dist2 > dist1 else random.choice([1, 2])
        banned = {p1_fountain_pos, p2_fountain_pos, p1_pos, p2_pos}
        for r_off in [-1, 0, 1]:
            for c_off in [-1, 0, 1]:
                banned.add((p1_pos[0] + r_off, p1_pos[1] + c_off)); banned.add((p2_pos[0] + r_off, p2_pos[1] + c_off))
        possible_spots = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if (r, c) not in banned]
        for pos in random.sample(possible_spots, 3): self.board[pos] = STONE_MARKER

    def select_starting_skill(self, player_num, skill_type):
        if not self.selection_confirmed[player_num]:
            self.special_skill[player_num] = skill_type
            self.selection_confirmed[player_num] = True
        if all(self.selection_confirmed.values()):
            self._setup_initial_board()
            self.current_phase = "roll"

    def find_movable_tiles(self):
        self.movable_tiles, self.fall_trigger_tiles = [], []
        player_r, player_c = self.player_pos[self.current_turn_player]
        other_player_pos = self.player_pos[2 if self.current_turn_player == 1 else 1]
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            path_steps, step = self.dice_roll, 1
            visited_ice, current_pos, final_dest = set(), (player_r, player_c), None
            while step <= path_steps:
                next_pos = (current_pos[0] + dr, current_pos[1] + dc)
                if not (0 <= next_pos[0] < BOARD_SIZE and 0 <= next_pos[1] < BOARD_SIZE):
                    if final_dest: self.fall_trigger_tiles.append(final_dest)
                    break
                if self.board[next_pos] == STONE_MARKER or next_pos == other_player_pos:
                    if final_dest: self.movable_tiles.append(final_dest)
                    break
                final_dest, current_pos = next_pos, next_pos
                if self.board[next_pos] == ICE_MARKER and next_pos not in visited_ice:
                    path_steps += 1; visited_ice.add(next_pos)
                step += 1
            else:
                if final_dest: self.movable_tiles.append(final_dest)
        self.movable_tiles, self.fall_trigger_tiles = list(set(self.movable_tiles)), list(set(self.fall_trigger_tiles))
        if not self.movable_tiles and not self.fall_trigger_tiles:
            self.game_over(winner=2 if self.current_turn_player == 1 else 1, reason="is blocked and cannot move!")

    def move_player(self, new_r, new_c):
        dest_type = self.board[new_r, new_c]
        if dest_type == BOMB_MARKER:
            self.game_over(winner=2 if self.current_turn_player == 1 else 1, reason="stepped on a bomb!")
            return
        self.player_pos[self.current_turn_player] = (new_r, new_c)
        if dest_type == RECOVERY_MARKER: self.player_points[self.current_turn_player] += 20
        self.current_phase = "place"; self.placement_type = 'stone'
        self.clear_highlights(); self.find_placeable_tiles()

    def set_placement_type(self, p_type):
        cost = self.skill_costs.get(p_type)
        if cost is not None and self.player_points[self.current_turn_player] < cost: return
        self.placement_type = p_type
        if p_type == 'drill':
            self.current_phase = 'drill_target'; self.find_drill_target_tiles()
        else:
            self.current_phase = 'place'; self.find_placeable_tiles()

    def find_placeable_tiles(self):
        self.placeable_tiles, self.drill_target_tiles = [], []
        player_r, player_c = self.player_pos[self.current_turn_player]
        other_player_pos = self.player_pos[2 if self.current_turn_player == 1 else 1]
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            r, c = player_r + dr, player_c + dc
            if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and (r, c) != other_player_pos:
                if self.placement_type == 'stone':
                    if self.board[r, c] != STONE_MARKER: self.placeable_tiles.append((r, c))
                elif self.placement_type in ['recovery', 'bomb', 'ice']:
                    if self.board[r, c] == EMPTY_MARKER: self.placeable_tiles.append((r, c))
        if not self.placeable_tiles and self.winner is None:
            self.game_over(winner=2 if self.current_turn_player == 1 else 1, reason="has no place to put an object!")

    def place_object(self, r, c):
        if self.placement_type == 'stone':
            self.board[r, c] = STONE_MARKER
            bonus_count, bonus_coords = self.check_figure_bonus(r, c)
            if bonus_count > 0:
                self.player_points[self.current_turn_player] += 10 * bonus_count
                self.figure_bonus_tiles, self.figure_bonus_timer = bonus_coords, 90
        else:
            self.player_points[self.current_turn_player] -= self.skill_costs[self.placement_type]
            marker_map = {'recovery': RECOVERY_MARKER, 'bomb': BOMB_MARKER, 'ice': ICE_MARKER}
            self.board[r, c] = marker_map[self.placement_type]
        self.end_turn()

    def _is_shape_complete(self, tl_r, tl_c, shape_coords):
        coords = []
        for dr, dc in shape_coords:
            r, c = tl_r + dr, tl_c + dc
            if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r, c] == STONE_MARKER): return None
            coords.append((r, c))
        return coords

    def check_figure_bonus(self, r, c):
        shapes = [
            {(0,0), (1,0), (2,0), (0,1), (2,1)}, {(0,0), (2,0), (0,1), (1,1), (2,1)},
            {(0,0), (1,0), (0,1), (0,2), (1,2)}, {(0,0), (0,2), (1,0), (1,1), (1,2)}
        ]
        found_shapes = set()
        for shape in shapes:
            for dr, dc in shape:
                tl_r, tl_c = r - dr, c - dc
                completed_coords = self._is_shape_complete(tl_r, tl_c, shape)
                if completed_coords: found_shapes.add(frozenset(completed_coords))
        if not found_shapes: return 0, []
        all_bonus_coords = set().union(*found_shapes)
        return len(found_shapes), list(all_bonus_coords)

    def find_drill_target_tiles(self):
        self.drill_target_tiles, self.placeable_tiles = [], []
        player_r, player_c = self.player_pos[self.current_turn_player]
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            r, c = player_r + dr, player_c + dc
            if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r, c] == STONE_MARKER:
                self.drill_target_tiles.append((r, c))
        if not self.drill_target_tiles: print("破壊できる石がありません")

    def use_drill(self, r, c):
        self.player_points[self.current_turn_player] -= self.skill_costs['drill']
        self.board[r, c] = EMPTY_MARKER
        self.end_turn()

    def end_turn(self):
        self.current_turn_player = 2 if self.current_turn_player == 1 else 1
        self.player_points[self.current_turn_player] += 10
        self.current_phase = "roll"; self.dice_roll = 0
        self.clear_highlights()

    def clear_highlights(self):
        self.movable_tiles, self.placeable_tiles, self.fall_trigger_tiles, self.drill_target_tiles = [], [], [], []

    def game_over(self, winner, reason):
        if self.winner is None:
            loser = 1 if winner == 2 else 2
            self.winner = winner; self.win_reason = f"Player {loser} {reason}"; self.current_phase = "game_over"

# --- 描画関連の関数 ---
def draw_board(screen, game_state, icon_images):
    move_highlight_surf = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA); move_highlight_surf.fill(MOVE_HIGHLIGHT_COLOR)
    fall_highlight_surf = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA); fall_highlight_surf.fill(FALL_HIGHLIGHT_COLOR)
    place_highlight_surf = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA); place_highlight_surf.fill(PLACE_HIGHLIGHT_COLOR)
    bonus_highlight_surf = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA); bonus_highlight_surf.fill(FIGURE_BONUS_HIGHLIGHT_COLOR)
    drill_highlight_surf = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA); drill_highlight_surf.fill(DRILL_TARGET_HIGHLIGHT_COLOR)

    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            rect = pygame.Rect(c * CELL_SIZE + BOARD_OFFSET_X, r * CELL_SIZE + BOARD_OFFSET_Y, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(screen, WHITE, rect)
            tile_type = game_state.board[r, c]
            icon_to_draw = None
            if tile_type == RECOVERY_MARKER:
                pygame.draw.rect(screen, RECOVERY_TILE_COLOR, rect); icon_to_draw = icon_images['recovery']
            elif tile_type == BOMB_MARKER:
                pygame.draw.rect(screen, BOMB_TILE_COLOR, rect); icon_to_draw = icon_images['bomb']
            elif tile_type == STONE_MARKER:
                icon_to_draw = icon_images['stone']
            elif tile_type == ICE_MARKER:
                pygame.draw.rect(screen, ICE_TILE_COLOR, rect); icon_to_draw = icon_images['ice']
            pygame.draw.rect(screen, GRID_COLOR, rect, 1)
            if icon_to_draw:
                screen.blit(icon_to_draw, icon_to_draw.get_rect(center=rect.center))

    for r, c in game_state.movable_tiles:
         screen.blit(move_highlight_surf, (c * CELL_SIZE + BOARD_OFFSET_X, r * CELL_SIZE + BOARD_OFFSET_Y))
    for r, c in game_state.fall_trigger_tiles:
        screen.blit(fall_highlight_surf, (c * CELL_SIZE + BOARD_OFFSET_X, r * CELL_SIZE + BOARD_OFFSET_Y))
    if game_state.current_phase == 'place':
        for r, c in game_state.placeable_tiles:
            screen.blit(place_highlight_surf, (c * CELL_SIZE + BOARD_OFFSET_X, r * CELL_SIZE + BOARD_OFFSET_Y))
    if game_state.current_phase == 'drill_target':
        for r, c in game_state.drill_target_tiles:
            screen.blit(drill_highlight_surf, (c * CELL_SIZE + BOARD_OFFSET_X, r * CELL_SIZE + BOARD_OFFSET_Y))
    
    if game_state.figure_bonus_timer > 0 and (game_state.figure_bonus_timer // 10) % 2 == 0:
        for r, c in game_state.figure_bonus_tiles:
            screen.blit(bonus_highlight_surf, (c * CELL_SIZE + BOARD_OFFSET_X, r * CELL_SIZE + BOARD_OFFSET_Y))

    for player_num, pos in game_state.player_pos.items():
        r, c = pos
        center = (c * CELL_SIZE + BOARD_OFFSET_X + CELL_SIZE // 2, r * CELL_SIZE + BOARD_OFFSET_Y + CELL_SIZE // 2)
        color = P1_COLOR if player_num == 1 else P2_COLOR
        pygame.draw.circle(screen, color, center, CELL_SIZE // 2 - 10)

def draw_player_panels(screen, game_state, fonts, button_rects):
    p1_panel_rect = pygame.Rect(0, 0, PANEL_WIDTH, SCREEN_HEIGHT)
    p2_panel_rect = pygame.Rect(SCREEN_WIDTH - PANEL_WIDTH, 0, PANEL_WIDTH, SCREEN_HEIGHT)
    pygame.draw.rect(screen, P1_PANEL_BG, p1_panel_rect)
    pygame.draw.rect(screen, P2_PANEL_BG, p2_panel_rect)

    for player_num in [1, 2]:
        panel_rect = p1_panel_rect if player_num == 1 else p2_panel_rect
        text_color = WHITE
        
        if game_state.current_phase == "skill_selection":
            if not game_state.selection_confirmed[player_num]:
                title_surf = fonts['large'].render(f"Player {player_num}", True, text_color)
                screen.blit(title_surf, (panel_rect.x + 20, 50))
                subtitle_surf = fonts['medium'].render("Choose Special Skill", True, text_color)
                screen.blit(subtitle_surf, (panel_rect.x + 20, 120))
                
                btn1 = button_rects['start_skill_1'].move(panel_rect.x, 0)
                pygame.draw.rect(screen, ICE_TILE_COLOR, btn1); pygame.draw.rect(screen, WHITE, btn1, 3)
                title1 = fonts['medium'].render("Ice Skill", True, BLACK); desc1 = fonts['small'].render("Place ice tiles", True, BLACK)
                screen.blit(title1, (btn1.x + 20, btn1.y + 20)); screen.blit(desc1, (btn1.x + 20, btn1.y + 60))
            else:
                title_surf = fonts['large'].render(f"Player {player_num}", True, text_color)
                screen.blit(title_surf, (panel_rect.x + 20, 50))
                ready_surf = fonts['large'].render("Ready!", True, (0, 255, 0))
                screen.blit(ready_surf, (panel_rect.x + 20, 250))
            continue

        is_turn = game_state.current_turn_player == player_num
        name_surf = fonts['large'].render(f"Player {player_num}{' (Turn)' if is_turn and game_state.winner is None else ''}", True, text_color)
        screen.blit(name_surf, (panel_rect.x + 20, 50))
        
        points_surf = fonts['medium'].render(f"Points: {game_state.player_points[player_num]}", True, text_color)
        screen.blit(points_surf, (panel_rect.x + 20, 120))
        
        if is_turn and game_state.dice_roll > 0:
            dice_surf = fonts['medium'].render(f"Dice Roll: {game_state.dice_roll}", True, (255, 255, 0))
            screen.blit(dice_surf, (panel_rect.x + 20, 240))

        if is_turn:
            if game_state.current_phase == 'roll':
                btn = button_rects['roll'].move(panel_rect.x, 0)
                pygame.draw.rect(screen, (0, 200, 0), btn)
                text = fonts['medium'].render("Roll Dice", True, WHITE)
                screen.blit(text, text.get_rect(center=btn.center))
            
            elif game_state.current_phase in ['place', 'drill_target']:
                btn_stone = button_rects['place_stone'].move(panel_rect.x, 0)
                pygame.draw.rect(screen, STONE_COLOR, btn_stone)
                if game_state.placement_type == 'stone' and game_state.current_phase == 'place': pygame.draw.rect(screen, WHITE, btn_stone, 4)
                text_stone = fonts['medium'].render("Place Stone", True, WHITE)
                screen.blit(text_stone, text_stone.get_rect(center=btn_stone.center))
                
                btn_rec = button_rects['place_recovery'].move(panel_rect.x, 0)
                pygame.draw.rect(screen, RECOVERY_TILE_COLOR, btn_rec)
                if game_state.placement_type == 'recovery': pygame.draw.rect(screen, WHITE, btn_rec, 4)
                text_rec = fonts['small'].render(f"Recovery ({game_state.skill_costs['recovery']}pt)", True, BLACK)
                screen.blit(text_rec, text_rec.get_rect(center=btn_rec.center))

                btn_bomb = button_rects['place_bomb'].move(panel_rect.x, 0)
                pygame.draw.rect(screen, BOMB_TILE_COLOR, btn_bomb)
                if game_state.placement_type == 'bomb': pygame.draw.rect(screen, WHITE, btn_bomb, 4)
                text_bomb = fonts['small'].render(f"Bomb ({game_state.skill_costs['bomb']}pt)", True, BLACK)
                screen.blit(text_bomb, text_bomb.get_rect(center=btn_bomb.center))

                btn_drill = button_rects['use_drill'].move(panel_rect.x, 0)
                pygame.draw.rect(screen, DRILL_COLOR, btn_drill)
                if game_state.current_phase == 'drill_target': pygame.draw.rect(screen, WHITE, btn_drill, 4)
                text_drill = fonts['small'].render(f"Drill ({game_state.skill_costs['drill']}pt)", True, WHITE)
                screen.blit(text_drill, text_drill.get_rect(center=btn_drill.center))
                
                if game_state.special_skill[player_num] == 'ice_skill':
                    btn_ice = button_rects['place_ice'].move(panel_rect.x, 0)
                    pygame.draw.rect(screen, ICE_TILE_COLOR, btn_ice)
                    if game_state.placement_type == 'ice': pygame.draw.rect(screen, WHITE, btn_ice, 4)
                    text_ice = fonts['small'].render(f"Ice ({game_state.skill_costs['ice']}pt)", True, BLACK)
                    screen.blit(text_ice, text_ice.get_rect(center=btn_ice.center))

def draw_game_over_screen(screen, game_state, fonts):
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA); overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))
    win_surf = fonts['large'].render(f"Player {game_state.winner} Wins!", True, (255, 215, 0))
    screen.blit(win_surf, win_surf.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 - 80)))
    reason_surf = fonts['medium'].render(game_state.win_reason, True, WHITE)
    screen.blit(reason_surf, reason_surf.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 - 20)))
    restart_button_rect = pygame.Rect(0, 0, 200, 50); restart_button_rect.center = (SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 + 50)
    pygame.draw.rect(screen, (0, 150, 0), restart_button_rect)
    btn_text = fonts['medium'].render("Restart", True, WHITE)
    screen.blit(btn_text, btn_text.get_rect(center=restart_button_rect.center))
    return restart_button_rect

# --- メイン処理 ---
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("2人対戦ターン制ストラテジーゲーム")
    clock = pygame.time.Clock()
    
    fonts = { 'small': pygame.font.Font(None, 32), 'medium': pygame.font.Font(None, 40), 'large': pygame.font.Font(None, 50) }
    
    try:
        icon_size = int(CELL_SIZE * 0.8)
        icon_images = {
            'stone': pygame.transform.scale(pygame.image.load('stone.png').convert_alpha(), (icon_size, icon_size)),
            'recovery': pygame.transform.scale(pygame.image.load('recovery.png').convert_alpha(), (icon_size, icon_size)),
            'bomb': pygame.transform.scale(pygame.image.load('bomb.png').convert_alpha(), (icon_size, icon_size)),
            'ice': pygame.transform.scale(pygame.image.load('ice.png').convert_alpha(), (icon_size, icon_size)),
        }
    except pygame.error as e:
        print(f"画像の読み込みに失敗しました: {e}"); pygame.quit(); sys.exit()

    game_state = GameState()
    
    button_rects = {
        'start_skill_1': pygame.Rect(20, 250, PANEL_WIDTH - 40, 120),
        'roll': pygame.Rect(40, 300, 200, 60),
        'place_stone': pygame.Rect(40, 300, 200, 50),
        'place_recovery': pygame.Rect(40, 360, 200, 50),
        'place_bomb': pygame.Rect(40, 420, 200, 50),
        'use_drill': pygame.Rect(40, 480, 200, 50),
        'place_ice': pygame.Rect(40, 540, 200, 50),
        'restart': pygame.Rect(0, 0, 200, 50)
    }
    button_rects['restart'].center = (SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 + 50)

    while True:
        if game_state.figure_bonus_timer > 0:
            game_state.figure_bonus_timer -= 1
            if game_state.figure_bonus_timer == 0:
                game_state.figure_bonus_tiles = []

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = pygame.mouse.get_pos()
                
                if game_state.current_phase == "skill_selection":
                    if not game_state.selection_confirmed[1]:
                        if button_rects['start_skill_1'].collidepoint(pos): game_state.select_starting_skill(1, 'ice_skill')
                    if not game_state.selection_confirmed[2]:
                        btn1_p2 = button_rects['start_skill_1'].move(SCREEN_WIDTH - PANEL_WIDTH, 0)
                        if btn1_p2.collidepoint(pos): game_state.select_starting_skill(2, 'ice_skill')
                
                elif game_state.current_phase == "game_over":
                    if button_rects['restart'].collidepoint(pos): game_state = GameState()
                
                else:
                    active_panel_offset = 0 if game_state.current_turn_player == 1 else (SCREEN_WIDTH - PANEL_WIDTH)
                    
                    if game_state.current_phase == "roll":
                        if button_rects['roll'].move(active_panel_offset, 0).collidepoint(pos):
                            game_state.dice_roll = random.randint(1, 3); game_state.find_movable_tiles()
                            if game_state.winner is None: game_state.current_phase = "move"
                    
                    elif game_state.current_phase == "move":
                        clicked_col = (pos[0] - BOARD_OFFSET_X) // CELL_SIZE; clicked_row = (pos[1] - BOARD_OFFSET_Y) // CELL_SIZE
                        if (clicked_row, clicked_col) in game_state.fall_trigger_tiles:
                            game_state.game_over(winner=2 if game_state.current_turn_player == 1 else 1, reason="fell off the cliff!")
                        elif (clicked_row, clicked_col) in game_state.movable_tiles:
                            game_state.move_player(clicked_row, clicked_col)
                    
                    elif game_state.current_phase in ['place', 'drill_target']:
                        btn_stone = button_rects['place_stone'].move(active_panel_offset, 0)
                        btn_rec = button_rects['place_recovery'].move(active_panel_offset, 0)
                        btn_bomb = button_rects['place_bomb'].move(active_panel_offset, 0)
                        btn_drill = button_rects['use_drill'].move(active_panel_offset, 0)
                        btn_ice = button_rects['place_ice'].move(active_panel_offset, 0)
                        
                        if btn_stone.collidepoint(pos): game_state.set_placement_type('stone')
                        elif btn_rec.collidepoint(pos): game_state.set_placement_type('recovery')
                        elif btn_bomb.collidepoint(pos): game_state.set_placement_type('bomb')
                        elif btn_drill.collidepoint(pos): game_state.set_placement_type('drill')
                        elif game_state.special_skill[game_state.current_turn_player] == 'ice_skill' and btn_ice.collidepoint(pos):
                            game_state.set_placement_type('ice')
                        
                        else:
                            clicked_col = (pos[0] - BOARD_OFFSET_X) // CELL_SIZE
                            clicked_row = (pos[1] - BOARD_OFFSET_Y) // CELL_SIZE
                            if game_state.current_phase == 'drill_target':
                                if (clicked_row, clicked_col) in game_state.drill_target_tiles:
                                    game_state.use_drill(clicked_row, clicked_col)
                            elif game_state.current_phase == 'place':
                                if (0 <= clicked_col < BOARD_SIZE and 0 <= clicked_row < BOARD_SIZE) and \
                                     (clicked_row, clicked_col) in game_state.placeable_tiles:
                                    game_state.place_object(clicked_row, clicked_col)

        screen.fill(BLACK)
        
        if game_state.current_phase == "skill_selection":
            draw_player_panels(screen, game_state, fonts, button_rects)
            draw_board(screen, game_state, icon_images)
        elif game_state.winner is not None:
            draw_player_panels(screen, game_state, fonts, button_rects)
            draw_board(screen, game_state, icon_images)
            draw_game_over_screen(screen, game_state, fonts)
        else:
            draw_player_panels(screen, game_state, fonts, button_rects)
            draw_board(screen, game_state, icon_images)

        pygame.display.flip()
        clock.tick(60)

if __name__ == '__main__':
    main()
