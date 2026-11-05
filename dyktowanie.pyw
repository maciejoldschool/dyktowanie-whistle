# Dyktowanie Whistle — nakladka dla Windows (ARM64 i x64)
#
# Przytrzymaj klawisze (domyslnie LEWY Ctrl + LEWY Shift) -> nagrywa
# Pusc                                                   -> tekst zostanie wklejony tam, gdzie stoi kursor
# Nacisniecie innego klawisza w trakcie (np. Ctrl+Shift+T) anuluje nagranie,
# wiec zwykle skroty dzialaja dalej normalnie.
#
# Ustawienia sa w pliku ustawienia.txt obok programu (tworzy sie przy pierwszym starcie).
# Wszystko dziala lokalnie: dzwiek nie opuszcza komputera.

import configparser
import ctypes
import os
import queue
import sys
import threading
import time
import traceback

APP = "Dyktowanie"
SR = 16000


def app_dir():
    """Folder programu (obok .exe albo skryptu); jesli nie da sie w nim pisac — %APPDATA%\\Dyktowanie."""
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    try:
        probe = os.path.join(base, ".zapis_test")
        open(probe, "w").close()
        os.remove(probe)
        return base
    except OSError:
        alt = os.path.join(os.environ.get("APPDATA", base), APP)
        os.makedirs(alt, exist_ok=True)
        return alt


HERE = app_dir()
LOG = open(os.path.join(HERE, "dyktowanie.log"), "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = LOG  # bez konsoli


def log(msg):
    print(time.strftime("%H:%M:%S"), msg)


def message_box(text, icon=0x40):
    ctypes.windll.user32.MessageBoxW(None, text, "Dyktowanie", icon)


if "--test" in sys.argv:
    # Samotest (uzywany przy budowaniu): czy paczka ma wszystko i silnik dziala na tym procesorze.
    try:
        import platform
        import tkinter, keyboard, sounddevice  # noqa: F401
        import numpy as np
        import needle
        r = needle.transcribe(np.zeros(SR, np.float32), language="pl")
        log(f"TEST OK {platform.machine()} needle {needle.__version__} {r}")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        log("TEST FAIL\n" + traceback.format_exc())
        sys.exit(1)


# ---------------- USTAWIENIA ----------------
DEFAULT_SETTINGS = """\
[dyktowanie]
# Jezyk mowy: pl, en, de, fr, es, it, nl albo auto (rozpozna sam)
jezyk = pl

# Klawisze do przytrzymania podczas mowienia, polaczone plusem.
# Mozliwe: lewy_ctrl, prawy_ctrl, lewy_shift, prawy_shift, lewy_alt
# Przyklady: lewy_ctrl + lewy_shift   albo samo   prawy_ctrl
klawisze = lewy_ctrl + lewy_shift

# Nazwy wlasne, ktore program ma lepiej rozpoznawac, oddzielone przecinkami.
# Przyklad: slowa = Krzysztof, ComfyUI, Blender
slowa =

# Dodawac spacje po wklejonym tekscie, zeby kolejne dyktowania sie nie sklejaly (tak / nie)
spacja_na_koncu = tak

# Po wklejeniu przywrocic poprzednia zawartosc schowka (tak / nie)
przywracaj_schowek = tak

# Anonimowe statystyki uzycia biblioteki Whistle: tylko nazwa funkcji, wersja i system,
# nigdy nagrania ani tekst (tak / nie)
statystyki = tak
"""

KEY_LABELS = {
    "lewy_ctrl": "lewy Ctrl", "prawy_ctrl": "prawy Ctrl",
    "lewy_shift": "lewy Shift", "prawy_shift": "prawy Shift",
    "lewy_alt": "lewy Alt",
}
LANGS = ("pl", "en", "de", "fr", "es", "it", "nl")


def load_settings():
    path = os.path.join(HERE, "ustawienia.txt")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_SETTINGS)
    cp = configparser.ConfigParser(comment_prefixes=("#", ";"), inline_comment_prefixes=None)
    cp.read_string(DEFAULT_SETTINGS)
    with open(path, encoding="utf-8-sig") as f:
        cp.read_file(f)
    s = cp["dyktowanie"]

    def yes(name):
        return s.get(name, "tak").strip().lower() in ("tak", "t", "yes", "y", "1", "true")

    lang = s.get("jezyk", "pl").strip().lower()
    if lang == "auto":
        lang = None
    elif lang not in LANGS:
        raise ValueError(f"jezyk = {lang} — dozwolone: {', '.join(LANGS)} albo auto")
    keys = [k.strip().lower() for k in s.get("klawisze", "").split("+") if k.strip()]
    bad = [k for k in keys if k not in KEY_LABELS]
    if not keys or bad:
        raise ValueError(f"klawisze = {s.get('klawisze')} — dozwolone: {', '.join(KEY_LABELS)}")
    words = [w.strip() for w in s.get("slowa", "").split(",") if w.strip()]
    return {
        "language": lang, "keys": frozenset(keys), "keywords": words,
        "trailing_space": yes("spacja_na_koncu"), "restore_clipboard": yes("przywracaj_schowek"),
        "telemetry": yes("statystyki"), "path": path,
    }


