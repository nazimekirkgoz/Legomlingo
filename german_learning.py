import time
import logging
import random
import pygame
import bleak
import threading
import asyncio

import os
import re
import numpy as np

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

# --- AUDIO GENERATION HELPER ---
SAMPLE_RATE = 44100

def generate_guitar_note(frequency, duration=1.0):
    n_samples = int(SAMPLE_RATE * duration)
    period = int(SAMPLE_RATE / frequency)
    string = np.random.uniform(-1, 1, period)
    samples = np.zeros(n_samples)
    
    decay = 0.996 # slightly faster decay for standard feedback sounds
    
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

# --- VISUAL FEEDBACK HELPERS ---
def draw_lego_brick(surface, x, y, color_rgb, size=(120, 60)):
    w, h = size
    shadow_color = tuple(max(0, c - 60) for c in color_rgb)
    highlight_color = tuple(min(255, c + 50) for c in color_rgb)
    
    # Draw main brick shadow (rounded)
    pygame.draw.rect(surface, shadow_color, (x + 4, y + 4, w, h), border_radius=8)
    # Draw main brick body
    pygame.draw.rect(surface, color_rgb, (x, y, w, h), border_radius=8)
    # Draw main brick border/highlight
    pygame.draw.rect(surface, highlight_color, (x, y, w, h), 2, border_radius=8)
    
    # Draw 2x4 studs
    stud_r = min(w, h) // 10
    dx = w // 4
    dy = h // 2
    for row in range(2):
        for col in range(4):
            cx = x + dx * col + dx // 2
            cy = y + dy * row + dy // 2
            # Stud shadow
            pygame.draw.circle(surface, shadow_color, (cx + 1, cy + 1), stud_r)
            # Stud body
            pygame.draw.circle(surface, color_rgb, (cx, cy), stud_r)
            # Stud highlight
            pygame.draw.circle(surface, highlight_color, (cx, cy), stud_r, 1)

def get_word_image_path(word):
    # Replace German umlauts
    w = word.lower().strip()
    w = w.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    # Keep only alphanumeric characters
    w = re.sub(r'[^a-z0-9]', '', w)
    return f"images/{w}.png"

# --- SETTINGS ---
LEGO_MAC_ADRESI = '00:16:53:C1:B6:DD' 

# --- DATA ---
ARTICLES = {
    "Die": {"color_code": 9, "color_name": "RED", "rgb": (255, 50, 50)},
    "Der": {"color_code": 3, "color_name": "BLUE", "rgb": (50, 100, 255)},
    "Das": {"color_code": 5, "color_name": "GREEN", "rgb": (50, 200, 50)}
}

