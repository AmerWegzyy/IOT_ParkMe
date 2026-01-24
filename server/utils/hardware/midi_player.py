import time
import threading
import mido

mido.set_backend('mido.backends.rtmidi')
class MidiBeatSync :

    def __init__(self, midi_path):
        # loading the midi file
        self.midi_path = midi_path
        self.mid = mido.MidiFile(midi_path)
        self.songBPM = self._extract_song_bpm()

        if self.songBPM is None:
            raise ValueError("This MIDI file has no tempo. ERROR")
    
        self.walkingBPM = self.songBPM
        self.TempoFactor = 1.0
        self.outport = mido.open_output()

        self._thread = None
        self._stop = False
        self._lock = threading.Lock()

    def _extract_song_bpm(self):
        for track in self.mid.tracks:
            for msg in track:
                if msg.type == "set_tempo":
                    return mido.tempo2bpm(msg.tempo)
        return None

    def set_BPM(self, bpm: float):
        if bpm <= 0:
            return
        with self._lock:
            self.walkingBPM = bpm
            self.TempoFactor = self.songBPM / self.walkingBPM

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True
        if self._thread:
            self._thread.join()
            self._thread = None

    def close(self):
        self.stop()
        self.outport.close()

    def _run(self):
        while not self._stop:
            # iterate the MIDI messages; msg.time is already seconds (delta)
            for msg in self.mid:
                if self._stop:
                    break
                delay = msg.time
                if delay > 0:
                    with self._lock:
                        tf = self.TempoFactor
                    target = time.perf_counter() + delay * tf
                    # playing one note at a time
                    while True:
                        if self._stop:
                            break
                        now = time.perf_counter()
                        remaining = target - now
                        if remaining <= 0:
                            break
                        time.sleep(min(0.001, remaining))
                        # updating the tempo factor mid-wait
                        with self._lock:
                            new_tf = self.TempoFactor
                        if new_tf != tf:
                            remaining *= new_tf / tf
                            tf = new_tf
                            target = now + remaining
                if not msg.is_meta:
                    self.outport.send(msg)
            # restart song on finish
            self.mid = mido.MidiFile(self.midi_path)
