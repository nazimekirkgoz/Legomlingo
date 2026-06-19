import time
import logging
import math
import numpy as np
import pygame
import bleak
import asyncio
import threading 

# pylgbst libraries
from pylgbst.hub import MoveHub
from pylgbst.peripherals import VisionSensor
from pylgbst import get_connection_auto

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# --- Python 3.12 Compatibility Patch ---
if not hasattr(bleak, "discover"):
    async def custom_discover(timeout=5.0, **kwargs):
        from bleak import BleakScanner
        return await BleakScanner.discover(timeout=timeout, **kwargs)
    bleak.discover = custom_discover
# ----------------------------------------

# --- SETTINGS (Check your MAC address) ---
SAMPLE_RATE = 44100
LEGO_MAC_ADRESI = '00:16:53:C1:B6:DD' # ⭐ PLEASE CHECK
pygame.mixer.init(SAMPLE_RATE, -16, 2, 512) # Initialize Pygame audio

# --- GUITAR SOUND GENERATOR ---
def generate_guitar_note(frequency, duration=1.0):
    n_samples = int(SAMPLE_RATE * duration)
    period = int(SAMPLE_RATE / frequency)
    string = np.random.uniform(-1, 1, period)
    samples = np.zeros(n_samples)
    
    # ⭐ TONE SETTING: Increased decay for longer sustain (0.996 -> 0.999)
    decay = 0.999 
    
    previous_val = 0
    buffer = list(string)
    output = []
    for _ in range(n_samples):
        val = buffer.pop(0)
        avg = 0.5 * (val + previous_val)
        new_val = avg * decay
        buffer.append(new_val)
        output.append(val)
        previous_val = val
    sound_array = np.array(output, dtype=np.float32)
    sound_array = np.column_stack((sound_array, sound_array))
    return pygame.sndarray.make_sound((sound_array * 32767).astype(np.int16))

# --- NOTE AND MELODY DEFINITIONS ---
NOTES = {
    'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23, 'G4': 392.00, 'A4': 440.00, 'B4': 493.88,
    'C5': 523.25, 'D5': 587.33, 'E5': 659.25, 'F5': 698.46, 'G5': 783.99, 'A5': 880.00, 'Bb4': 466.16
}

# ⭐ TITANIC MELODIES (CORRECTED)
MELODIES = {
    "VERSE": [
        ('F4', 1.0), ('F4', 1.0), ('F4', 1.0), ('F4', 1.0), ('E4', 1.0), ('F4', 2.0), # Every night in my dreams
        ('F4', 1.0), ('E4', 1.0), ('F4', 1.0), ('G4', 1.0), ('A4', 2.0), ('G4', 2.0), # I see you I feel you
        ('F4', 1.0), ('F4', 1.0), ('F4', 1.0), ('F4', 1.0), ('E4', 1.0), ('F4', 2.0), # That is how I know you
        ('F4', 1.0), ('E4', 1.0), ('F4', 1.0), ('G4', 1.0), ('A4', 2.0), ('G4', 2.0) # Far across the distance
         # Go on (Simple ending)
    ],
    "CHORUS": [
        ('F4', 1.0), ('G4', 3.0), ('C5', 2.0), ('Bb4', 1.0), ('A4', 1.0), ('G4', 3.0), # Near, far, wherever you are
        ('F4', 1.0), ('G4', 3.0), ('C5', 2.0), ('Bb4', 1.0), ('A4', 1.0), ('G4', 3.0), # I believe that the heart does go on
    ],
    "ENDING": [
       ('F4', 1.0), ('F4', 0.5), ('F4', 0.5), ('F4', 0.5), ('E4', 1.0), ('F4', 2.0) # Outro
    ]
}

# ⭐ LYRICS
LYRICS = {
    "VERSE": {
        0: "Every night in my dreams",
        6: "I see you I feel you",
        12: "That is how I know you",
        24: "Go on"
        18: "Far across the distance...",
       
    },
    "CHORUS": {
        0: "Near, far, wherever you are",
        7: "I believe that the heart does go on"
    },
    "ENDING": {
        0: "Outro..."
    }
}

# ⭐ NOTE NAMES (SOLFÈGE)
NOTE_NAMES = {
    'C4': 'DO', 'D4': 'RE', 'E4': 'MI', 'F4': 'FA', 'G4': 'SOL', 'A4': 'LA', 'B4': 'SI',
    'C5': 'DO (High)', 'D5': 'RE (High)', 'E5': 'MI (High)', 'F5': 'FA (High)', 'G5': 'SOL (High)', 'A5': 'LA (High)', 'Bb4': 'SI (Flat)'
}