WORD_POOLS = {
    "KLASSE_1": [
        # Animals & Basics (1. Klasse)
        {"word": "Hund", "article": "Der", "plural": "Hunde", "def": "Ein Haustier, das bellt."},
        {"word": "Katze", "article": "Die", "plural": "Katzen", "def": "Ein Haustier, das miaut."},
        {"word": "Vogel", "article": "Der", "plural": "Vögel", "def": "Ein Tier, das fliegen kann."},
        {"word": "Maus", "article": "Die", "plural": "Mäuse", "def": "Ein kleines Tier, das Käse mag."},
        {"word": "Ball", "article": "Der", "plural": "Bälle", "def": "Damit spielt man."},
        {"word": "Sonne", "article": "Die", "plural": "Sonnen", "def": "Sie scheint am Himmel."},
        {"word": "Mond", "article": "Der", "plural": "Monde", "def": "Er leuchtet in der Nacht."},
        {"word": "Kind", "article": "Das", "plural": "Kinder", "def": "Ein junger Mensch."},
        {"word": "Schule", "article": "Die", "plural": "Schulen", "def": "Wo man lernt."},
        {"word": "Buch", "article": "Das", "plural": "Bücher", "def": "Man kann es lesen."},
        {"word": "Tisch", "article": "Der", "plural": "Tische", "def": "Daran sitzt man."},
        {"word": "Stift", "article": "Der", "plural": "Stifte", "def": "Damit schreibt man."},
        {"word": "Oma", "article": "Die", "plural": "Omas", "def": "Die Mutter der Mutter/des Vaters."},
        {"word": "Opa", "article": "Der", "plural": "Opas", "def": "Der Vater der Mutter/des Vaters."},
        {"word": "Haus", "article": "Das", "plural": "Häuser", "def": "Wo man wohnt."},
        # New Additions
        {"word": "Nase", "article": "Die", "plural": "Nasen", "def": "Mitten im Gesicht."},
        {"word": "Auge", "article": "Das", "plural": "Augen", "def": "Damit sieht man."},
        {"word": "Ohr", "article": "Das", "plural": "Ohren", "def": "Damit hört man."},
        {"word": "Mund", "article": "Der", "plural": "Münder", "def": "Damit isst und spricht man."},
        {"word": "Hand", "article": "Die", "plural": "Hände", "def": "Am Ende des Arms."},
        {"word": "Fuß", "article": "Der", "plural": "Füße", "def": "Damit läuft man."},
        {"word": "Arm", "article": "Der", "plural": "Arme", "def": "Verbindet Hand und Schulter."},
        {"word": "Bein", "article": "Das", "plural": "Beine", "def": "Zum Stehen und Gehen."},
        {"word": "Kopf", "article": "Der", "plural": "Köpfe", "def": "Ganz oben am Körper."},
        {"word": "Haar", "article": "Das", "plural": "Haare", "def": "Wächst auf dem Kopf."},
        {"word": "Mädchen", "article": "Das", "plural": "Mädchen", "def": "Ein junges weibliches Kind."}
    ],
    "KLASSE_2": [
        # Nature, Seasons, House (2. Klasse)
        {"word": "Baum", "article": "Der", "plural": "Bäume", "def": "Er hat Blätter und Wurzeln."},
        {"word": "Blume", "article": "Die", "plural": "Blumen", "def": "Sie blüht im Garten."},
        {"word": "Wasser", "article": "Das", "plural": "Wässer", "def": "Nass und flüssig."},
        {"word": "Feuer", "article": "Das", "plural": "Feuer", "def": "Heiß und leuchtend."},
        {"word": "Wind", "article": "Der", "plural": "Winde", "def": "Bewegte Luft."},
        {"word": "Wolke", "article": "Die", "plural": "Wolken", "def": "Weiß und am Himmel."},
        {"word": "Bett", "article": "Das", "plural": "Betten", "def": "Zum Schlafen."},
        {"word": "Stuhl", "article": "Der", "plural": "Stühle", "def": "Zum Sitzen."},
        {"word": "Fenster", "article": "Das", "plural": "Fenster", "def": "Man schaut hinaus."},
        {"word": "Tür", "article": "Die", "plural": "Türen", "def": "Ein- und Ausgang."},
        {"word": "Garten", "article": "Der", "plural": "Gärten", "def": "Draußen beim Haus."},
        {"word": "Straße", "article": "Die", "plural": "Straßen", "def": "Wo Autos fahren."},
        {"word": "Winter", "article": "Der", "plural": "Winter", "def": "Die kalte Jahreszeit."},
        {"word": "Sommer", "article": "Der", "plural": "Sommer", "def": "Die warme Jahreszeit."},
        {"word": "Schnee", "article": "Der", "plural": "Schnee", "def": "Weiß und kalt."},
        # New Additions
        {"word": "Berg", "article": "Der", "plural": "Berge", "def": "Hoch und felsig."},
        {"word": "See", "article": "Der", "plural": "Seen", "def": "Großes Gewässer."},
        {"word": "Fluss", "article": "Der", "plural": "Flüsse", "def": "Fließendes Wasser."},
        {"word": "Wald", "article": "Der", "plural": "Wälder", "def": "Viele Bäume."},
        {"word": "Wiese", "article": "Die", "plural": "Wiesen", "def": "Grasfläche."},
        {"word": "Stein", "article": "Der", "plural": "Steine", "def": "Hart und grau."},
        {"word": "Weg", "article": "Der", "plural": "Wege", "def": "Zum Drauflaufen."},
        {"word": "Brücke", "article": "Die", "plural": "Brücken", "def": "Weg über den Fluss."},
        {"word": "Himmel", "article": "Der", "plural": "Himmel", "def": "Oben, blau oder grau."},
        {"word": "Erde", "article": "Die", "plural": "Erden", "def": "Der Boden unter uns."}
    ],
    "KLASSE_3": [
        # City, Clothing, Time (3. Klasse)
        {"word": "Auto", "article": "Das", "plural": "Autos", "def": "Fahrzeug mit vier Rädern."},
        {"word": "Fahrrad", "article": "Das", "plural": "Fahrräder", "def": "Fahrzeug mit zwei Rädern."},
        {"word": "Bus", "article": "Der", "plural": "Busse", "def": "Großes Fahrzeug für viele."},
        {"word": "Zug", "article": "Der", "plural": "Züge", "def": "Fährt auf Schienen."},
        {"word": "Stadt", "article": "Die", "plural": "Städte", "def": "Viele Häuser und Menschen."},
        {"word": "Dorf", "article": "Das", "plural": "Dörfer", "def": "Wenig Häuser, viel Natur."},
        {"word": "Kleidung", "article": "Die", "plural": "Kleidungen", "def": "Was man anzieht."},
        {"word": "Hose", "article": "Die", "plural": "Hosen", "def": "Kleidung für die Beine."},
        {"word": "Hemd", "article": "Das", "plural": "Hemden", "def": "Kleidung für den Oberkörper."},
        {"word": "Schuh", "article": "Der", "plural": "Schuhe", "def": "Man trägt es an den Füßen."},
        {"word": "Uhr", "article": "Die", "plural": "Uhren", "def": "Zeigt die Zeit an."},
        {"word": "Zeit", "article": "Die", "plural": "Zeiten", "def": "Was die Uhr misst."},
        {"word": "Jahr", "article": "Das", "plural": "Jahre", "def": "365 Tage."},
        {"word": "Monat", "article": "Der", "plural": "Monate", "def": "Ca. 30 Tage."},
        {"word": "Woche", "article": "Die", "plural": "Wochen", "def": "7 Tage."},
        # New Additions
        {"word": "König", "article": "Der", "plural": "Könige", "def": "Trägt eine Krone."},
        {"word": "Königin", "article": "Die", "plural": "Königinnen", "def": "Frau des Königs."},
        {"word": "Schloss", "article": "Das", "plural": "Schlösser", "def": "Wo Könige wohnen."},
        {"word": "Ritter", "article": "Der", "plural": "Ritter", "def": "Kämpfer in Rüstung."},
        {"word": "Drache", "article": "Der", "plural": "Drachen", "def": "Fabelwesen, das Feuer speit."},
        {"word": "Markt", "article": "Der", "plural": "Märkte", "def": "Wo man draußen einkauft."},
        {"word": "Geld", "article": "Das", "plural": "Gelder", "def": "Zum Bezahlen."},
        {"word": "Preis", "article": "Der", "plural": "Preise", "def": "Was es kostet."},
        {"word": "Laden", "article": "Der", "plural": "Läden", "def": "Ein Geschäft."},
        {"word": "Kasse", "article": "Die", "plural": "Kassen", "def": "Wo man bezahlt."}
    ],
    "LEVEL_A1": [
        # Daily Life, Food, Family (A1)
        {"word": "Frühstück", "article": "Das", "plural": "Frühstücke", "def": "Essen am Morgen."},
        {"word": "Mittagessen", "article": "Das", "plural": "Mittagessen", "def": "Essen am Mittag."},
        {"word": "Abendessen", "article": "Das", "plural": "Abendessen", "def": "Essen am Abend."},
        {"word": "Brot", "article": "Das", "plural": "Brote", "def": "Grundnahrungsmittel."},
        {"word": "Apfel", "article": "Der", "plural": "Äpfel", "def": "Eine Frucht."},
        {"word": "Kaffee", "article": "Der", "plural": "Kaffees", "def": "Ein heißes Getränk."},
        {"word": "Milch", "article": "Die", "plural": "Milchen", "def": "Weißes Getränk von der Kuh."},
        {"word": "Freund", "article": "Der", "plural": "Freunde", "def": "Person, die man mag."},
        {"word": "Familie", "article": "Die", "plural": "Familien", "def": "Eltern und Kinder."},
        {"word": "Wohnung", "article": "Die", "plural": "Wohnungen", "def": "Gemietetes Zuhause."},
        {"word": "Zimmer", "article": "Das", "plural": "Zimmer", "def": "Raum in der Wohnung."},
        {"word": "Bad", "article": "Das", "plural": "Bäder", "def": "Wo man sich wäscht."},
        {"word": "Küche", "article": "Die", "plural": "Küchen", "def": "Wo man kocht."},
        {"word": "Datum", "article": "Das", "plural": "Daten", "def": "Kalendertag."},
        {"word": "Name", "article": "Der", "plural": "Namen", "def": "Wie man heißt."},
        # New Additions
        {"word": "Wasser", "article": "Das", "plural": "Wässer", "def": "Zum Trinken."},
        {"word": "Tee", "article": "Der", "plural": "Tees", "def": "Heißes Getränk aus Blättern."},
        {"word": "Saft", "article": "Der", "plural": "Säfte", "def": "Getränk aus Früchten."},
        {"word": "Bier", "article": "Das", "plural": "Biere", "def": "Alkohol aus Hopfen."},
        {"word": "Wein", "article": "Der", "plural": "Weine", "def": "Alkohol aus Trauben."},
        {"word": "Glas", "article": "Das", "plural": "Gläser", "def": "Daraus trinkt man."},
        {"word": "Tasse", "article": "Die", "plural": "Tassen", "def": "Für Kaffee oder Tee."},
        {"word": "Teller", "article": "Der", "plural": "Teller", "def": "Darauf liegt das Essen."},
        {"word": "Gabel", "article": "Die", "plural": "Gabeln", "def": "Zum Aufspießen."},
        {"word": "Löffel", "article": "Der", "plural": "Löffel", "def": "Für Suppe."},
        {"word": "Mädchen", "article": "Das", "plural": "Mädchen", "def": "Ein junges weibliches Kind."}
    ],
    "LEVEL_A2": [
        # Work, Travel, Shopping (A2)
        {"word": "Arbeit", "article": "Die", "plural": "Arbeiten", "def": "Job oder Tätigkeit."},
        {"word": "Beruf", "article": "Der", "plural": "Berufe", "def": "Was man gelernt hat."},
        {"word": "Büro", "article": "Das", "plural": "Büros", "def": "Arbeitsraum mit Schreibtisch."},
        {"word": "Chef", "article": "Der", "plural": "Chefs", "def": "Vorgesetzter."},
        {"word": "Urlaub", "article": "Der", "plural": "Urlaube", "def": "Freie Zeit ohne Arbeit."},
        {"word": "Reise", "article": "Die", "plural": "Reisen", "def": "Fahrt an einen anderen Ort."},
        {"word": "Flugzeug", "article": "Das", "plural": "Flugzeuge", "def": "Fliegt in der Luft."},
        {"word": "Fahrkarte", "article": "Die", "plural": "Fahrkarten", "def": "Ticket für Bus oder Bahn."},
        {"word": "Gepäck", "article": "Das", "plural": "Gepäcke", "def": "Koffer und Taschen."},
        {"word": "Supermarkt", "article": "Der", "plural": "Supermärkte", "def": "Großes Geschäft."},
        {"word": "Kasse", "article": "Die", "plural": "Kassen", "def": "Wo man bezahlt."},
        {"word": "Rechnung", "article": "Die", "plural": "Rechnungen", "def": "Papier mit dem Preis."},
        {"word": "Geld", "article": "Das", "plural": "Gelder", "def": "Zum Bezahlen."},
        {"word": "Preis", "article": "Der", "plural": "Preise", "def": "Kosten für eine Ware."},
        {"word": "Angebot", "article": "Das", "plural": "Angebote", "def": "Günstige Ware."},
        # New Additions
        {"word": "Hotel", "article": "Das", "plural": "Hotels", "def": "Wo man im Urlaub schläft."},
        {"word": "Zimmer", "article": "Das", "plural": "Zimmer", "def": "Raum im Hotel."},
        {"word": "Schlüssel", "article": "Der", "plural": "Schlüssel", "def": "Öffnet die Tür."},
        {"word": "Koffer", "article": "Der", "plural": "Koffer", "def": "Für das Gepäck."},
        {"word": "Tasche", "article": "Die", "plural": "Taschen", "def": "Zum Tragen von Dingen."},
        {"word": "Pass", "article": "Der", "plural": "Pässe", "def": "Dokument für Reisen."},
        {"word": "Visum", "article": "Das", "plural": "Visa", "def": "Erlaubnis zur Einreise."},
        {"word": "Grenze", "article": "Die", "plural": "Grenzen", "def": "Linie zwischen Ländern."},
        {"word": "Zoll", "article": "Der", "plural": "Zölle", "def": "Kontrolle an der Grenze."},
        {"word": "Flug", "article": "Der", "plural": "Flüge", "def": "Reise mit dem Flugzeug."}
    ],
    "LEVEL_B1": [
        # Emotions, Abstract, Culture (B1) - Incorporating existing B1/Mia Kurs words
        {"word": "Gesundheit", "article": "Die", "plural": "Gesundheiten", "def": "Körperliches Wohlergehen."},
        {"word": "Krankheit", "article": "Die", "plural": "Krankheiten", "def": "Gegenteil von Gesundheit."},
        {"word": "Erfahrung", "article": "Die", "plural": "Erfahrungen", "def": "Was man im Leben lernt."},
        {"word": "Ergebnis", "article": "Das", "plural": "Ergebnisse", "def": "Das Resultat."},
        {"word": "Entscheidung", "article": "Die", "plural": "Entscheidungen", "def": "Die Wahl treffen."},
        {"word": "Freiheit", "article": "Die", "plural": "Freiheiten", "def": "Unabhängigkeit."},
        {"word": "Wahrheit", "article": "Die", "plural": "Wahrheiten", "def": "Das Richtige, Fakten."},
        {"word": "Meinung", "article": "Die", "plural": "Meinungen", "def": "Persönliche Ansicht."},
        {"word": "Vorteil", "article": "Der", "plural": "Vorteile", "def": "Etwas Gutes an einer Sache."},
        {"word": "Nachteil", "article": "Der", "plural": "Nachteile", "def": "Etwas Schlechtes an einer Sache."},
        {"word": "Zukunft", "article": "Die", "plural": "Zukünfte", "def": "Was noch kommt."},
        {"word": "Vergangenheit", "article": "Die", "plural": "Vergangenheiten", "def": "Was schon war."},
        {"word": "Umwelt", "article": "Die", "plural": "Umwelten", "def": "Natur und Umgebung."},
        {"word": "Gesellschaft", "article": "Die", "plural": "Gesellschaften", "def": "Gemeinschaft der Menschen."},
        {"word": "Kultur", "article": "Die", "plural": "Kulturen", "def": "Kunst und Traditionen."},
        # New Additions
        {"word": "Politik", "article": "Die", "plural": "Politiken", "def": "Staatsführung."},
        {"word": "Partei", "article": "Die", "plural": "Parteien", "def": "Politische Gruppe."},
        {"word": "Wahl", "article": "Die", "plural": "Wahlen", "def": "Abstimmung."},
        {"word": "Stimme", "article": "Die", "plural": "Stimmen", "def": "Beim Wählen oder Sprechen."},
        {"word": "Gesetz", "article": "Das", "plural": "Gesetze", "def": "Offizielle Regel."},
        {"word": "Recht", "article": "Das", "plural": "Rechte", "def": "Was einem zusteht."},
        {"word": "Staat", "article": "Der", "plural": "Staaten", "def": "Das Land als Organisation."},
        {"word": "Regierung", "article": "Die", "plural": "Regierungen", "def": "Die das Land führen."},
        {"word": "Präsident", "article": "Der", "plural": "Präsidenten", "def": "Staatsoberhaupt."},
        {"word": "Minister", "article": "Der", "plural": "Minister", "def": "Mitglied der Regierung."}
    ]
}

