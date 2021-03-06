#!/usr/bin/env python3

import ecl
import eclbuiltins
import eclcompletion
import util
import os
import subprocess
import sys
import shutil
import time
import termcolor
from contextlib import contextmanager
from ctypes import *
import click
import yaml
from typing import Dict, List, Tuple, Optional

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = 'hide'

class AutoEnableConfig: # for a given mode
    always: bool
    builtins: bool
    other_modes: bool
    for_prefixes: List[str]
    for_suffixes: List[str]
    for_applications: List[str]
    for_leaf_applications: List[str]

# config from files:
configdir = ''
numbers: Dict[str, str] = {}
word_replacements: Dict[str, List[str]] = {}
eclc = ecl.Context({}, {})
short_mode_names: Dict[str, str] = {}
auto_enable_cfg: Dict[ecl.Mode, AutoEnableConfig] = {}

# options:
prompt = True
color = True

# active application detection:
current_windowtitle = ''
current_windowprocesses = {}

# evc state:
mode: ecl.Mode = 'default'
suggestions = None
all_good_beep = None
good_beep = None
bad_beep = None

def colored(s: str, c: str) -> str:
    if not color: return s
    return termcolor.colored(s, c)

def load_yaml(f: str):
    with open(f, 'r') as stream:
        return yaml.load(stream, yaml.CLoader)

def read_auto_enable_config(cfg) -> AutoEnableConfig:
    r = AutoEnableConfig()
    r.always = cfg.get('always', False)
    r.builtins = cfg.get('built-ins', True)
    r.other_modes = cfg.get('other-modes', True)
    r.for_applications = cfg.get('for-applications', '').split()
    r.for_leaf_applications = cfg.get('for-leaf-applications', '').split()
    r.for_prefixes = cfg.get('for-prefixes', [])
    r.for_suffixes = cfg.get('for-suffixes', [])
    return r

def load_config():
    global eclc, word_replacements, numbers
    word_replacements = load_yaml(configdir + '/replacements.yaml')
    numbers = load_yaml(configdir + '/numbers.yaml')
    modes = load_yaml(configdir + '/modes.yaml')

    # handle enums:
    enums = {}
    new_completions = {}
    for key, v in modes.items():
        t = ecl.parse_type(key)
        if t is not None:
            if type(v) is dict:
                if 'completions' in v:
                    new_completions[t] = v['completions']
                v = v['forms']
            if type(v) is list: v = '/'.join(v)
            enums[t] = ecl.parse_pattern(v)
    for e in enums:
        del modes['<' + e + '>']

    # handle shortnames:
    def remove_shortname(s):
        i = s.find('(')
        return (s if i == -1 else s[:i].strip())
    new_short_mode_names = {}
    for mode, aliases in modes.items():
        realname = remove_shortname(mode)
        if realname != mode:
            shortname = mode[mode.find('(') + 1: -1]
            new_short_mode_names[realname] = shortname
    modes = dict([(remove_shortname(m), a) for m, a in modes.items()])

    # handle auto-enabling:

    new_auto_enable_cfg = {}
    always_on_modes = []
    for mode, aliases in modes.items():
        if type(aliases) is not dict: raise Exception(mode + " is not a dict")
        cfg = read_auto_enable_config(aliases.get('auto-enable', {}))
        new_auto_enable_cfg[mode] = cfg
        if cfg.always: always_on_modes.append(mode)
        if 'auto-enable' in aliases: del aliases['auto-enable']

    # commit

    global short_mode_names, auto_enable_cfg

    eclc = ecl.Context(modes, enums)

    eclc.color = color
    eclc.script_vars['configdir'] = configdir
    eclc.builtin_commands = eclbuiltins.builtin_commands
    eclc.global_builtins = eclbuiltins.global_builtins
    eclc.builtin_types = eclbuiltins.builtin_types
    eclc.always_on_modes = always_on_modes
    auto_enable_cfg = new_auto_enable_cfg
    short_mode_names = new_short_mode_names
    eclc.completions = new_completions

