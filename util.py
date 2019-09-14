import shutil
import re
import collections
import subprocess
import time
import sys

def escape(s):
    x = ''
    for c in s:
        if c == '"': x += '\\"'
        elif c == '\\': x += '\\\\'
        else: x += c
    return x

def quote_if_necessary(s):
    if ' ' not in s and '"' not in s: return s
    return '"' + escape(s) + '"'

ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
def strip_markup(s):
    return ansi_escape.sub('', s)

def indented_and_wrapped(l, n):
    cols = shutil.get_terminal_size().columns
    cur = n
    r = ''
    l = [x + ' ' for x in ' '.join(l).split()]
    while l != []:
        s = l[0]
        w = len(strip_markup(s))
        if (cur + w <= cols) or r == '' or r.endswith('\n' + ' ' * n):
            cur += w
            r += s
            l = l[1:]
        else:
            r += '\n' + ' ' * n
            cur = n
    return r

def process_family(pid):
    import psutil
    children = collections.defaultdict(list)
    for p in psutil.process_iter():
        try:
            children[p.ppid()].append(p.pid)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
    start = [pid]
    return pstree_branch(start, children)

terminal_apps = ['urxvt']

def pstree_branch(pids, children, stop_on_terminal=False):
    import psutil
    r = {}
    for pid in pids:
        pro = psutil.Process(pid)
        name = pro.name()
        if stop_on_terminal and name in terminal_apps: continue
        b = (pstree_branch(children[pid], children, True) if pid in children else {})
        b['name'] = name
        try: b['cwd'] = pro.cwd()
        except: pass
        b['pid'] = pid
        r[pid] = b
    return r

def occurs_in_branch(x, processes):
    for k, v in processes.items():
        if k == 'name':
            if v == x: return True
        elif occurs_in_branch(x, v):
            return True
    return False

def occurs_as_leaf_in_branch(x, processes):
    if len(processes) == 1 and 'name' in processes and processes['name'] == x:
        return True
    for k, v in processes.items():
        if k != 'name' and occurs_as_leaf_in_branch(x, v):
            return True
    return False

def split_expansion(s):
    if s == '': return []
    if s[0] == '"':
        x = ''
        i = 1
        while s[i] != '"':
            if s[i:].startswith('\\"'):
                x += '"'
                i += 2
            elif s[i:].startswith('\\\\'):
                x += '\\'
                i += 2
            else:
                x += s[i]
                i += 1
        if i + 1 == len(s): return [x]
        afterspace = i + 1
        while s[afterspace] == ' ': afterspace += 1
        return [x] + split_expansion(s[afterspace:])
    space = s.find(' ')
    if space == -1: return [s]
    afterspace = space + 1
    while afterspace < len(s) and s[afterspace] == ' ': afterspace += 1
    return [s[:space]] + split_expansion(s[afterspace:])

def simple_subprocess(cmd):
    p = subprocess.Popen(cmd, shell=True,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.stdout.read().decode('utf-8').rstrip()

def print_pstree(t, indent=0):
    r = ''
    pre = ''
    corner = ' └ '
    if 'pid' in t:
        name = (t['name'] if 'name' in t else '?')
        r += name + ' (pid: ' + str(t['pid'])
        if 'cwd' in t: r += ', cwd: ' + t['cwd']
        r += ')\n'
        pre = ' ' * indent + corner
        indent += len(corner)
    for k, v in t.items():
        if type(k) is int:
            r += pre + print_pstree(v, indent)
    return r

def italic(s):
    turn_on_italic = "\x1B[3m"
    turn_off_italic = "\x1B[23m"
    return turn_on_italic + s + turn_off_italic

def sound(name, count=1, wait=True):
    if count == 0: return
    import pygame
    pygame.mixer.music.load("sounds/" + name)
    for i in range(0, count):
        pygame.mixer.music.play()
        if wait:
            while pygame.mixer.music.get_busy(): time.sleep(0.01)
            time.sleep(0.1)

def clear_line():
    if not sys.stdout.isatty(): return
    cols = shutil.get_terminal_size().columns
    print('\r' + ' ' * cols + '\r', end='')
    sys.stdout.flush()

def truncate(s, n):
    return (s[:n-3] + '...' if len(s) > n else s)

def get_current_application():
    current_windowtitle = ''
    current_windowprocesses = {}
    active_win = simple_subprocess('xdotool getactivewindow')
    if active_win == '': return
    current_windowtitle = simple_subprocess('xdotool getwindowname ' + active_win)
    current_windowpid = simple_subprocess('xdotool getwindowpid ' + active_win)
    if current_windowpid != '':
        current_windowprocesses = process_family(int(current_windowpid))
    return (current_windowtitle, current_windowprocesses)
