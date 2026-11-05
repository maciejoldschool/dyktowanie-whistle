# Dyktowanie — mów zamiast pisać (Windows)

Przytrzymaj **lewy Ctrl + lewy Shift** i mów. Puść, a tekst sam wklei się tam, gdzie stoi kursor.
Rozpoznawanie mowy działa lokalnie na Twoim komputerze, na modelu
[Whistle](https://cactuscompute.com/blog/whistle) od Cactus Compute (polski, angielski, niemiecki,
francuski, hiszpański, włoski, niderlandzki). Nagrania nie są nigdzie wysyłane.

## Pobieranie

Najnowsze paczki są w zakładce **[Releases](https://github.com/maciejoldschool/dyktowanie-whistle/releases/latest)**:

| Paczka | Dla kogo |
|---|---|
| `Dyktowanie-x64.zip` | zwykłe komputery z Windows (Intel, AMD) |
| `Dyktowanie-arm64.zip` | komputery z Windows na ARM (np. Snapdragon) |

Nie wiesz, który masz? Ustawienia Windows → System → Informacje → „Typ systemu”.

Pełna instrukcja jest w [INSTRUKCJA.txt](INSTRUKCJA.txt) i w środku każdej paczki.

## W skrócie

1. Rozpakuj zip i uruchom `Dyktowanie-….exe`.
2. Jeśli Windows pokaże „System Windows ochronił ten komputer”, kliknij **Więcej informacji → Uruchom mimo to**
   (program nie ma płatnego podpisu cyfrowego).
3. Za pierwszym razem program pobierze model mowy (ok. 20 MB). Gdy pojawi się zielony pasek
   „Dyktowanie gotowe”, możesz mówić.
4. Język, klawisze i słowa-podpowiedzi zmienisz w pliku `ustawienia.txt` obok programu.

## Dla programistów

Całość to jeden plik: [`dyktowanie.pyw`](dyktowanie.pyw). Paczki `.exe` buduje automatycznie
[GitHub Actions](.github/workflows/build.yml) (PyInstaller, osobno x64 i ARM64); każdy `.exe`
przechodzi samotest (`--test`), zanim trafi do wydania.

Uruchomienie ze źródeł (Python 3.12+):

```
pip install cactus-needle numpy sounddevice keyboard
pythonw dyktowanie.pyw
```

Dodatek `cactus-needle[mic]` nie jest potrzebny: jego biblioteka `soxr` nie ma gotowej wersji
na Windows ARM, więc przeliczanie dźwięku do 16 kHz robi sam skrypt.
