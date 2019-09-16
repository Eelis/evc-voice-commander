import termcolor
import subprocess
import time
import ecl
import util
import threading
import os
import sys
import util

builtin_commands = {}

dryrun = False

def make_builtin(pattern):
    def f(g):
        builtin_commands[pattern] = (None, g)
        return g
    return f

def make_functional_builtin(pattern):
    def f(g):
        builtin_commands[pattern] = (g, None)
        return g
    return f

def key_by_name(name):
    return (extra_key_names[name] if name in extra_key_names else name)

def is_keyname(s):
    return s in keynames or s in extra_key_names

def is_keyspec(spec):
    for combo in spec.split(','):
        mult = combo.find('*')
        if mult != -1:
            if not combo[:mult].isdigit(): return False
            combo = combo[mult+1:]
        for k in combo.split('+'):
            if not is_keyname(k): return False
    return True

keynames = ['\t', '\n', '\r', ' ', '!', '"', '#', '$', '%', '&', "'", '(',
    ')', '*', '+', ',', '-', '.', '/', '0', '1', '2', '3', '4', '5', '6', '7',
    '8', '9', ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '^', '_', '`',
    'a', 'b', 'c', 'd', 'e','f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o',
    'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', '{', '|', '}', '~',
    'accept', 'add', 'alt', 'altleft', 'altright', 'apps', 'backspace',
    'browserback', 'browserfavorites', 'browserforward', 'browserhome',
    'browserrefresh', 'browsersearch', 'browserstop', 'capslock', 'clear',
    'convert', 'ctrl', 'ctrlleft', 'ctrlright', 'decimal', 'del', 'delete',
    'divide', 'down', 'end', 'enter', 'esc', 'escape', 'execute', 'f1', 'f10',
    'f11', 'f12', 'f13', 'f14', 'f15', 'f16', 'f17', 'f18', 'f19', 'f2', 'f20',
    'f21', 'f22', 'f23', 'f24', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9',
    'final', 'fn', 'hanguel', 'hangul', 'hanja', 'help', 'home', 'insert', 'junja',
    'kana', 'kanji', 'launchapp1', 'launchapp2', 'launchmail',
    'launchmediaselect', 'left', 'modechange', 'multiply', 'nexttrack',
    'nonconvert', 'num0', 'num1', 'num2', 'num3', 'num4', 'num5', 'num6',
    'num7', 'num8', 'num9', 'numlock', 'pagedown', 'pageup', 'pause', 'pgdn',
    'pgup', 'playpause', 'prevtrack', 'print', 'printscreen', 'prntscrn',
    'prtsc', 'prtscr', 'return', 'right', 'scrolllock', 'select', 'separator',
    'shift', 'shiftleft', 'shiftright', 'sleep', 'space', 'stop', 'subtract', 'tab',
    'up', 'volumedown', 'volumemute', 'volumeup', 'win', 'winleft', 'winright', 'yen',
    'command', 'option', 'optionleft', 'optionright']
        # these coincide with names in pyautogui
        # (which we don't want to import just for this list because it takes ~60 milliseconds)

extra_key_names = {
    'space': ' ',
    'dollar': '$',
    'ampersand': '&',
    'hash': '#',
    'colon': ':',
    'semicolon': ';',
    'percent': '%',
    'period': '.',
    'comma': ',',
    'slash': '/',
    'wmkey': 'winleft'
}

builtin_types = {
    'word': lambda _: True,
    'number': lambda s: s.isdigit(),
    'positive': lambda s: s.isdigit() and int(s) > 0,
    'job': lambda n: n.isdigit() and int(n) in jobs,
    'key': is_keyname,
    'keys': is_keyspec,
}

#######################################

@make_builtin('set <word> <word>')
def cmd_set(ctx, _set, var, val):
    e = ctx['ecl']
    e.script_vars[var] = val

@make_functional_builtin('get <word>')
def cmd_get(ctx, _get, var):
    e = ctx['ecl']
    return e.script_vars[var] if var in e.script_vars else 'undefined'

jobs = {}
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
def cmd_asynchronously(ctx, _, mode, cmd):
    global jobs, next_job_nr
    pr = ctx['ecl'].match_command(util.split_expansion(cmd), [mode])
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

@make_builtin('run <words>')
def cmd_run(_ctx, _, cmd):
    if dryrun: return
    subprocess.Popen(
        util.split_expansion(cmd), shell=False, close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)

@make_builtin('execute <words>')
def cmd_execute(ctx, _, cmd):
    if dryrun: return
    output = subprocess.Popen(
        util.split_expansion(cmd), shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE).stdout.read().decode('utf-8').strip()
    cmd_print(ctx, 'print', output)

startup_cwd = os.getcwd()

