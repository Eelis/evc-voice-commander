#!/usr/bin/env python3

import ecl
import eclbuiltins
import util
import time
import os
import subprocess
import sys
import shutil
import termcolor
from contextlib import contextmanager
from ctypes import *
import click
import yaml

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

# config from files:
configdir = ''
numbers = {}
word_replacements = {}
eclc = ecl.EclContext()
short_mode_names = {}
auto_enable_cfg = {}
explicitly_autoenabled = []

# options:
prompt = True
printactions = False
color = True
sound_effects = False

# active application detection:
current_windowtitle = ''
current_windowprocesses = {}

# evc state:
mode = None
completions = {}
suggestions = []


def colored(s, c):
    if not color: return s
    return termcolor.colored(s, c)

def load_yaml(f):
    with open(f, 'r') as stream:
        return yaml.load(stream, yaml.CLoader)

def load_config():
    global word_replacements, numbers, eclc, completions, short_mode_names, auto_enable_cfg
    short_mode_names = {}
    auto_enable_cfg = {}
    word_replacements = load_yaml(configdir + '/replacements.yaml')
    numbers = load_yaml(configdir + '/numbers.yaml')
    modes = load_yaml(configdir + '/modes.yaml')

    # handle enums:
    eclc.enums = {}
    completions = {}
    for key, v in modes.items():
        if key.startswith('<'):
            n = key[1:-1]
            if type(v) is dict:
                if 'completions' in v:
                    completions[n] = v['completions']
                v = v['forms']
            if type(v) is list: v = '/'.join(v)
            eclc.enums[n] = v
    for e in eclc.enums:
        del modes['<' + e + '>']

    # handle shortnames:
    def remove_shortname(s):
        i = s.find('(')
        return (s if i == -1 else s[:i].strip())
    for mode, aliases in modes.items():
        realname = remove_shortname(mode)
        if realname != mode:
            shortname = mode[mode.find('(') + 1: -1]
            short_mode_names[realname] = shortname
    modes = dict([(remove_shortname(m), a) for m, a in modes.items()])

    # handle auto-enabling:
    for mode, aliases in modes.items():
        cfg = {}
        if 'auto-enable' in aliases:
            cfg = aliases['auto-enable']
            del aliases['auto-enable']
        if 'always' not in cfg: cfg['always'] = False
        if 'built-ins' not in cfg: cfg['built-ins'] = True
        if 'other-modes' not in cfg: cfg['other-modes'] = True
        cfg['for-applications'] = (cfg['for-applications'].split() if 'for-applications' in cfg else [])
        cfg['for-leaf-applications'] = (cfg['for-leaf-applications'].split() if 'for-leaf-applications' in cfg else [])
        if 'for-prefixes' not in cfg: cfg['for-prefixes'] = []
        if 'for-suffixes' not in cfg: cfg['for-suffixes'] = []
        auto_enable_cfg[mode] = cfg

    eclc.modes = modes

def mode_is_auto_enabled(current_mode, candidate):
    c = auto_enable_cfg[current_mode]
    if not c['other-modes']: return False

    if candidate in explicitly_autoenabled: return True

    c = auto_enable_cfg[candidate]
    if c['always']: return True
    for app in c['for-applications']:
        if util.occurs_in_branch(app, current_windowprocesses): return True
    for app in c['for-leaf-applications']:
        if util.occurs_as_leaf_in_branch(app, current_windowprocesses): return True
    for prefix in c['for-prefixes']:
        if current_windowtitle.startswith(prefix): return True
    for suffix in c['for-suffixes']:
        if current_windowtitle.endswith(suffix): return True
    return False

def get_active_modes():
    return [mode] + [m for m in eclc.modes if m != mode and mode_is_auto_enabled(mode, m)]
        # important: mode itself comes first

def color_commands(p): return colored(p, 'magenta')

def color_mode(m): return colored(m, 'cyan')

# input preprocessing:

def replace_numbers(words, collected=''):
    if words == []: return ([collected] if collected != '' else [])
    first, *rest = words
    if first in numbers: return replace_numbers(rest, collected + numbers[first])
    if collected != '': return [collected, first] + replace_numbers(rest)
    return [first] + replace_numbers(rest)

def replace_words(words):
    if words == []: return []
    for i in range(0, len(words)):
        for k, vv in word_replacements.items():
            for v in vv:
                kw = v.split()
                if len(words) >= i + len(kw) and words[i:i+len(kw)] == kw:
                    return words[:i] + k.split() + replace_words(words[i+len(kw):])
    return words