MIN_SECONDS = 0.4    # krotsze nagrania sa ignorowane
SHOW_DELAY = 0.25    # po ilu sekundach trzymania pokazuje sie czerwony pasek
# --------------------------------------------

# jedna instancja naraz
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "WhistleDyktowanieMutex")
if ctypes.windll.kernel32.GetLastError() == 183:
    message_box("Dyktowanie juz dziala.")
    sys.exit(0)

try:
    CFG = load_settings()
except Exception as e:
    log("ustawienia: " + repr(e))
    message_box(f"Blad w pliku ustawienia.txt:\n\n{e}", 0x10)
    sys.exit(1)

if not CFG["telemetry"]:
    os.environ["NEEDLE_TELEMETRY"] = "0"

import tkinter as tk

import keyboard
import numpy as np
import sounddevice as sd


def key_id(event):
    """Nazwa klawisza z KEY_LABELS albo None dla kazdego innego (w tym AltGr)."""
    name = (event.name or "").lower()
    scan = event.scan_code
    if scan == 29 and "ctrl" in name:
        return "prawy_ctrl" if "right" in name else "lewy_ctrl"
    if scan == 42 and "right" not in name:
        return "lewy_shift"
    if scan == 54 or name == "right shift":
        return "prawy_shift"
    if scan == 56 and name in ("alt", "left alt"):
        return "lewy_alt"
    return None


