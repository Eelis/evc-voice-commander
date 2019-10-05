#!/usr/bin/env python3

# This script:
# - auto-mutes output when a loud noise is heard on the microphone
# - keeps output muted until the microphone isn't being used anymore
# - only passes microphone sound through if output is muted or output isn't beingused

import soundcard
import threading
import pulsectl
import numpy
import sys
import time

output_to_watch = "Monitor of Built-in Audio Analog Stereo"
mic_name = "UMC202HD 192k Analog Stereo"

deactivate_if_output_louder_than = 0.05
activate_if_mic_louder_than = 0.53
extend_active_if_mic_louder_than = 0.1
output_volume_when_active = 0.1

def find_mic():
    for mic in soundcard.all_microphones():
        if mic.name == mic_name:
            return mic
    raise Exception('could not find microphone: "' + mic_name + '"')

def find_output():
    for mic in soundcard.all_microphones(include_loopback=True):
        if mic.name == output_to_watch:
            return mic
    raise Exception('could not find output: "' + output_to_watch + '"')

sample_rate = 16000

pulse = pulsectl.Pulse('pre-evc')

def get_sink():
    return pulse.sink_list()[0] # todo: find by name or use default or something

last_significant_output = 0

def read_output(output):
    global last_significant_output
    with output.recorder(samplerate=1024, channels=[-1]) as rec:
        while True:
            data = rec.record(numframes=64)
            for v in data:
                if abs(v) > deactivate_if_output_louder_than:
                    last_significant_output = time.time()
                    break

sink = get_sink()

def read_mic(mic):
    orig_volume = None
    muting = False
    last_significant_input = 0
    with mic.recorder(samplerate=sample_rate, channels=[-1]) as rec:
        while True:
            data = rec.record(numframes = sample_rate / 20)
            now = time.time()

            # pass data through:
            if muting or not now - last_significant_output < 2:
                sys.stdout.buffer.write((data * 2**16).astype(numpy.int16).tobytes())

            # notice loud input (e.g. claps):
            for v in data:
                if abs(v) > activate_if_mic_louder_than:
                    last_significant_input = now
                    break

            # notice continued speech:
            if last_significant_input != now and now - last_significant_input < 2:
                for v in data:
                    if abs(v) > extend_active_if_mic_louder_than:
                        last_significant_input = now
                        break

            if muting and now - last_significant_input > 2:
                # unmute:
                pulse.volume_set(sink, pulsectl.PulseVolumeInfo(orig_volume))
                muting = False
            elif not muting and now - last_significant_input < 2:
                # mute:
                orig_volume = sink.volume.values.copy()
                new_volume = pulsectl.PulseVolumeInfo(output_volume_when_active, len(orig_volume))
                pulse.volume_set(sink, new_volume)
                muting = True


output = find_output()
mic = find_mic()

threading.Thread(target=lambda: read_output(output)).start()
read_mic(mic)
