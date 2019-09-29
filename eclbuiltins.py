import termcolor
import subprocess
import time
import ecl
import util
import threading
import os
import sys
import util
import random
import pyautogui # type: ignore
from typing import Dict, List, Tuple, Callable, Optional

builtin_commands: List[ecl.BuiltinCommand] = []
global_builtins: List[ecl.BuiltinCommand] = []

dryrun = False

def make_builtin(pattern: str) -> Callable[[Callable], Callable]:
    def f(g):
        builtin_commands.append((ecl.parse_pattern(pattern), None, g))
        return g
    return f

def make_global_builtin(pattern: str) -> Callable[[Callable], Callable]:
    def f(g):
        global_builtins.append((ecl.parse_pattern(pattern), None, g))
        return g
    return f

def make_functional_builtin(pattern: str) -> Callable[[Callable], Callable]:
    def f(g):
        builtin_commands.append((ecl.parse_pattern(pattern), g, None))
        return g
    return f

def make_global_functional_builtin(pattern: str) -> Callable[[Callable], Callable]:
    def f(g):
        global_builtins.append((ecl.parse_pattern(pattern), g, None))
        return g
    return f

def key_by_name(name) -> str:
    return (extra_key_names[name] if name in extra_key_names else name)

def is_keyname(s) -> bool:
    return s in pyautogui.KEY_NAMES or s in extra_key_names

modifier_keys = ['shift', 'control', 'alt', 'wmkey']

extra_key_names: Dict[str, str] = {
    'space': ' ',
    'dollar': '$',
    'ampersand': '&',
    'hash': '#',
    'colon': ':',
    'semicolon': ';',
    'percent': '%',
    'plus': '+',
    'minus': '-',
    'period': '.',
    'comma': ',',
    'slash': '/',
    'control': 'ctrl',
    'wmkey': 'winleft',
    'single quote': "'",
    'double quote': '"',
}

builtin_types = {
    'word': lambda _: True,
    'number': lambda s: s.isdigit(),
    'positive': lambda s: s.isdigit() and int(s) > 0,
    'job': lambda n: n.isdigit() and int(n) in jobs,
    'key': is_keyname,
}

def is_builtin_type(t: ecl.Typename) -> bool:
    return t in builtin_types or t in ['mode', 'command']

#######################################

@make_builtin('set <word> <word>')
def cmd_set(ctx, _set, var, val):
    e = ctx['ecl']
    e.script_vars[var] = val

@make_functional_builtin('get <word>')
def cmd_get(ctx, _get, var):
    e = ctx['ecl']
    return e.script_vars[var] if var in e.script_vars else 'undefined'

jobs: Dict[int, str] = {}
next_job_nr = 0

@make_builtin('jobs')
def cmd_jobs(_):
    if jobs == {}:
        print('No active jobs.')
        return
    for n, cmd in jobs.items():
        print(str(n) + ':', cmd)

@make_builtin('cancel job <job>')
def cmd_cancel_job(_cancel, _job, n):
    n = int(n)
    if n in jobs: del jobs[n]

@make_builtin('window processes')
def cmd_window_processes(*_):
    _, processes = util.get_current_application()
    print('  ' + util.print_pstree(processes, 2))

@make_builtin('asynchronously <command>')
def cmd_asynchronously(ctx, _, cmd):
    global jobs, next_job_nr
    pr = ctx['ecl'].match_commands(util.split_expansion(cmd), [])
    n = next_job_nr
    next_job_nr += 1
    jobs[n] = cmd
    def f():
        # todo: VERY EVIL unsafe concurrent access to 'jobs' below
        status = 'finished'
        for act, w in pr.actions:
            if n not in jobs:
                status = 'canceled'
                break
            act(ctx, *w)
        if n in jobs: del jobs[n]
        print(' ', status + ':', ctx['ecl'].colored(cmd, 'green'))
        #if prompt: print_prompt()
    threading.Thread(target=f).start()