# --- GAME STATES ---
STATE_START_SCREEN = "START_SCREEN"
STATE_PREP = "PREP"          
STATE_QUESTION = "QUESTION"  
STATE_FEEDBACK = "FEEDBACK"  
STATE_RETRY = "RETRY"        
STATE_GAME_OVER = "GAME_OVER"
STATE_VICTORY = "VICTORY"
STATE_CONNECTING = "CONNECTING"
STATE_SPLASH = "SPLASH"
STATE_INTRO = "INTRO"

class GermanGame:
    def __init__(self):
        pygame.init()
        # Adjusted resolution to be smaller/safer
        self.width = 1024
        self.height = 768
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("German Article Learning")
        
        # Fonts
        self.font_s = pygame.font.SysFont("Arial", 20)
        self.font_m = pygame.font.SysFont("Arial", 32) 
        self.font_l = pygame.font.SysFont("Arial", 48, bold=True)
        self.font_xl = pygame.font.SysFont("Arial", 60, bold=True)

        # Game Logic
        self.state = STATE_CONNECTING # Start with connecting, then go to Start Screen
        self.selected_difficulty = None
        self.current_words = []
        self.word_queue = []
        self.target_word = None
        self.timer_start = 0
        self.feedback_message = ""
        self.feedback_color = (0, 0, 0)
        self.detected_color_code = None
        self.raw_color_code = None # For debug
        self.last_distance = 0 # For debug/logic
        self.wrong_attempts = 0
        self.score = 0
        self.questions_asked = 0
        self.completed_words = [] # Keep track of words done
        
        # Sensor Stability
        self.stable_color_start_time = 0
        self.last_stable_color = None
        self.last_logged_color = None # For debug logging
        
        # Hub
        self.hub = None
        self.is_connected = False
        
        # Start Screen Buttons
        cx = self.width // 2
        cy = self.height // 2
        # Defines 2 columns
        # Left Col: Klasse 1-3
        self.btn_k1 = pygame.Rect(cx - 320, cy - 100, 300, 60)
        self.btn_k2 = pygame.Rect(cx - 320, cy, 300, 60)
        self.btn_k3 = pygame.Rect(cx - 320, cy + 100, 300, 60)
        
        # Right Col: Level A1-B1
        self.btn_a1 = pygame.Rect(cx + 20, cy - 100, 300, 60)
        self.btn_a2 = pygame.Rect(cx + 20, cy, 300, 60)
        self.btn_b1 = pygame.Rect(cx + 20, cy + 100, 300, 60)
        
        # Load Splash Image
        try:
            self.splash_img = pygame.image.load('legolingo_splash.jpg')
            self.splash_img = pygame.transform.scale(self.splash_img, (self.width, self.height))
        except Exception as e:
            logging.error(f"Could not load splash image: {e}")
            self.splash_img = None
            
        # Load Kiomi Robot Assets
        try:
            self.kiomi_img = pygame.image.load('kiomi_robot.png')
            # Scale if too big, but let's assume it's okay or scale to fit nicely
            self.kiomi_img = pygame.transform.scale(self.kiomi_img, (400, 600))
        except Exception as e:
            logging.error(f"Could not load robot image: {e}")
            self.kiomi_img = None

        try:
            self.kiomi_sound = pygame.mixer.Sound('kiomi_intro.mp3')
        except Exception as e:
             logging.error(f"Could not load robot sound: {e}")
             self.kiomi_sound = None

        # Pre-generate feedback sounds
        try:
            self.sound_der = generate_guitar_note(392.00, 1.2) # G4 (Der - Blue)
            self.sound_die = generate_guitar_note(329.63, 1.2) # E4 (Die - Red)
            self.sound_das = generate_guitar_note(523.25, 1.2) # C5 (Das - Green)
            self.sound_wrong = generate_guitar_note(150.00, 0.8) # Low buzz (Wrong)
        except Exception as e:
            logging.error(f"Could not generate feedback sounds: {e}")
            self.sound_der = None
            self.sound_die = None
            self.sound_das = None
            self.sound_wrong = None

        self.splash_start = 0
        self.intro_start_time = 0
        self.intro_played = False

        # Initial check (will be updated by thread)
        if not self.is_connected:
            self.state = STATE_SPLASH
            self.splash_start = time.time()
        else:
            self.state = STATE_START_SCREEN

    def cleanup(self):
        if self.hub:
            logging.info("Disconnecting LEGO Hub...")
            try:
                self.hub.disconnect()
            except Exception as e:
                logging.error(f"Error during disconnect: {e}")


    def init_game(self):
        # Use selected difficulty pool, fallback to A1
        pool = WORD_POOLS.get(self.selected_difficulty, WORD_POOLS["LEVEL_A1"])
        
        # Select 10 words ensuring at least one of each article
        der = [w for w in pool if w['article'] == 'Der']
        die = [w for w in pool if w['article'] == 'Die']
        das = [w for w in pool if w['article'] == 'Das']
        
        selected = []
        # Try to get one of each, fallback if list is empty (shouldn't happen with current data)
        if der: selected.append(random.choice(der))
        if die: selected.append(random.choice(die))
        if das: selected.append(random.choice(das))
        
        remaining = [w for w in pool if w not in selected]
        
        # Fill up to 10
        needed = 10 - len(selected)
        if len(remaining) >= needed:
            selected.extend(random.sample(remaining, needed))
        else:
            selected.extend(remaining)
            
        random.shuffle(selected)
        
        self.current_words = selected
        self.word_queue = list(selected)
        random.shuffle(self.word_queue) # Shuffle queue so it's not in the same order as the list 
        self.completed_words = []
        self.score = 0
        self.questions_asked = 0
        self.wrong_attempts = 0 # Global counter for wrong attempts
        
        self.state = STATE_PREP
        self.timer_start = time.time()
        
        if self.hub:
            try: self.hub.led.set_color(0) 
            except: pass

    def next_question(self):
        if not self.word_queue:
            self.state = STATE_VICTORY
            return

        self.target_word = self.word_queue.pop(0)
        self.questions_asked += 1
        self.state = STATE_QUESTION
        self.timer_start = time.time()
        self.detected_color_code = None
        # self.wrong_attempts is NOT reset here anymore
        
        # Reset stability
        self.stable_color_start_time = 0
        self.last_stable_color = None
        
        if self.hub:
            try: self.hub.led.set_color(0) 
            except: pass

    def handle_input(self, color_code, distance=None):
        self.detected_color_code = color_code
        if distance is not None:
            self.last_distance = distance

        # RESET STABILITY if color is None (0) or Unknown (255)
        if color_code in [0, 255]:
            self.stable_color_start_time = 0
            self.last_stable_color = None
            return

        # RESTART LOGIC (Only in GAME OVER)
        if self.state == STATE_GAME_OVER or self.state == STATE_VICTORY:
            # Check for RED (9) to restart
            if color_code == 9:
                 self.init_game() # Restarts with SAME difficulty
            return

        if self.state in [STATE_FEEDBACK, STATE_START_SCREEN, STATE_CONNECTING, STATE_INTRO]:
            return
        
        # DISTANCE CHECK (Ignore if too far, increased to 8 to avoid drops)
        if distance is not None and distance > 8:
            # Also reset stability if too far!
            self.stable_color_start_time = 0
            self.last_stable_color = None
            return

        # STABILITY CHECK (Hold for 0.1s)
        if color_code == self.last_stable_color:
            if time.time() - self.stable_color_start_time < 0.1: 
                return # Not stable enough yet
        else:
            self.last_stable_color = color_code
            self.stable_color_start_time = time.time()
            return # Wait for stability

        if self.state == STATE_QUESTION:
            target_article = self.target_word['article']
            target_color_code = ARTICLES[target_article]['color_code']
            
            detected_article = None
            for art, data in ARTICLES.items():
                if data['color_code'] == color_code:
                    detected_article = art
                    break
            
            if not detected_article:
                return 
            
            if color_code == target_color_code:
                # CORRECT
                self.state = STATE_FEEDBACK
                self.score += 1
                self.completed_words.append(self.target_word)
                self.feedback_message = "Richtig!"
                self.feedback_color = (50, 200, 50) 
                self.timer_start = time.time()
                if self.hub: self.hub.led.set_color(5) 
                
                # Play correct gender sound
                art = self.target_word['article']
                if art == "Der" and self.sound_der: self.sound_der.play()
                elif art == "Die" and self.sound_die: self.sound_die.play()
                elif art == "Das" and self.sound_das: self.sound_das.play()
            else:
                # WRONG
                self.wrong_attempts += 1
                if self.hub: self.hub.led.set_color(9) 
                
                # Play wrong sound
                if self.sound_wrong: self.sound_wrong.play()
                
                if self.wrong_attempts >= 2:
                    # GAME OVER - 2 Versuche vorbei (Global)
                    self.state = STATE_GAME_OVER
                    self.feedback_message = f"Es ist vorbei"
                    self.feedback_color = (255, 50, 50)
                    self.timer_start = time.time()
                else:
                    # Show FALSCH and move on
                    self.state = STATE_FEEDBACK
                    self.feedback_message = "Falsch!"
                    self.feedback_color = (255, 50, 50) 
                    self.timer_start = time.time() 

    def update(self):
        current_time = time.time()
        
        if self.state == STATE_SPLASH:
            if current_time - self.splash_start > 3.0:
                self.state = STATE_CONNECTING

        elif self.state == STATE_CONNECTING:
            if self.is_connected:

                self.state = STATE_INTRO
                self.intro_played = False
                
        elif self.state == STATE_INTRO:
            if not self.intro_played:
                try:
                    if self.kiomi_sound: self.kiomi_sound.play()
                except:
                    pass
                self.intro_played = True
                self.intro_start_time = current_time
            
            # Duration check (audio length + buffer)
            duration = 7.0 
            if self.kiomi_sound:
                duration = self.kiomi_sound.get_length() + 1.0
            
            if current_time - self.intro_start_time > duration:
                self.state = STATE_START_SCREEN
                
        elif self.state == STATE_PREP:
            # 4 seconds prep
            if current_time - self.timer_start > 4.0:
                self.next_question()
                
        elif self.state == STATE_QUESTION:
            # TIMEOUT CHECK (15 seconds)
            if current_time - self.timer_start > 15.0:
                self.wrong_attempts += 1
                if self.wrong_attempts >= 2:
                    self.state = STATE_GAME_OVER
                    self.feedback_message = "Es ist vorbei"
                    self.feedback_color = (255, 50, 50)
                else:
                    self.state = STATE_FEEDBACK
                    self.feedback_message = "Zu langsam!"
                    self.feedback_color = (255, 180, 0)
                self.timer_start = time.time()
                
        elif self.state == STATE_FEEDBACK:
            if current_time - self.timer_start > 4.0:
                self.next_question()
                
        elif self.state == STATE_VICTORY:
            if current_time - self.timer_start > 15.0:
                self.init_game()

    def draw_text_centered(self, text, font, color, center_y, bg_color=None):
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(self.width // 2, center_y))
        if bg_color:
            pygame.draw.rect(self.screen, bg_color, rect.inflate(20, 10))
        self.screen.blit(surf, rect)

    def draw_start_screen(self):
        # Background is drawn in draw()
        
        self.draw_text_centered("Wähle deine Stufe", self.font_xl, (0, 0, 0), 150)
        
        # Draw Buttons
        mouse_pos = pygame.mouse.get_pos()
        
        buttons = [
            (self.btn_k1, "1. Klasse", "KLASSE_1"),
            (self.btn_k2, "2. Klasse", "KLASSE_2"),
            (self.btn_k3, "3. Klasse", "KLASSE_3"),
            (self.btn_a1, "Level A1", "LEVEL_A1"),
            (self.btn_a2, "Level A2", "LEVEL_A2"),
            (self.btn_b1, "Level B1", "LEVEL_B1")
        ]
        
        for btn, text, key in buttons:
            color = (200, 200, 200)
            if btn.collidepoint(mouse_pos):
                color = (150, 200, 255)
            
            pygame.draw.rect(self.screen, color, btn, border_radius=10)
            pygame.draw.rect(self.screen, (100, 100, 100), btn, 2, border_radius=10)
            
            text_surf = self.font_m.render(text, True, (0, 0, 0))
            self.screen.blit(text_surf, text_surf.get_rect(center=btn.center))

    def draw_intro(self):
         cx, cy = self.width // 2, self.height // 2
         
         # Draw Robot
         if self.kiomi_img:
             rect = self.kiomi_img.get_rect(center=(cx, cy))
             self.screen.blit(self.kiomi_img, rect)
             
         # Draw Speech Bubble (Text)
         # Simple visual box
         bubble_rect = pygame.Rect(cx - 400, cy + 150, 800, 150)
         pygame.draw.rect(self.screen, (255, 255, 255), bubble_rect, border_radius=20)
         pygame.draw.rect(self.screen, (0, 0, 0), bubble_rect, 2, border_radius=20)
         
         self.draw_text_centered("Ich bin Kiomi.", self.font_l, (0, 0, 0), cy + 180)
         self.draw_text_centered("Seid ihr bereit, die Artikel zu üben?", self.font_m, (0, 0, 0), cy + 240)



    def draw(self):
        # SPLASH
        if self.state == STATE_SPLASH:
            if self.splash_img:
                self.screen.blit(self.splash_img, (0, 0))
            else:
                self.screen.fill((255, 255, 255))
            pygame.display.flip()
            return

        # BACKGROUND
        if self.splash_img:
            self.screen.blit(self.splash_img, (0, 0))
            # Draw central panel
            margin = 40
            panel_rect = pygame.Rect(margin, margin, self.width - 2*margin, self.height - 2*margin)
            pygame.draw.rect(self.screen, (255, 255, 255), panel_rect, border_radius=20)
            # Add a subtle border to the panel
            pygame.draw.rect(self.screen, (200, 200, 200), panel_rect, 2, border_radius=20)
        else:
            self.screen.fill((255, 255, 255))

        if self.state == STATE_START_SCREEN:
            self.draw_start_screen()
            pygame.display.flip()
            return

        if self.state == STATE_INTRO:
            self.draw_intro()
            pygame.display.flip()
            return
        
        cx, cy = self.width // 2, self.height // 2
        
        # Header Status
        status_text = f"Frage: {self.questions_asked}/10 | Punkte: {self.score} | Fehler: {self.wrong_attempts}/2"
        if not self.is_connected: status_text += " | SEARCHING FOR LEGO..."
        self.screen.blit(self.font_s.render(status_text, True, (100, 100, 100)), (60, 60))

        # --- WORD LIST ---
        col1_x = self.width // 4
        col2_x = 3 * self.width // 4
        start_y = 120
        
        for i, word in enumerate(self.current_words):
            color = (50, 50, 50) 
            
            # Logic: 
            # - If word is completed: Gray
            # - If word is current AND we are in Feedback/GameOver: Green/Red
            # - Otherwise (Question/Retry/Prep): Black (No hint!)
            
            if word in self.completed_words:
                 # Completed words stay visible but no special marking
                 color = (0, 0, 0) 
            elif word == self.target_word and self.state in [STATE_FEEDBACK, STATE_GAME_OVER]:
                 color = (0, 180, 0) if self.state == STATE_FEEDBACK and self.feedback_message == "Richtig!" else (200, 0, 0)
            
            text = self.font_m.render(f"{word['word']}", True, color)
            if i < 5:
                self.screen.blit(text, text.get_rect(center=(col1_x, start_y + i * 40)))
            else:
                self.screen.blit(text, text.get_rect(center=(col2_x, start_y + (i-5) * 40)))

        # --- CONTENT ---
        content_y = 420 # Moved down to avoid overlap with word list
        
        if self.state == STATE_CONNECTING:
            self.draw_text_centered("Verbinde mit LEGO Hub...", self.font_xl, (0, 0, 0), content_y - 50)
            self.draw_text_centered("Bitte grünen Knopf am Hub drücken!", self.font_l, (100, 100, 100), content_y + 50)
            
            # Pulsing effect
            elapsed = time.time()
            if int(elapsed * 2) % 2 == 0:
                 self.draw_text_centered("Suche...", self.font_m, (200, 0, 0), content_y + 150)
            
            self.draw_text_centered("(Drücke 'S' um ohne LEGO zu testen)", self.font_s, (150, 150, 150), content_y + 250)
        
        elif self.state == STATE_PREP:
            self.draw_text_centered("Merke dir die Wörter!", self.font_l, (0, 0, 0), content_y)
            elapsed = time.time() - self.timer_start
            bar_width = int((1 - elapsed/5.0) * 600)
            pygame.draw.rect(self.screen, (100, 150, 255), (cx - 300, 450, bar_width, 20))

        elif self.state == STATE_QUESTION:
            self.draw_text_centered("Welches Wort ist das?", self.font_l, (0, 0, 150), content_y - 80)
            
            # Definition
            def_words = self.target_word['def'].split()
            lines = []
            curr_line = ""
            for w in def_words:
                if len(curr_line) + len(w) > 35:
                    lines.append(curr_line)
                    curr_line = w + " "
                else:
                    curr_line += w + " "
            lines.append(curr_line)
            
            for i, line in enumerate(lines):
                self.draw_text_centered(line, self.font_xl, (0, 0, 0), content_y + i * 60)
            
            # Timer
            if self.state == STATE_QUESTION:
                elapsed = time.time() - self.timer_start
                remaining = max(0, 15.0 - elapsed)
                color = (0, 180, 0) if remaining > 3 else (200, 0, 0)
                self.draw_text_centered(f"{remaining:.1f}s", self.font_xl, color, content_y + 180)

            self.draw_text_centered("Zeige die Farbe!", self.font_m, (150, 150, 150), content_y + 230)
                
            if not self.is_connected:
                hint = self.font_s.render("(Tastatur: R=Rot, B=Blau, G=Grün)", True, (150, 150, 150))
                self.screen.blit(hint, hint.get_rect(center=(cx, self.height - 100)))

        elif self.state == STATE_FEEDBACK:
            self.draw_text_centered(self.feedback_message, self.font_xl, self.feedback_color, content_y - 50)
            
            card_h = 220
            card_rect = pygame.Rect(cx - 300, content_y + 20, 600, card_h)
            pygame.draw.rect(self.screen, (240, 240, 250), card_rect, border_radius=15)
            pygame.draw.rect(self.screen, self.feedback_color, card_rect, 3, border_radius=15)
            
            art = self.target_word['article']
            word = self.target_word['word']
            plural = self.target_word['plural']
            
            # Fetch gender color
            gender_color = ARTICLES.get(art, {"rgb": (0, 0, 0)})["rgb"]
            
            # Try to load custom image
            img_path = get_word_image_path(word)
            word_image = None
            if os.path.exists(img_path):
                try:
                    word_image = pygame.image.load(img_path)
                    word_image = pygame.transform.scale(word_image, (140, 140))
                except Exception as e:
                    logging.error(f"Error loading image {img_path}: {e}")
            
            # Draw visual asset (either custom image or 3D Lego brick) on the left side of the card
            asset_x = cx - 260
            asset_y = content_y + 20 + (card_h - 140) // 2
            
            if word_image:
                self.screen.blit(word_image, (asset_x, asset_y))
            else:
                draw_lego_brick(self.screen, asset_x + 10, asset_y + 35, gender_color, size=(120, 70))
            
            # Draw Word & Plural on the right side of the card
            text_area_cx = cx + 80
            
            full_word_surf = self.font_xl.render(f"{art} {word}", True, gender_color)
            self.screen.blit(full_word_surf, full_word_surf.get_rect(center=(text_area_cx, content_y + 85)))
            
            plural_surf = self.font_l.render(f"Die {plural}", True, (100, 100, 100))
            self.screen.blit(plural_surf, plural_surf.get_rect(center=(text_area_cx, content_y + 155)))

        elif self.state == STATE_GAME_OVER or self.state == STATE_VICTORY:
            title = "SPIEL VORBEI" if self.state == STATE_GAME_OVER else "GEWONNEN!"
            color = (200, 0, 0) if self.state == STATE_GAME_OVER else (0, 180, 0)
            
            self.draw_text_centered(title, self.font_xl, color, content_y - 80)
            
            score_text = f"Ergebnis: {self.score} von 10"
            self.draw_text_centered(score_text, self.font_xl, (0, 0, 0), content_y)
            
            if self.state == STATE_GAME_OVER:
                self.draw_text_centered(f"Letztes Wort: {self.target_word['article']} {self.target_word['word']}", self.font_l, (100, 100, 100), content_y + 80)
            
            self.draw_text_centered("Zum Neustart ROT halten!", self.font_m, (150, 150, 150), content_y + 180)
            
            # Add option to go back to menu? For now just restart same difficulty.
            self.draw_text_centered("(Oder 'M' für Menü)", self.font_s, (100, 100, 100), content_y + 220)

        # --- DEBUG SENSOR ---
        debug_info = []
        if self.raw_color_code is not None:
            debug_info.append(f"Raw: {self.raw_color_code}")
        if self.detected_color_code is not None:
            debug_info.append(f"Stable: {self.detected_color_code}")
        debug_info.append(f"Dist: {self.last_distance}")
        
        if debug_info:
             debug_text = " | ".join(debug_info)
             self.screen.blit(self.font_s.render(debug_text, True, (200, 200, 200)), (60, self.height - 70))

        # --- LEGEND (BOTTOM) ---
        legend_y = self.height - 80
        pygame.draw.rect(self.screen, ARTICLES["Die"]["rgb"], (cx - 250, legend_y, 100, 30), border_radius=5)
        self.screen.blit(self.font_s.render("Die (Rot)", True, (255,255,255)), (cx - 240, legend_y + 5))
        pygame.draw.rect(self.screen, ARTICLES["Der"]["rgb"], (cx - 50, legend_y, 100, 30), border_radius=5)
        self.screen.blit(self.font_s.render("Der (Blau)", True, (255,255,255)), (cx - 40, legend_y + 5))
        pygame.draw.rect(self.screen, ARTICLES["Das"]["rgb"], (cx + 150, legend_y, 100, 30), border_radius=5)
        self.screen.blit(self.font_s.render("Das (Grün)", True, (0,0,0)), (cx + 160, legend_y + 5))

        pygame.display.flip()

# --- GLOBAL GAME INSTANCE ---
game = None

def sensor_callback(color, distance):
    global game
    if game:
        # Log if color changed
        if color != game.last_logged_color:
             color_name = "UNKNOWN"
             if color == 9: color_name = "RED"
             elif color == 3: color_name = "BLUE"
             elif color == 5: color_name = "GREEN"
             elif color == 0: color_name = "NONE"
             
             logging.info(f"Sensor Detected: {color} ({color_name}) | Dist: {distance}")
             game.last_logged_color = color

        game.raw_color_code = color
        game.handle_input(color, distance)

def boost_thread():
    global game
    while True:
        try:
            logging.info(f"Searching for LEGO Hub ({LEGO_MAC_ADRESI})... Please turn it on (Green Button).")
            if game: game.is_connected = False
            
            connection = get_connection_auto(hub_mac=LEGO_MAC_ADRESI)
            hub = MoveHub(connection)
            
            if game:
                game.hub = hub
                game.is_connected = True
            
            logging.info("LEGO HUB CONNECTED! Light should turn off.")
            hub.led.set_color(0) 
            
            hub.vision_sensor.subscribe(sensor_callback)
            logging.info("Sensor subscribed.")
            
            while True:
                time.sleep(1)
                if not connection.is_alive: 
                    logging.warning("Connection lost.")
                    break
                    
        except Exception as e:
            logging.error(f"Connection failed or lost: {e}")
            if game: game.is_connected = False
            time.sleep(2) 
            
def main():
    global game
    game = GermanGame()
    
    t = threading.Thread(target=boost_thread, daemon=True)
    t.start()
    
    clock = pygame.time.Clock()
    running = True
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_r: game.handle_input(9) 
                if event.key == pygame.K_g: game.handle_input(5) 
                if event.key == pygame.K_b: game.handle_input(3) 
                
                # Back to menu shortcut
                if event.key == pygame.K_m and game.state in [STATE_GAME_OVER, STATE_VICTORY]:
                    game.state = STATE_START_SCREEN
                
                # Skip connection
                if event.key == pygame.K_s and game.state == STATE_CONNECTING:
                    game.state = STATE_INTRO
                    game.intro_played = False
                    game.intro_start_time = time.time()
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                if game.state == STATE_START_SCREEN:
                    mouse_pos = event.pos
                    if game.btn_k1.collidepoint(mouse_pos):
                        game.selected_difficulty = "KLASSE_1"
                        game.init_game()
                    elif game.btn_k2.collidepoint(mouse_pos):
                        game.selected_difficulty = "KLASSE_2"
                        game.init_game()
                    elif game.btn_k3.collidepoint(mouse_pos):
                        game.selected_difficulty = "KLASSE_3"
                        game.init_game()
                    elif game.btn_a1.collidepoint(mouse_pos):
                        game.selected_difficulty = "LEVEL_A1"
                        game.init_game()
                    elif game.btn_a2.collidepoint(mouse_pos):
                        game.selected_difficulty = "LEVEL_A2"
                        game.init_game()
                    elif game.btn_b1.collidepoint(mouse_pos):
                        game.selected_difficulty = "LEVEL_B1"
                        game.init_game()
        
        game.update()
        game.draw()
        clock.tick(60)
        
        clock.tick(60)
    
    if game: game.cleanup()
    pygame.quit()

if __name__ == "__main__":
    main()