# --- TITANIC GUITAR CLASS ---
class TitanicGuitar:
    def __init__(self):
        # Pygame Screen
        pygame.init()
        self.screen_width = 800
        self.screen_height = 600
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("LEGO Titanic Guitar")
        
        # Fonts
        self.font_small = pygame.font.Font(None, 24)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_large = pygame.font.Font(None, 72)
        self.font_huge = pygame.font.Font(None, 120)

        # State Variables
        self.is_connected = False
        self.demo_mode = False
        self.next_strum_time = 0.0
        self.base_tempo = 0.5 

        # Melody State
        self.melody_sounds = {note: generate_guitar_note(freq, 2.0) for note, freq in NOTES.items()} # 2.0s duration for better sustain
        self.current_melody_name = "VERSE"
        self.current_melody = MELODIES[self.current_melody_name]
        self.note_index = 0
        self.current_lyric = "" 
        self.current_note_name = "" 
        
        # Sensor Data
        self.raw_color_code = None
        self.last_distance = None
        self.volume = 1.0

    def set_volume(self, distance):
        """Sets volume based on distance."""
        if distance is None:
            vol = 0.0
        else:
            # 0-10 inches. Close=1.0, Far=0.0
            vol = 1.0 - (min(distance, 10.0) / 10.0)
            vol = max(0.0, min(1.0, vol))
            
        self.volume = vol
        for s in self.melody_sounds.values():
            s.set_volume(self.volume)

    def play_next_note(self):
        """Plays the next note in the current melody."""
        if not self.current_melody:
            return self.base_tempo
            
        note_name, duration_multiplier = self.current_melody[self.note_index]
        
        # Visual Updates
        self.current_note_name = NOTE_NAMES.get(note_name, note_name)
        if self.current_melody_name in LYRICS and self.note_index in LYRICS[self.current_melody_name]:
            self.current_lyric = LYRICS[self.current_melody_name][self.note_index]

        # Play Sound
        if note_name in self.melody_sounds and self.volume > 0.05:
            self.melody_sounds[note_name].play()
            
        self.note_index += 1
        if self.note_index >= len(self.current_melody):
            self.note_index = 0 # Loop back
            
        return duration_multiplier

    def switch_melody(self, new_melody_name):
        """Instantly switches the melody."""
        if new_melody_name not in MELODIES: return
        
        if self.current_melody_name != new_melody_name:
            logging.info(f"🎶 Melody: {self.current_melody_name} -> {new_melody_name}")
            self.current_melody_name = new_melody_name
            self.current_melody = MELODIES[new_melody_name]
            self.note_index = 0
            self.current_lyric = ""
            self.next_strum_time = 0.0

    def toggle_demo(self):
        self.demo_mode = not self.demo_mode
        logging.info(f"Demo Mode: {self.demo_mode}")
        self.next_strum_time = 0.0

    def update_display(self):
        """Draws the screen."""
        self.screen.fill((0, 0, 0))
        center = (self.screen_width // 2, self.screen_height // 2)
        
        # Color Info
        color_map = {
            "VERSE": ((255, 50, 50), "RED (VERSE)"),
            "CHORUS": ((50, 255, 50), "GREEN (CHORUS)"),
            "ENDING": ((50, 50, 255), "BLUE (ENDING)")
        }
        current_color, color_name = color_map.get(self.current_melody_name, ((100,100,100), "WAITING"))

        # Ring and Progress
        pygame.draw.circle(self.screen, (30, 30, 30), center, 160, 10)
        pygame.draw.circle(self.screen, current_color, center, 150, 5)
        
        # Texts
        text_section = self.font_large.render(self.current_melody_name, True, (200, 200, 200))
        self.screen.blit(text_section, (center[0] - text_section.get_width()//2, 80))

        text_note = self.font_huge.render(self.current_note_name, True, (255, 255, 255))
        self.screen.blit(text_note, text_note.get_rect(center=center))
        
        if self.current_lyric:
            lyric_surf = self.font_medium.render(f'"{self.current_lyric}"', True, (255, 255, 200))
            self.screen.blit(lyric_surf, lyric_surf.get_rect(center=(center[0], center[1] + 100)))

        # Volume Bar
        vol_h = int(self.volume * 200)
        pygame.draw.rect(self.screen, (50, 50, 50), (750, 200, 20, 200))
        pygame.draw.rect(self.screen, (0, 255, 0), (750, 400 - vol_h, 20, vol_h))
        
        # Status
        status = "DEMO MODE" if self.demo_mode else "SHOW COLOR: Red/Green/Blue"
        if not self.is_connected and not self.demo_mode: status = "SEARCHING FOR LEGO..."
        
        st_surf = self.font_medium.render(status, True, (150, 150, 150))
        self.screen.blit(st_surf, (center[0] - st_surf.get_width()//2, 500))

        pygame.display.flip()

# --- LEGO CALLBACK ---
guitar = None

def sensor_callback(color, distance):
    global guitar
    if not guitar: return

    guitar.raw_color_code = color
    guitar.last_distance = distance
    
    # Update Volume
    guitar.set_volume(distance)

# --- MAIN PROGRAM ---
def main():
    global guitar
    guitar = TitanicGuitar()
    
    def boost_thread_target():
        while True: 
            try:
                connection = get_connection_auto(hub_mac=LEGO_MAC_ADRESI)
                hub = MoveHub(connection)
                guitar.is_connected = True
                logging.info("CONNECTED!")
                hub.vision_sensor.subscribe(sensor_callback)
                while True:
                    time.sleep(2)
                    hub.led.set_color(3)
            except Exception:
                guitar.is_connected = False
                time.sleep(3) 
    
    threading.Thread(target=boost_thread_target, daemon=True).start()
    
    try:
        running = True
        clock = pygame.time.Clock()
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False 
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_d: guitar.toggle_demo()
                    if event.key == pygame.K_ESCAPE: running = False
            
            current_time = time.time()
            
            # --- PLAYBACK LOGIC ---
            should_play = False
            
            if guitar.demo_mode:
                should_play = True
                # Demo Auto-Sequence Logic could go here, but keeping it simple for now
            elif guitar.is_connected:
                # Color Control (Strict Gating)
                color = guitar.raw_color_code
                target = None
                if color == 9: target = "VERSE"
                elif color == 5: target = "CHORUS"
                elif color == 3: target = "ENDING"
                
                if target:
                    guitar.switch_melody(target)
                    should_play = True
                else:
                    should_play = False # Stop if no color
            
            if should_play and current_time >= guitar.next_strum_time:
                duration_mult = guitar.play_next_note()
                guitar.next_strum_time = current_time + (duration_mult * guitar.base_tempo)
            
            guitar.update_display()
            clock.tick(60)
            
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()

if __name__ == "__main__":
    main()