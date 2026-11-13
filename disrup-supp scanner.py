"""Big rooms are told apart from three EE.log signals written while the mission loads:
  1. 'Using: ... as backdrop for /LayerZ/CsgZoneN': each big room lists its own set of CsgZones,
     and Z is the room slot.
  2. 'HighLevelGraph setup B implicit bridges for zone Z': separates rooms with the same CsgZone set.
  3. 'Replication count by concrete type' table, written only by the host: TerritoryTrigger and
     ComputerActivateSeq counts separate the remaining pairs.
"""
import os
import re
import sys
import time
import threading
import tkinter as tk

STOP_FLAG = threading.Event()

OVERLAY_DATA = {
    'status': 'Waiting for map...',
    'rooms': [],
    'color': 'yellow',
}

OROKIN_SIGS = {
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9): 'X',
    (0, 1, 2, 3, 4, 5, 6, 7, 8): 'X',
    (0, 1, 2, 3, 4): 'arch',
    (0, 1, 2, 3, 4, 5, 6): 'auditorium|fountain',
    (0, 1, 2, 3, 4, 5): 'elevator',
    (0, 1, 3, 4, 6, 8): 'football',
    (0, 1, 2): 'ramp',
    (0, 1): 'ramp',
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11): 'tree',
}
GALLEON_SIGS = {
    (0, 1, 2, 5, 6, 7): 'reactor',
    (0, 1, 2, 3, 4, 5): 'hangar',
    (0, 1, 2): 'pain|triangle',
    (0, 1): 'planets|square',
}
GALLEON_SURVIVAL_SIGS = dict(GALLEON_SIGS)
GALLEON_SURVIVAL_SIGS.update({
    (0, 1, 2, 3, 4): 'junction|computer',
    # 1076-object room never found in game; presumed stairs, the one listed room not seen elsewhere
    (0, 1, 2, 3): 'stairs',
})
DERELICT_SIGS = {
    (0,): 'elevator',
    (0, 1, 2, 3): 'tree',
    (0, 1, 2): 'pipes|bridge',
}
TERRITORY = {'hangar': 2, 'reactor': 2, 'square': 2, 'triangle': 1, 'pain': 0, 'planets': 0,
             'junction': 2, 'computer': 0, 'stairs': 2}

TILESETS = [
    ('OrokinTowerSurvival', 'Orokin Survival', (2, 6, 8), OROKIN_SIGS),
    ('GrineerGalleonDisruption', 'Galleon Disruption', (4, 8), GALLEON_SIGS),
    ('GrineerGalleonSurvival', 'Galleon Survival', (2, 6, 8), GALLEON_SURVIVAL_SIGS),
    ('OrokinTowerDerelictSurvival', 'Derelict Survival', (2, 9, 13), DERELICT_SIGS),
]

TIERS = {
    'elevator': 'best', 'tree': 'best', 'auditorium': 'best', 'football': 'best',
    'arch': 'good', 'fountain': 'good',
    'X': 'avoid',
    'reactor': 'best', 'hangar': 'best', 'planets': 'best',
    'square': 'good', 'pain': 'good',
    'stairs': 'avoid', 'triangle': 'avoid', 'junction': 'avoid', 'computer': 'avoid',
    'bridge': 'best', 'pipes': 'good',
}

# HighLevelGraph lines come about 0.1 s after the replication table; wait this long before deciding
SETTLE_SECONDS = 2.0


def new_mission(level):
    return {'level': level, 'csg': {}, 'graph': {}, 'rep': {}, 'table': 'none', 'table_time': None}