def get_suggestions(missing, enums):
    r = []
    for m in missing:
        for u in m.split('|'):
            if u.startswith('<'):
                type = u[1:-1]
                if type in completions:
                    cmd = completions[type]
                    r += subprocess.Popen(cmd, shell=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL).stdout.read().decode('utf-8').strip().split('\n')
                elif type in enums:
                    mm = [form.split()[0] for form in enums[type].split('/')]
                    r += get_suggestions(mm, enums)
            else:
                r.append(u)
    return r

def eval_command(words, line):
    global suggestions
    if words == []: return

    handle_builtins = auto_enable_cfg[mode]['built-ins']

    enabled_modes = get_active_modes()

    pr = eclc.process(words, enabled_modes, handle_builtins)
    if pr.longest != 0: suggestions = get_suggestions(pr.missing, eclc.enums)
    c = confirm_input(words, pr, line)

    if printactions:
        actnames = [' '.join(w) for _, w in pr.actions]
        if actnames != [] and ' '.join(actnames) != ' '.join(words):
            print(', '.join(actnames))

    ctx = {"enabled_modes": enabled_modes, 'ecl': eclc}
    attempt = None
    try:
        for f, w in pr.actions:
            attempt = w
            f(ctx, *w)
    except Exception as e:
        print(colored(' '.join(attempt) + ": " + str(e), 'red'))

    if c: clear_line()
    return pr.longest

async def process_lines(input):
    import asyncio
    global mode
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader(loop=loop, limit=asyncio.streams._DEFAULT_LIMIT)
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader, loop=loop), input)

    if prompt: print_prompt()
    last_active_modes = get_active_modes()

    successful_input = []

    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), 0.5)
        except asyncio.TimeoutError:
            get_current_application()
            m = get_active_modes()
            if last_active_modes != m:
                last_active_modes = m
                if prompt:
                    clear_line()
                    print_prompt()
        else:
            if not line: break # EOF
            else:
                line = line.decode('utf-8').rstrip('\n')
                if line == '' or line[0] == '#': continue

                try:
                    load_config()
                except Exception as e:
                    print("\nerror loading config:", e)

                words = replace_numbers(replace_words(line.split()))
                if len(words) > 0 and words[0] in ['the', 'a', 'i', 'and']:
                    words.pop(0)
                if words != []:
                    if words[0] == 'continue': words = successful_input + words[1:]
                    elif len(suggestions) == 1 and words == ['indeed']:
                        words = successful_input + [suggestions[0]]
                    elif suggestions != [] and len(words) == 2 and words[0] == 'indeed' and words[1].isdigit():
                        i = int(words[1])
                        if i < len(suggestions):
                            words = successful_input + [suggestions[i]]
                    longest = eval_command(words, line)
                    if longest != 0:
                        successful_input = words[:longest]
                    if prompt: print_prompt()
                    last_active_modes = get_active_modes()

# output:

def sound(n, count=1, wait=True):
    if count == 0 or not sound_effects: return
    import pygame
    pygame.mixer.music.load("sounds/" + n)
    for i in range(0, count):
        pygame.mixer.music.play()
        if wait:
            while pygame.mixer.music.get_busy(): time.sleep(0.01)
            time.sleep(0.1)

def short_mode_name(mode):
    return (short_mode_names[mode] if mode in short_mode_names else mode)

def clear_line():
    if not sys.stdout.isatty() or not prompt: return
    cols = shutil.get_terminal_size().columns
    print('\r' + ' ' * cols + '\r', end='')
    sys.stdout.flush()

def prompt_string():
    current, *auto = get_active_modes()
    short_current = short_mode_name(current)
    mm = []
    if short_current != '': mm = [short_current]
    elif auto != []: mm = [current]
    mm += [s for s in list(map(short_mode_name, auto)) if s != '']
    return ','.join(map(color_mode, mm)) + '> '

def print_prompt():
    print(prompt_string(), end='')
    sys.stdout.flush()

def truncate(s, n):
    return (s[:n-3] + '...' if len(s) > n else s)