cmdline_modes: List[str] = []
def mode_is_auto_enabled(candidate: ecl.Mode) -> bool:
    if candidate in cmdline_modes: return True
    c = auto_enable_cfg[candidate]
    if c.always: return True
    for app in c.for_applications:
        if util.occurs_in_branch(app, current_windowprocesses): return True
    for app in c.for_leaf_applications:
        if util.occurs_as_leaf_in_branch(app, current_windowprocesses): return True
    for prefix in c.for_prefixes:
        if current_windowtitle.startswith(prefix): return True
    for suffix in c.for_suffixes:
        if current_windowtitle.endswith(suffix): return True
    return False

def get_active_modes() -> List[str]:
    return [mode] + [m for m in eclc.modes if m != mode and mode_is_auto_enabled(m)]
        # important: mode itself comes first

@eclbuiltins.make_functional_builtin('get active modes')
def cmd_get_active_modes(*_):
    return ' '.join(get_active_modes())

def color_mode(m: ecl.Mode) -> str: return colored(m, 'cyan')

# input preprocessing:

def replace_numbers(words: List[str], collected=''):
    if not words: return ([collected] if collected != '' else [])
    first, *rest = words
    if first in numbers: return replace_numbers(rest, collected + numbers[first])
    if collected != '': return [collected, first] + replace_numbers(rest)
    return [first] + replace_numbers(rest)

def replace_words(words: List[str]) -> List[str]:
    if not words: return []
    for i in range(0, len(words)):
        for k, vv in word_replacements.items():
            for v in vv:
                kw = v.split()
                if len(words) >= i + len(kw) and words[i:i+len(kw)] == kw:
                    return words[:i] + k.split() + replace_words(words[i+len(kw):])
    return words

def eval_command(words: List[str], line: str, enabled_modes: List[ecl.Mode], ignore_0match):
    global suggestions, mode
    if not words: return

    handle_builtins = auto_enable_cfg[mode].builtins

    try:
        pr = eclc.match_commands(words, enabled_modes, handle_builtins)
    except Exception as e:
        print(colored(' '.join(words) + ": " + str(e), 'red'))
        return 0

    if pr.longest != 0 and pr.missing:
        suggestions = eclcompletion.get_suggestions(eclc, words[:pr.longest], pr.missing, enabled_modes, handle_builtins)
    c = confirm_input(words, pr, line, ignore_0match)
    if pr.new_mode is not None:
        mode = pr.new_mode

    ctx = {"enabled_modes": enabled_modes, 'ecl': eclc}
    attempt = None
    try:
        for f, w in pr.actions:
            attempt = w
            f(ctx, *w)
    except Exception as e:
        if attempt is not None:
            print(colored(' '.join(attempt) + ": " + str(e), 'red'))

    if c and prompt: util.clear_line()
    return pr.longest

ignore_lines = ['', 'if']

def maybe_pick_suggestion(words: List[str], linsugs: List[List[str]]) -> Optional[List[str]]:
    i = -1
    if len(linsugs) == 1 and words == ['yes']: i = 0
    if len(linsugs) > 1 and len(words) == 1 and words[0].isdigit(): i = int(words[0]) - 1
    if len(words) == 3 and words[:2] == ["yes", "the"]: i = util.ordinal(words[2])
    if len(words) == 2 and words[0] == 'yes' and words[1].isdigit():
        i = int(words[1]) - 1
    return (linsugs[i] if 0 <= i and i < len(linsugs) else None)