def decode(mission):
    for fragment, name, zones, sigs in TILESETS:
        if fragment in mission['level']:
            break
    else:
        return None

    rooms = {}
    for z in zones:
        seen = mission['csg'].get(z, set())
        room = '?'
        if seen:
            # Nearest known signature; a room can list one backdrop zone more or less
            best = max(sigs, key=lambda k: len(seen & set(k)) / len(seen | set(k)))
            if len(seen & set(best)) / len(seen | set(best)) >= 0.75:
                room = sigs[best]
        bridges = mission['graph'].get(z)
        if room == 'auditorium|fountain':
            room = 'fountain' if bridges == 31 else 'auditorium'
        elif room == 'pain|triangle':
            room = 'pain' if bridges == 114 else 'triangle'
        elif room == 'pipes|bridge':
            room = 'bridge' if bridges == 52 else 'pipes'
        rooms[z] = room

    # Junction is the only room with a hackable computer (ComputerActivateSeq in the table)
    unsure = [z for z, r in rooms.items() if r == 'junction|computer']
    if unsure and mission['table'] == 'done':
        junctions = mission['rep'].get('/Lotus/Sounds/Objects/Computer/ComputerActivateSeq', 0)
        assign(rooms, unsure, junctions, 'junction', 'computer')

    unsure = [z for z, r in rooms.items() if r == 'planets|square']
    # The table leaves out types with no objects, so a missing TerritoryTrigger means 0
    territory = mission['rep'].get('/Lotus/Types/Game/TerritoryTrigger', 0)
    if unsure and mission['table'] == 'done':
        extra = territory - sum(TERRITORY.get(r, 0) for z, r in rooms.items() if z not in unsure)
        assign(rooms, unsure, extra // 2, 'square', 'planets')
    return name, [rooms[z].replace('|', '/') for z in zones]


def assign(rooms, zones, count, a, b):
    """The table gives how many zones are room a, not which ones; a mixed result is marked '?'."""
    count = max(0, min(count, len(zones)))
    mixed = 0 < count < len(zones)
    for i, z in enumerate(zones):
        rooms[z] = (a if i < count else b) + ('?' if mixed else '')


def show(tileset, rooms):
    tiers = [TIERS.get(r.rstrip('?')) for r in rooms]
    if '?' in rooms:
        status, color = f'{tileset}: unknown room', 'yellow'
    elif 'avoid' in tiers:
        status, color = f'{tileset}: AVOID', 'red'
    else:
        status, color = f'{tileset}: {tiers.count("best")} best', 'green'
    OVERLAY_DATA.update({'status': status, 'rooms': list(zip(rooms, tiers)), 'color': color})

    print('\n====================================')
    print(status)
    print('Rooms: ' + ', '.join(f'{r} [{t}]' if t else r for r, t in zip(rooms, tiers)))
    print('====================================')


class LogReader:
    def __init__(self, path):
        self.path = path
        self.pos = 0
        self.partial = ''
        self.mission = None
        self.shown = False

    def feed(self, line):
        if 'ServerFramework:OpenLevel - ' in line:
            self.mission = new_mission(line.split(' - ', 1)[1].strip())
            self.shown = False
            return
        m = self.mission
        if m is None:
            return
        g = re.search(r'as backdrop for /Layer(\d+)/CsgZone(\d+)', line)
        if g:
            m['csg'].setdefault(int(g[1]), set()).add(int(g[2]))
            return
        g = re.search(r'HighLevelGraph setup (\d+) implicit bridges for zone (\d+)', line)
        if g:
            m['graph'][int(g[2])] = int(g[1])
            return
        if m['table'] == 'none' and 'Replication count by concrete type' in line:
            m['table'] = 'reading'
        elif m['table'] == 'reading':
            g = re.match(r'\S+ Net \[Info\]:\s+(\d+) (/\S+)$', line)
            if g:
                m['rep'][g[2]] = int(g[1])
            elif not re.match(r'\S+ Net \[Info\]:\s*$', line):
                m['table'] = 'done'
                m['table_time'] = time.monotonic()

    def poll(self, catching_up=False):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return
        if size < self.pos:
            # The game restarted and EE.log was rewritten
            self.pos, self.partial, self.mission = 0, '', None
        if size > self.pos:
            with open(self.path, 'r', encoding='latin1') as f:
                f.seek(self.pos)
                data = self.partial + f.read(size - self.pos)
            self.pos = size
            lines = data.split('\n')
            self.partial = lines.pop()
            for line in lines:
                self.feed(line)

        m = self.mission
        if m and not self.shown and m['table'] == 'done' and (
                catching_up or time.monotonic() - m['table_time'] >= SETTLE_SECONDS):
            self.shown = True
            result = decode(m)
            if result:
                show(*result)
            else:
                OVERLAY_DATA.update({'status': 'Waiting for map...', 'rooms': [], 'color': 'yellow'})


def get_warframe_log_path(filename: str) -> str | None:
    if sys.platform == 'win32':
        local_appdata = os.getenv('LOCALAPPDATA')
        if not local_appdata:
            return None
        return os.path.join(local_appdata, 'Warframe', filename)

    steam_roots = [
        os.path.expanduser('~/.steam/steam'),
        os.path.expanduser('~/.local/share/Steam'),
    ]
    rel = os.path.join(
        'steamapps', 'compatdata', '230410',
        'pfx', 'drive_c', 'users', 'steamuser',
        'AppData', 'Local', 'Warframe', filename,
    )
    for root in steam_roots:
        path = os.path.join(root, rel)
        if os.path.exists(path):
            return path
    return None


def tail_log(reader: LogReader, interval: float = 0.5):
    print('\nPress ENTER to stop the program.\n')
    while not STOP_FLAG.is_set():
        try:
            reader.poll()
        except Exception as e:
            print(f'Error reading the log: {e}')
        time.sleep(interval)


def keypress_listener(stop_event: threading.Event):
    try:
        sys.stdin.readline()
    except Exception:
        pass
    print('\nStopping...')
    stop_event.set()


class OverlayApp(tk.Tk):
    _BG      = '#111111'
    _FG_DIM  = '#94a3b8'
    _PALETTE = {'green': '#22c55e', 'red': '#ef4444', 'yellow': '#f59e0b'}
    _TIER_FG = {'best': '#22c55e', 'good': '#60a5fa', 'avoid': '#ef4444'}

    def __init__(self, stop_event):
        super().__init__()
        self.stop_event = stop_event

        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.attributes('-alpha', 0.92)
        self.configure(bg=self._BG)

        sw = self.winfo_screenwidth()
        w, h = 480, 64
        self.geometry(f'{w}x{h}+{sw // 2 - w // 2}+14')

        self.bind('<ButtonPress-1>', self._drag_start)
        self.bind('<B1-Motion>',     self._drag_motion)

        self.accent = tk.Frame(self, bg=self._PALETTE['yellow'], width=4)
        self.accent.pack(side='left', fill='y')
        self.accent.pack_propagate(False)

        content = tk.Frame(self, bg=self._BG)
        content.pack(side='left', fill='both', expand=True, padx=(12, 14), pady=9)

        self.status_label = tk.Label(
            content, text='Waiting for map...', font=('Helvetica', 12, 'bold'),
            fg=self._PALETTE['yellow'], bg=self._BG, anchor='w',
        )
        self.status_label.pack(fill='x')

        self.rooms_frame = tk.Frame(content, bg=self._BG)
        self.rooms_frame.pack(fill='x', pady=(2, 0))
        self._shown = None

        self.update_ui()
        self.after(500, self.periodic_check)

    def _drag_start(self, event):
        self._ox = event.x_root - self.winfo_x()
        self._oy = event.y_root - self.winfo_y()

    def _drag_motion(self, event):
        self.geometry(f'+{event.x_root - self._ox}+{event.y_root - self._oy}')

    def periodic_check(self):
        if self.stop_event.is_set():
            self.destroy()
            return
        self.update_ui()
        self.after(500, self.periodic_check)

    def update_ui(self):
        state = (OVERLAY_DATA['status'], tuple(OVERLAY_DATA['rooms']), OVERLAY_DATA['color'])
        if state == self._shown:
            return
        self._shown = state

        color = self._PALETTE[OVERLAY_DATA['color']]
        self.accent.configure(bg=color)
        self.status_label.configure(text=OVERLAY_DATA['status'], fg=color)

        for child in self.rooms_frame.winfo_children():
            child.destroy()
        if not OVERLAY_DATA['rooms']:
            tk.Label(self.rooms_frame, text='-', font=('Helvetica', 10),
                     fg=self._FG_DIM, bg=self._BG).pack(side='left')
        for room, tier in OVERLAY_DATA['rooms']:
            tk.Label(self.rooms_frame, text=room, font=('Helvetica', 10, 'bold'),
                     fg=self._TIER_FG.get(tier, self._FG_DIM), bg=self._BG).pack(side='left', padx=(0, 14))


def start_overlay(stop_event):
    try:
        OverlayApp(stop_event).mainloop()
    except Exception as e:
        print(f'\nOverlay failed to start/run: {e}')
        stop_event.set()


def main():
    path = get_warframe_log_path('EE.log')
    if not path or not os.path.exists(path):
        print(f'EE.log not found: {path}')
        return

    # Read what is already in the log, so a mission that is already loaded shows right away
    reader = LogReader(path)
    reader.poll(catching_up=True)

    threading.Thread(target=keypress_listener, args=(STOP_FLAG,), daemon=True).start()
    log_thread = threading.Thread(target=tail_log, args=(reader,), daemon=True)
    log_thread.start()

    start_overlay(STOP_FLAG)
    STOP_FLAG.set()
    log_thread.join(timeout=1)
    print('Program ended.')


if __name__ == '__main__':
    main()