def confirm_input(words, pr, original_input):
    n = pr.longest
    cols = shutil.get_terminal_size().columns
    prp = prompt_string()
    printed = ''
    if n == 0 or (n == 1 and pr.missing != [] and words[0].isdigit()):
        clear_line()
        print(prp + colored(truncate(original_input, cols - len(util.strip_markup(prp))), 'yellow'), end='\r')
        sys.stdout.flush()
        return False
    if prompt:
        clear_line()
        printed = prp + colored(' '.join(words[:n]), 'green')
        print(printed, end='')
    if pr.error is not None:
        print()
        print(colored('error:', 'red'), pr.error)
        sound('good.wav', n)
        sound('bad.wav', 1, wait=False)
        return False

    if prompt:
        if n != len(words):
            if n != 0:
                print(' ', end='')
                printed += ' '
            avail = cols - len(util.strip_markup(printed))
            print(colored(truncate(' '.join(words[n:]), avail), 'red'), end='')
        elif pr.missing != []:
            # if all words were consumed but evaluation still went bad,
            # it means additional input was missing
            print(colored(' ???', 'red'), end='')
        print()

    if pr.missing == []:
        if pr.retval is not None:
            print(colored(str(pr.retval), 'magenta'))
    else:
        if suggestions != []:
            if len(suggestions) == 1 and not suggestions[0].startswith('<'):
                print(colored("error: did you mean '" + suggestions[0] + "'?", 'red'))
            else:
                print(colored("did you perhaps mean:", 'red'))
                rows = shutil.get_terminal_size().lines
                for i, s in enumerate(suggestions[:rows - 3]):
                    print('-', s + '?', '(' + str(i) + ')')
        else:
            what = ' or '.join(map(eclc.italic_types, list(set(pr.missing))))
            problem = ('missing' if n == len(words) else 'expected')
            print(colored('error: ' + problem + ' ' + what, 'red'))

    sound('good.wav', n)
    if n != len(words) or pr.missing != []:
        sound('bad.wav', 1, wait=False)
    return True

def get_current_application():
    global current_windowtitle, current_windowprocesses
    current_windowtitle = ''
    current_windowprocesses = {}
    active_win = simple_subprocess('xdotool getactivewindow')
    if active_win == '': return
    current_windowtitle = simple_subprocess('xdotool getwindowname ' + active_win)
    current_windowpid = simple_subprocess('xdotool getwindowpid ' + active_win)
    if current_windowpid != '':
        current_windowprocesses = util.process_family(int(current_windowpid))

ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)

def py_asound_error_handler(filename, line, function, err, fmt):
    pass

c_asound_error_handler = ERROR_HANDLER_FUNC(py_asound_error_handler)

@contextmanager
def noalsaerr():
    if sound_effects:
        asound = cdll.LoadLibrary('libasound.so')
        asound.snd_lib_error_set_handler(c_asound_error_handler)
    yield
    if sound_effects:
        asound.snd_lib_error_set_handler(None)

@contextmanager
def hidden_cursor():
    if sys.stdout.isatty() and prompt:
        sys.stdout.write("\033[?25l") # hide cursor
    try:
        yield
    finally:
        if sys.stdout.isatty() and prompt:
            sys.stdout.write("\033[?25h") # restore cursor

@click.command()
@click.option('--color', default=True, type=bool)
@click.option('--prompt', default=True, type=bool)
@click.option('--printactions', default=False, type=bool, is_flag=True)
@click.option('--configdir', default=os.getenv('HOME') + '/.evc-voice-commander',type=str)
@click.option('--dryrun', default=False, type=bool, is_flag=True)
@click.option('--volume', default=0.1, type=float) # default volume very low so our beeps are
                                                   # (a) non-obnoxious, and
                                                   # (b) won't interfere with speech recognition.
@click.argument('mode', nargs=1, default='default')
@click.argument('cmd', nargs=-1)
def evc(color, prompt, printactions, configdir, dryrun, volume, mode, cmd):
    global sound_effects, explicitly_autoenabled

    mm = mode.split(',')
    explicitly_autoenabled = mm[1:]
    mode = mm[0]

    globals()['mode'] = mode
    globals()['color'] = color
    eclc.color = color
    globals()['configdir'] = configdir
    eclc.script_vars['configdir'] = configdir
    eclbuiltins.dryrun = dryrun
    globals()['prompt'] = prompt
    globals()['printactions'] = printactions

    initial_words = list(cmd)
    if volume != 0:
        import pygame
        pygame.init()
        pygame.mixer.music.set_volume(volume)
        sound_effects = True

    load_config()

    if mode not in eclc.modes:
        print("no such mode:", mode)
        return

    with noalsaerr():
        with hidden_cursor():
            if initial_words != []:
                eval_command(initial_words, ' '.join(initial_words))
            else:
                import asyncio
                asyncio.get_event_loop().run_until_complete(process_lines(sys.stdin))

if __name__ == '__main__': evc()