async def process_lines(input):
    import asyncio
    global current_windowtitle, current_windowprocesses, suggestions
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader(loop=loop, limit=asyncio.streams._DEFAULT_LIMIT) # type: ignore
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader, loop=loop), input)

    if prompt: print_prompt()
    last_active_modes = get_active_modes()

    successful_input: List[str] = []

    while True:
        try:
            line_bytes = await asyncio.wait_for(reader.readline(), 0.5)
        except asyncio.TimeoutError:
            current_windowtitle, current_windowprocesses = util.get_current_application()
            x = util.cwd_of_branch(current_windowprocesses)
            if x is not None:
                try: os.chdir(x)
                except FileNotFoundError: pass
                except PermissionError: pass
            m = get_active_modes()
            if last_active_modes != m:
                last_active_modes = m
                if prompt:
                    util.clear_line()
                    print_prompt()
        else:
            if not line_bytes: break # EOF
            line: str = line_bytes.decode('utf-8').rstrip('\n')
            if line in ignore_lines or line[0] == '#': continue

            try:
                load_config()
            except Exception as e:
                print("\nerror loading config:", e)

            words = replace_numbers(replace_words(line.split()))
            if len(words) > 0 and words[0] in ['the', 'a', 'i', 'and']:
                words.pop(0)
            if words:
                if words[0] == 'continue': words = successful_input + words[1:]
                elif suggestions is not None:
                    p = maybe_pick_suggestion(words, eclcompletion.linear_suggestions(suggestions))
                    if p is not None:
                        words = successful_input + p
                        suggestions = None
                enabled_modes = get_active_modes()
                longest = eval_command(words, line, enabled_modes, True)
                if longest != 0:
                    successful_input = words[:longest]
                elif "dictation" in eclc.script_vars and eclc.script_vars["dictation"] == "true":
                    eval_command(["builtin", "text"] + words, "builtin text " + line,
                        enabled_modes, True)
                if prompt: print_prompt()
                last_active_modes = get_active_modes()

def short_mode_name(mode: ecl.Mode) -> str:
    return (short_mode_names[mode] if mode in short_mode_names else mode)

def prompt_string() -> str:
    current, *auto = get_active_modes()
    if current == 'default': auto = []
    short_current = short_mode_name(current)
    mm: List[ecl.Mode] = []
    if short_current != '': mm = [short_current]
    elif auto: mm = [current]
    mm += [s for s in list(map(short_mode_name, auto)) if s != '']
    mm = list(map(eclc.color_mode, mm))
    if eclc.script_vars.get('dictation', '') == 'true':
        mm.append('*')
    return ','.join(mm) + '> '

def print_prompt():
    print(prompt_string(), end='')
    sys.stdout.flush()

def confirm_input(words: List[str], pr, original_input, ignore_0match):
    n = pr.longest
    cols = shutil.get_terminal_size().columns
    prp = prompt_string()
    printed = ''
    if ignore_0match and (n == 0 or (n == 1 and pr.missing and words[0].isdigit())):
        if prompt: util.clear_line()
        print(prp + colored(util.truncate(original_input, cols - len(util.strip_markup(prp))), 'yellow'), end='\r')
        sys.stdout.flush()
        return False
    if prompt:
        util.clear_line()
        printed = prp
        print(printed, end='')
        sys.stdout.flush()

    if prompt:
        needed = 0
        i = 0
        while i < n:
            needed += len(words[i])
            if i + 1 < n: needed += len(' ')
            i += 1
        if n != len(words):
            if n != 0: needed += len(' ')
            needed += 5
        elif pr.missing:
            needed += len(' ???')
        avail = cols - len(util.strip_markup(printed))
        if needed > avail:
            print('\n  ', end='')
            printed = '  '

    all_good = (n == len(words) and not pr.missing and pr.error is None)

    if all_good:
        if all_good_beep is not None:
            all_good_beep.play()
    elif good_beep is not None and n != 0:
        good_beep.play(n - 1)

    i = 0
    while i < n:
        if prompt:
            x = colored(words[i], 'green')
            if i + 1 < n: x += ' '
            print(x, end='')
            sys.stdout.flush()
            printed += x
        if not all_good and good_beep is not None:
            time.sleep(good_beep.get_length())
        i += 1

    if not all_good and bad_beep is not None:
        bad_beep.play()

    if prompt:
        if n != len(words):
            if n != 0:
                print(' ', end='')
                printed += ' '
            avail = cols - len(util.strip_markup(printed))
            print(colored(util.truncate(' '.join(words[n:]), avail), 'red'), end='')
        elif pr.missing:
            # if all words were consumed but evaluation still went bad,
            # it means additional input was missing
            print(colored(' ???', 'red'), end='')
        print()

    if pr.error is not None:
        print()
        print(colored('error:', 'red'), pr.error)
        return False

    if not pr.missing:
        if pr.retval is not None:
            s = str(pr.retval)
            if not s.endswith('\n'): s += '\n'
            print(s, end='')
    elif n != len(words) and pr.missing == ['<command>']:
        print(colored('error: no such command', 'red'))
    elif suggestions is not None:
        eclcompletion.print_suggestions(eclc, suggestions)
    else:
        problem = ('missing' if n == len(words) else 'expected')
        problem += ' ' + ' or '.join(map(eclc.render_unit, list(set(pr.missing))))
        print(colored('error: ' + problem, 'red'))

    return True

ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)

