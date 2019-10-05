import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = 'hide'

import pygame
import pygame.sndarray
import numpy

sampleRate = 44100

def init():
    if pygame.version.vernum.major < 2:
        raise Exception("pygame < 2 has severe CPU usage bugs that interfere with speech recognition")
    pygame.mixer.pre_init(sampleRate, -16, 1, 512)
        # without the pre_init, there is a ~300ms delay when you play a sound..
    pygame.mixer.init()
    pygame.init()

def make_beep(freq, volume, duration, trailing_silence=0):
    return pygame.sndarray.make_sound(numpy.array(
        [volume * numpy.sin(2.0 * numpy.pi * freq * x / sampleRate) for x in range(int(duration * sampleRate))] +
        [0 for x in range(int(trailing_silence * sampleRate))]
        ).astype(numpy.int16))
