#!/usr/bin/env python3

import pyaudio
import sys

RATE = 16000
CHUNK = int(RATE / 10)

audio = pyaudio.PyAudio()
stream = audio.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)

while True: sys.stdout.buffer.write(stream.read(CHUNK))