def py_asound_error_handler(filename, line, function, err, fmt):
    pass

c_asound_error_handler = ERROR_HANDLER_FUNC(py_asound_error_handler)

@contextmanager
def noalsaerr(enabled: bool):
    if enabled:
        asound = cdll.LoadLibrary('libasound.so')
        asound.snd_lib_error_set_handler(c_asound_error_handler)
    yield
    if enabled:
        asound.snd_lib_error_set_handler(None)

@contextmanager
def hidden_cursor():
    b = not sys.stdin.isatty() and sys.stdout.isatty() and prompt
    if b: sys.stdout.write("\033[?25l") # hide cursor
    try:
        yield
    finally:
        if b: sys.stdout.write("\033[?25h") # restore cursor

def init_sound(volume: float):
    global good_beep, bad_beep, all_good_beep
    import beeps
    beeps.init()

    all_good_beep = beeps.make_beep(1050, 12000, 0.07, 0.04)
    good_beep = beeps.make_beep(950, 12000, 0.08, 0.04)
    bad_beep = beeps.make_beep(210, 31000, 0.15)

    all_good_beep.set_volume(volume)
    good_beep.set_volume(volume)
    bad_beep.set_volume(volume)

opt_home_dir: Optional[str] = os.getenv('HOME')
if opt_home_dir is None: raise Exception('HOME not set')
home_dir: str = opt_home_dir

@click.command()
@click.option('--color', default=True, type=bool, show_default=True)
@click.option('--prompt', default=True, type=bool, show_default=True)
@click.option('--modes', default='default', type=str, show_default=True)
@click.option('--appdir', default=os.getenv('PWD'), type=str, show_default=True)
@click.option('--configdir', default=home_dir + '/.evc-voice-commander',type=str, show_default=True)
@click.option('--dryrun', default=False, type=bool, is_flag=True, show_default=True)
@click.option('--volume', default=(0 if sys.stdin.isatty() else 0.1), type=float, show_default=True)
    # stdin not being a tty is interpreted to mean the input is coming
    # from speech, hence we enable sound, but with low volume so our beeps are
    # (a) non-obnoxious, and
    # (b) won't interfere with speech recognition.
@click.argument('cmd', nargs=-1)
def evc(color, prompt, modes, configdir, appdir, dryrun, volume, cmd):
    global cmdline_modes, mode

    cmdline_modes = modes.split(',')
    mode = cmdline_modes[0]
    globals()['color'] = color
    globals()['configdir'] = configdir
    globals()['appdir'] = appdir
    eclbuiltins.dryrun = dryrun
    globals()['prompt'] = prompt

    initial_words = list(cmd)
    if volume != 0: init_sound(volume)

    try:
        load_config()
    except Exception as e:
        print("\nerror: invalid config:", e)
        return

    for m in cmdline_modes:
        if m not in eclc.modes:
            print(colored('error: no such mode: ' + m, 'red'))
            return

    with noalsaerr(volume != 0):
        with hidden_cursor():
            if initial_words:
                eval_command(initial_words, ' '.join(initial_words), cmdline_modes, False)
            else:
                import asyncio
                asyncio.get_event_loop().run_until_complete(process_lines(sys.stdin))

if __name__ == '__main__': evc()