@make_builtin('run <word>+')
def cmd_run(_ctx, _, cmd):
    if dryrun:
        print("running", cmd)
        return
    subprocess.Popen(
        util.split_expansion(cmd), shell=False, close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)

@make_builtin('execute <word>+')
def cmd_execute(ctx, _, cmd):
    if dryrun:
        print("executing", cmd)
        return
    output = subprocess.Popen(
        util.split_expansion(cmd), shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE).stdout.read().decode('utf-8').strip()
    if output != '':
        print(ctx['ecl'].colored(output, 'magenta'))

startup_cwd = os.getcwd()

@make_builtin('restart commander')
def cmd_restart(_ctx, _restart, _commander):
    os.chdir(startup_cwd)
    os.execl(sys.argv[0], *sys.argv)

@make_builtin('keydown <key>')
def cmd_keydown(_ctx, _keydown, key_name):
    if not dryrun:
        pyautogui.keyDown(key_by_name(key_name))

@make_builtin('keyup <key>')
def cmd_keyup(_ctx, _keyup, key_name):
    if not dryrun:
        pyautogui.keyUp(key_by_name(key_name))

@make_builtin('shutdown commander')
def cmd_exit(_ctx, _shutdown, _commander):
    sys.stdout.write("\033[?25h") # restore cursor
    sys.exit(0)

@make_functional_builtin('<number> plus <number>')
def cmd_plus(_ctx, x, _p, y):
    return int(x) + int(y)

@make_functional_builtin('<number> minus <number>')
def cmd_minus(_ctx, x, _p, y):
    return int(x) - int(y)

@make_functional_builtin('<number> times <number>')
def num_times_num(_ctx, x, _p, y):
    return int(x) * int(y)

@make_functional_builtin('<number> is less than <number>')
def cmd_less_than(_ctx, x, _is, _less, _than, y):
    return "true" if int(x) < int(y) else "false"

@make_functional_builtin('<number> is greater than <number>')
def cmd_greater_than(_ctx, x, _is, _greater_, _than, y):
    return "true" if int(x) > int(y) else "false"

@make_functional_builtin('<word> equals <word>')
def cmd_equals(_ctx, x, _equals, y):
    return "true" if x == y else "false"

@make_functional_builtin('enumindex <word> <word>')
def cmd_enumindex(ctx, _, e: ecl.Typename, v: str):
    pattern: ecl.Pattern = ctx['ecl'].enums[e]
    form: ecl.Form = [[(v, False)]]
    return pattern.index(form) if form in pattern else -1

def print_builtin(e: ecl.Context, pattern: ecl.Pattern, func: Callable):
    import inspect
    print('\n' + e.color_commands(e.render_pattern(pattern)), '= ', end='')
    lines = inspect.getsource(func).split('\n')
    while lines and lines[-1] == '':
        lines = lines[:-1]
    if lines and lines[0].startswith('@make_builtin'):
        lines = lines[1:]
    if len(lines) == 1:
        print(lines[0].strip().rstrip(','))
    else:
        print('\n' + '\n'.join(map(lambda s: '    ' + s, lines)), end = '\n\n')

def strip_mode(words: List[str]) -> Tuple[str, List[str]]:
    if words[:2] == ['builtin', 'mode'] and len(words) > 3:
        return (words[2], words[3:])
    elif words[:1] == ['builtin']:
        return ('builtin', words[1:])
    raise Exception("cannot determine mode of command: " + str(words))

