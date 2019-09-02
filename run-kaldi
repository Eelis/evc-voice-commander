import time
import os
import argparse
from gi.repository import GObject
import yaml
import json
import sys
import locale
import codecs
import time
import gi
import pdb
from collections import OrderedDict

gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

GObject.threads_init()
Gst.init(None)

class DecoderPipeline2(object):
    def __init__(self, conf={}):
        self.create_pipeline(conf)

        self.result_handler = None
        self.full_result_handler = None
        self.eos_handler = None
        self.error_handler = None


    def create_pipeline(self, conf):

        self.appsrc = Gst.ElementFactory.make("appsrc", "appsrc")
        self.decodebin = Gst.ElementFactory.make("decodebin", "decodebin")
        self.audioconvert = Gst.ElementFactory.make("audioconvert", "audioconvert")
        self.audioresample = Gst.ElementFactory.make("audioresample", "audioresample")
        self.tee = Gst.ElementFactory.make("tee", "tee")
        self.queue1 = Gst.ElementFactory.make("queue", "queue1")
        self.filesink = Gst.ElementFactory.make("filesink", "filesink")
        self.queue2 = Gst.ElementFactory.make("queue", "queue2")
        self.asr = Gst.ElementFactory.make("kaldinnet2onlinedecoder", "asr")
        self.fakesink = Gst.ElementFactory.make("fakesink", "fakesink")

        if not self.asr:
            print >> sys.stderr, "ERROR: Couldn't create the kaldinnet2onlinedecoder element!"
            sys.exit(-1);

        self.asr.set_property("use-threaded-decoder", True) # todo: necessary?

        decoder_config = conf
        if 'nnet-mode' in decoder_config:
          self.asr.set_property('nnet-mode', decoder_config['nnet-mode'])
          del decoder_config['nnet-mode']

        decoder_config = OrderedDict(decoder_config)

        if "fst" in decoder_config:
            decoder_config["fst"] = decoder_config.pop("fst")
        if "model" in decoder_config:
            decoder_config["model"] = decoder_config.pop("model")

        for (key, val) in decoder_config.iteritems():
            if key != "use-threaded-decoder":
                self.asr.set_property(key, val)

        self.appsrc.set_property("is-live", True)
        self.filesink.set_property("location", "/dev/null")

        self.pipeline = Gst.Pipeline()
        for element in [self.appsrc, self.decodebin, self.audioconvert, self.audioresample, self.tee,
                        self.queue1, self.filesink,
                        self.queue2, self.asr, self.fakesink]:
            self.pipeline.add(element)


        self.appsrc.link(self.decodebin)
        self.decodebin.connect('pad-added', self._connect_decoder)
        self.audioconvert.link(self.audioresample)

        self.audioresample.link(self.tee)

        self.tee.link(self.queue1)
        self.queue1.link(self.filesink)

        self.tee.link(self.queue2)
        self.queue2.link(self.asr)

        self.asr.link(self.fakesink)

        # Create bus and connect several handlers
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.enable_sync_message_emission()
        self.bus.connect('message::eos', self._on_eos)
        self.bus.connect('message::error', self._on_error)

        #self.asr.connect('partial-result', self._on_partial_result)
        self.asr.connect('final-result', self._on_final_result)
        #self.asr.connect('full-final-result', self._on_full_final_result)

        self.pipeline.set_state(Gst.State.READY)

    def _connect_decoder(self, element, pad):
        pad.link(self.audioconvert.get_static_pad("sink"))


    def _on_partial_result(self, asr, hyp):
        #logger.info("Got partial result: %s" % hyp.decode('utf8'))
        pass

    def _on_final_result(self, asr, hyp):
        decoded = hyp.decode('utf8')
        print decoded
        sys.stdout.flush()
        #logger.info("Got final result: %s" % decoded)

    def _on_full_final_result(self, asr, result_json):
        decoded = result_json.decode('utf8')
        print decoded
        #logger.info("Got full final result: %s" % result_json.decode('utf8'))

    def _on_error(self, bus, msg):
        print msg.parse_error()

    def _on_eos(self, bus, msg):
        pass
        #logger.info('Pipeline received eos signal')

    def init_request(self, caps_str):
        #logger.info("Setting caps to %s" % caps_str)
        caps = Gst.caps_from_string(caps_str)
        self.appsrc.set_property("caps", caps)
        self.pipeline.set_state(Gst.State.PLAYING)
        self.filesink.set_state(Gst.State.PLAYING)

    def process_data(self, data):
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        self.appsrc.emit("push-buffer", buf)

decoder_pipeline = None

def on_stdin_data(x, more):
    data = x.read(4096)
    if len(data) != 0:
        decoder_pipeline.process_data(data)
    return True

def main():
    global decoder_pipeline

    with open("/opt/models/english_nnet2.yaml") as f:
        conf = yaml.safe_load(f)

    decoder_pipeline = DecoderPipeline2(conf)
    decoder_pipeline.init_request("audio/x-raw, layout=(string)interleaved, rate=(int)16000, format=(string)S16LE, channels=(int)1")

    loop = GObject.MainLoop()
    GObject.io_add_watch(sys.stdin, GObject.IO_IN, on_stdin_data)
    loop.run()

if __name__ == "__main__":
    main()