def resample(x, rate):
    """Przelicza nagranie do 16 kHz (zamiast biblioteki soxr, ktorej nie ma na Windows ARM)."""
    x = np.asarray(x, np.float32)
    if rate == SR or len(x) == 0:
        return x
    if rate > SR:  # filtr antyaliasingowy przed zmniejszeniem czestotliwosci
        fc = 0.45 * SR / rate
        n = np.arange(-64, 65)
        h = 2 * fc * np.sinc(2 * fc * n) * np.hamming(len(n))
        x = np.convolve(x, h / h.sum(), mode="same")
    t_old = np.arange(len(x)) / rate
    t_new = np.arange(int(len(x) * SR / rate)) / SR
    return np.interp(t_new, t_old, x).astype(np.float32)


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.keys_text = " + ".join(KEY_LABELS[k] for k in sorted(cfg["keys"], key=list(KEY_LABELS).index))
        self.root = tk.Tk()
        self.root.withdraw()
        self.pill = tk.Toplevel(self.root)
        self.pill.overrideredirect(True)
        self.pill.attributes("-topmost", True)
        self.pill.attributes("-alpha", 0.92)
        self.label = tk.Label(self.pill, text="", font=("Segoe UI", 11), fg="white", bg="#222", padx=16, pady=8)
        self.label.pack()
        self.pill.update_idletasks()
        self.hwnd = ctypes.windll.user32.GetParent(self.pill.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(self.hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(self.hwnd, -20, style | 0x08000000 | 0x80)  # nie kradnij fokusu
        self.pill.withdraw()

        self.ui = queue.Queue()
        self.jobs = queue.Queue()
        self.ready = False
        self.held = set()        # wcisniete klawisze z kombinacji
        self.dirty = False       # w tej kombinacji padl inny klawisz -> nie nagrywaj, az wszystko pusci
        self.recording = False
        self.rec_started = 0.0
        self.shown = False
        self.chunks = []
        self.stream = None
        self.rate = SR
        self.hide_at = None

        threading.Thread(target=self.worker, daemon=True).start()
        keyboard.hook(lambda e: self.ui.put(("key", e.event_type, key_id(e))))
        self.show("Ladowanie modelu Whistle… (pierwszy start pobiera ok. 20 MB)", "#444")
        self.jobs.put(("warmup",))
        self.root.after(20, self.poll)

    # ---------- nakladka ----------
    def show(self, text, color, seconds=None):
        self.label.config(text=text, bg=color)
        self.pill.config(bg=color)
        self.pill.update_idletasks()
        w, h = self.pill.winfo_reqwidth(), self.pill.winfo_reqheight()
        sw, sh = self.pill.winfo_screenwidth(), self.pill.winfo_screenheight()
        self.pill.geometry(f"+{(sw - w) // 2}+{sh - h - 90}")
        ctypes.windll.user32.ShowWindow(self.hwnd, 4)  # pokaz bez aktywacji
        self.hide_at = time.time() + seconds if seconds else None

    def hide(self):
        ctypes.windll.user32.ShowWindow(self.hwnd, 0)
        self.hide_at = None

    def poll(self):
        try:
            while True:
                self.handle(*self.ui.get_nowait())
        except queue.Empty:
            pass
        now = time.time()
        if self.recording and not self.shown and now - self.rec_started >= SHOW_DELAY:
            self.shown = True
            self.show(f"● Nagrywam…   pusc {self.keys_text}, by wkleic", "#c62828")
        if self.hide_at and now > self.hide_at:
            self.hide()
        self.root.after(20, self.poll)

    def handle(self, kind, *args):
        if kind == "key":
            self.on_key(*args)
        elif kind == "ready":
            self.ready = True
            self.show(f"Dyktowanie gotowe — przytrzymaj {self.keys_text}", "#2e7d32", 3)
        elif kind == "paste":
            self.paste(args[0])
        elif kind == "message":
            self.show(args[0], args[1], args[2])

    # ---------- logika klawiszy ----------
    def on_key(self, event_type, key):
        if key is not None and key not in self.cfg["keys"]:
            key = None                            # klawisz spoza kombinacji traktujemy jak kazdy inny
        if event_type == "down":
            if key is None:
                if self.held:
                    self.dirty = True
                    if self.recording:
                        self.abort()
                return
            if key in self.held:                  # autopowtarzanie
                return
            self.held.add(key)
            if self.held == self.cfg["keys"] and not self.dirty and not self.recording and self.ready:
                self.start()
        else:  # "up"
            if key is None:
                return
            self.held.discard(key)
            if self.recording:
                self.stop()
            if not self.held:
                self.dirty = False

    # ---------- nagrywanie ----------
    def start(self):
        self.chunks = []
        cb = lambda data, *_: self.chunks.append(data[:, 0].copy())
        try:
            try:
                self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=cb)
                self.rate = SR
            except Exception:
                self.rate = int(sd.query_devices(kind="input")["default_samplerate"])
                self.stream = sd.InputStream(samplerate=self.rate, channels=1, dtype="float32", callback=cb)
            self.stream.start()
        except Exception as e:
            log("mikrofon: " + repr(e))
            self.show("Brak mikrofonu — sprawdz Ustawienia > Prywatnosc > Mikrofon", "#b71c1c", 4)
            self.dirty = True
            return
        self.recording = True
        self.shown = False
        self.rec_started = time.time()

    def close_stream(self):
        self.recording = False
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass

    def abort(self):
        """Kombinacja + inny klawisz — to byl zwykly skrot, nie dyktowanie."""
        self.close_stream()
        if self.shown:
            self.hide()

    def stop(self):
        self.close_stream()
        audio = np.concatenate(self.chunks) if self.chunks else np.zeros(0, np.float32)
        if len(audio) < MIN_SECONDS * self.rate:
            if self.shown:
                self.hide()
            return
        self.show("Rozpoznaje…", "#1565c0")
        self.jobs.put(("transcribe", audio, self.rate))

    # ---------- model (osobny watek) ----------
    def worker(self):
        try:
            import needle
        except Exception:
            log(traceback.format_exc())
            self.ui.put(("message", "Nie udalo sie zaladowac Whistle — zobacz dyktowanie.log", "#b71c1c", 8))
            return
        cfg = self.cfg
        while True:
            job = self.jobs.get()
            try:
                if job[0] == "warmup":
                    needle.transcribe(np.zeros(SR, np.float32), language=cfg["language"])  # pobiera silnik i model przy 1. starcie
                    self.ui.put(("ready",))
                elif job[0] == "transcribe":
                    t = time.time()
                    out = needle.transcribe(resample(job[1], job[2]), language=cfg["language"],
                                            keywords=cfg["keywords"] or None)
                    text = (out.get("text") or "").strip()
                    log(f"{len(job[1]) / job[2]:.1f}s audio -> {time.time() - t:.2f}s: {text}")
                    if text:
                        while any(keyboard.is_pressed(k) for k in ("ctrl", "shift", "alt")):
                            time.sleep(0.02)  # poczekaj, az puscisz klawisze
                        self.ui.put(("paste", text + (" " if cfg["trailing_space"] else "")))
                    else:
                        self.ui.put(("message", "Nic nie uslyszalem", "#555", 1.5))
            except Exception:
                log(traceback.format_exc())
                if job[0] == "warmup":
                    self.ui.put(("message", "Nie udalo sie pobrac modelu — sprawdz internet i uruchom ponownie", "#b71c1c", 8))
                else:
                    self.ui.put(("message", "Blad — zobacz dyktowanie.log", "#b71c1c", 4))

    # ---------- wklejanie ----------
    def paste(self, text):
        old = None
        if self.cfg["restore_clipboard"]:
            try:
                old = self.root.clipboard_get()
            except Exception:
                old = None
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        keyboard.send("ctrl+v")
        self.hide()
        if old is not None:
            self.root.after(800, lambda: (self.root.clipboard_clear(), self.root.clipboard_append(old), self.root.update()))


if __name__ == "__main__":
    log(f"start — ustawienia: {CFG['path']}")
    App(CFG).root.mainloop()
