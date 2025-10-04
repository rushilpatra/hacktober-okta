\
from typing import List, Tuple, Dict
from dataclasses import dataclass
from pydub import AudioSegment
from faster_whisper import WhisperModel

_model = None
def get_model():
    global _model
    if _model is None:
        _model = WhisperModel("small", compute_type="int8")
    return _model

@dataclass
class Word:
    text: str
    start: float
    end: float
    char_start: int
    char_end: int

def transcribe_with_words(audio_path: str):
    model = get_model()
    segments, info = model.transcribe(audio_path, word_timestamps=True)
    words: List[Word] = []
    full_text_parts = []
    cursor = 0
    for seg in segments:
        for w in seg.words:
            token = w.word.strip()
            if not token: continue
            if full_text_parts and not full_text_parts[-1].endswith(" "):
                full_text_parts.append(" "); cursor += 1
            full_text_parts.append(token)
            char_start = cursor
            cursor += len(token)
            words.append(Word(text=token, start=w.start, end=w.end, char_start=char_start, char_end=cursor))
    transcript = "".join(full_text_parts)
    return transcript, words

def spans_to_time_ranges(spans: List[Tuple[int,int]], words: List[Word]):
    ranges = []
    for s, e in spans:
        w_times = [(w.start, w.end) for w in words if not (w.char_end <= s or w.char_start >= e)]
        if not w_times: continue
        start = min(t[0] for t in w_times); end = max(t[1] for t in w_times)
        ranges.append((start, end))
    ranges.sort()
    merged = []
    for t in ranges:
        if not merged or t[0] > merged[-1][1] + 0.05:
            merged.append([t[0], t[1]])
        else:
            merged[-1][1] = max(merged[-1][1], t[1])
    return [(a,b) for a,b in merged]

def bleep_audio(input_path: str, time_ranges, tone_hz: int = 1000):
    audio = AudioSegment.from_file(input_path)
    out = audio
    for (start, end) in time_ranges:
        s = int(start * 1000); e = int(end * 1000)
        dur = max(0, e - s)
        if dur <= 0: continue
        tone = AudioSegment.sine(frequency=tone_hz, duration=dur).apply_gain(-3)
        out = out.overlay(tone, position=s)
    return out