@make_builtin('restart commander')
def cmd_restart(_ctx, _restart, _commander):
    os.chdir(startup_cwd)
    os.execl(sys.argv[0], *sys.argv)

@make_builtin('keydown <key>')
def cmd_keydown(_ctx, _keydown, key_name):
    if not dryrun:
        import pyautogui
        pyautogui.keyDown(key_by_name(key_name))

@make_builtin('keyup <key>')
def cmd_keyup(_ctx, _keyup, key_name):
    if not dryrun:
        import pyautogui
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
def cmd_less_than(_ctx, x, _is, _greater_, _than, y):
    return "true" if int(x) > int(y) else "false"

@make_functional_builtin('enumindex <word> <word>')
def cmd_enumindex(ctx, _, e, v):
    l = ctx['ecl'].enums[e].split('/')
    return l.index(v) if v in l else -1

def print_builtin(e, pattern):
    import inspect
    _, func = builtin_commands[pattern]
    print('\n' + e.color_commands(pattern), '= ', end='')
    lines = inspect.getsource(func).split('\n')
    while lines != [] and lines[-1] == '':
        lines = lines[:-1]
    if lines != [] and lines[0].startswith('@make_builtin'):
        lines = lines[1:]
    if len(lines) == 1:
        print(lines[0].strip().rstrip(','))
    else:
        print('\n' + '\n'.join(map(lambda s: '    ' + s, lines)), end = '\n\n')

@make_builtin('define <command>')
def cmd_define(ctx, _, _cmdmode, cmd):
    ecl = ctx['ecl']
    em = ctx['enabled_modes']
    args = util.split_expansion(cmd)
    for m in em:
        for pattern in ecl.modes[m].keys():
            pr = ecl.match_pattern(pattern, args, em)
            if pr.longest > 0 and pr.missing == []:
                print('\nin ', end='')
                print(ecl.alias_definition_str(m, pattern, len('in ')))
                print()
                return
    for pattern, _ in builtin_commands.items():
        pr = ecl.match_pattern(pattern, args, em)
        if pr.longest > 0 and pr.missing == []:
            print_builtin(ecl, pattern)

@make_builtin('options')
def cmd_options(ctx, _):
    mm = ctx['enabled_modes']
    e = ctx['ecl']
    print()
    builtins_displayed = []
    modes = e.modes

    def command_pattern(pat):
        return e.color_commands(e.italic_types(pat)) + ', '

    def simple_pattern(pat):
        return e.italic_types(pat) + ', '

    for m in mm:
        indent = len(m) + len("in : ")
        l = []
        simples = []
        for pat, exp in modes[m].items():
            if exp == 'builtin press $0': # todo
                if len(pat.split()) == 1:
                    for alt in pat.split('|'):
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
        for pat, exp in modes[m].items():
            if pat in modes and pat != m and exp == 'builtin mode ' + pat:
                l.append(e.color_mode(pat) + ', ')
        if l != []:
            print('in', e.color_mode(m) + ': ', end='')
            s = l[-1]; l[-1] = s[:-2] # remove last comma
            print(util.indented_and_wrapped(l, indent), end='\n\n')

    l = [e.italic_types(b) + ', ' for b in builtin_commands.keys() if ecl.is_global_builtin_pattern(b)]
    if l != []:
        print('global: ', end='')
        indent = len('global: ')
        s = l[-1]; l[-1] = s[:-2] # remove last comma
        print(util.indented_and_wrapped(l, indent), end='\n\n')

@make_builtin('text <words>')
def cmd_text(_ctx, _, s):
    if not dryrun:
        import pyautogui
        pyautogui.press([c for c in s])

builtin_commands['mode <mode>'] = (None, None)

@make_functional_builtin('return <word>')
def cmd_return(_ctx, _, w):
    return w

@make_functional_builtin('active <mode>')
def cmd_active(ctx, _, m):
    return "true" if m in ctx['enabled_modes'] else "false"

@make_builtin('press <keys>')
def cmd_press(_ctx, _, spec):
    if dryrun: return
    import pyautogui
    for combo in spec.split(','):
        times = 1
        mult = combo.find('*')
        if mult != -1:
            times = int(combo[:mult])
            combo = combo[mult+1:]
        keys = combo.split('+')
        if len(keys) == 1:
            k = key_by_name(keys[0])
            pyautogui.press([k] * times)
        else:
            kk = list(map(key_by_name, keys))
            for i in range(times):
                for k in kk: pyautogui.keyDown(k)
                time.sleep(0.05)
                for k in reversed(kk): pyautogui.keyUp(k)

@make_builtin('print <words>')
def cmd_print(ctx, _, s):
    print(ctx['ecl'].colored(' '.join(util.split_expansion(s)), 'magenta'))