@make_global_builtin('define <command>')
def cmd_define(ctx, _, braced_cmd):
    ecl = ctx['ecl']

    cmd, rest = util.try_parse_braced_expr(braced_cmd)
    if cmd is None or rest != '': raise Exception("todo")

    while True:
        if len(cmd) != 1: break
        x, rest = util.try_parse_braced_expr(cmd[0])
        if x is None or rest != '': break
        cmd = x

    mode, cmd = strip_mode(cmd)
    if mode == 'builtin':
        for pattern, f, g in builtin_commands:
            pr = ecl.match_pattern(pattern, cmd, [])
            if pr.longest > 0 and not pr.missing and pr.error is None:
                if f is None: f = g
                if f is not None: print_builtin(ecl, pattern, f)
    else:
        for pattern, exp in ecl.modes[mode]:
            pr = ecl.match_pattern(pattern, cmd, [mode])
            if pr.longest > 0 and not pr.missing and pr.error is None:
                print('\nin ', end='')
                print(ecl.alias_definition_str(mode, pattern, exp, len('in ')))
                print()
                return

@make_global_functional_builtin('options')
def cmd_options(ctx, _):
    mm = ctx['enabled_modes']
    e = ctx['ecl']
    output = '\n'
    modes = e.modes

    def command_pattern(pat):
        return e.color_commands(e.italic_types_in_pattern(pat)) + ', '

    def simple_pattern(pat: ecl.Pattern):
        return e.render_pattern(pat) + ', '

    for m in mm:
        indent = len(m) + len("in : ")
        l = []
        simples = []
        for pat, exp in modes[m]:
            if exp == 'builtin press $0': # todo
                if len(pat) == 1:
                    for alt in pat[0]:
                        simples.append(simple_pattern(alt))
                else:
                    simples.append(simple_pattern(pat))
            elif not pat.startswith('_'):
                for form in pat.split('/'):
                    if ' ' in form:
                        l.append(command_pattern(form))
                    else:
                        for alt in form.split('|'):
                            l.append(command_pattern(alt))
        l += simples
        #for pat, exp in modes[m]:
        #    if pat in modes and pat != m and exp == 'builtin mode ' + pat:
        #        l.append(e.color_mode(pat) + ', ')
        if l:
            output += 'in ' + e.color_mode(m) + ': '
            s = l[-1]; l[-1] = s[:-2] # remove last comma
            output += util.indented_and_wrapped(l, indent) + '\n\n'

    l = []#[e.italic_types_in_pattern(b) + ', ' for b, _ in builtin_commands if ecl.is_global_builtin_pattern(b)] # todo
    if l:
        output += 'global: '
        indent = len('global: ')
        s = l[-1]; l[-1] = s[:-2] # remove last comma
        output += util.indented_and_wrapped(l, indent) + '\n\n'
    return output

@make_builtin('text <word>+')
def cmd_text(_ctx, _, s):
    if dryrun:
        print("entering text", s)
    else:
        pyautogui.press([c for c in s])

builtin_commands.append((ecl.parse_pattern('mode <mode>'), None, None))

@make_functional_builtin('return <word>')
def cmd_return(_ctx, _, w):
    return w

@make_builtin('press <key>+')
def cmd_press(_ctx, _, spec):
    if dryrun:
        print("pressing", spec)
        return
    modifiers = []
    for key in util.split_expansion(spec):
        if key in modifier_keys:
            modifiers.append(key)
        else:
            if not modifiers:
                key = key_by_name(key)
                pyautogui.press([key])
            else:
                keys = list(map(key_by_name, modifiers + [key]))
                for k in keys: pyautogui.keyDown(k, pause=0.02)
                for k in reversed(keys): pyautogui.keyUp(k, pause=0.02)
                modifiers = []

@make_builtin('print <word>+')
def cmd_print(ctx, _, s):
    print(ctx['ecl'].colored(' '.join(util.split_expansion(s)), 'magenta'))

@make_functional_builtin('randomint <number>')
def cmd_randomint(_ctx, _randomint, max):
    return str(random.randint(0, int(max) - 1))

def run_actions(ctx, actions):
    for act, args in actions:
        act(ctx, *args)

@make_builtin('<number> times <command>')
def cmd_times_cmd(ctx, n, _times, cmd):
    global jobs, next_job_nr
    pr = ctx['ecl'].match_commands(util.split_expansion(cmd), [])
    for _ in range(int(n)):
        run_actions(ctx, pr.actions)
