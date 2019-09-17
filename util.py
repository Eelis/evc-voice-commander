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
    x = try_parse_braced_expr(s)
    if x is not None:
        _, rest = x
        if rest == '': return s
    if ' ' in s or '"' in s or '{' in s or '}' in s:
        return '"' + escape(s) + '"'
    return s

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
        try:
            pro = psutil.Process(pid)
            name = pro.name()
            if stop_on_terminal and name in terminal_apps: continue
            b = (pstree_branch(children[pid], children, True) if pid in children else {})
            b['name'] = name
            try: b['cwd'] = pro.cwd()
            except: pass
            b['pid'] = pid
            r[pid] = b
        except psutil.NoSuchProcess:
            pass
    return r

def occurs_in_branch(x, processes):
    for k, v in processes.items():
        if k == 'name':
            if v == x: return True
        elif type(v) is dict and occurs_in_branch(x, v):
            return True
    return False

def cwd_of_branch(processes):
    for v in processes.values():
        if type(v) is dict:
            t = cwd_of_branch(v)
            if t is not None: return t
    return (processes['cwd'] if 'cwd' in processes else None)

def occurs_as_leaf_in_branch(x, processes):
    children = False
    for v in processes.values():
        if type(v) is dict:
            children = True
            if occurs_as_leaf_in_branch(x, v):
                return True
    return not children and 'name' in processes and processes['name'] == x

def parse_quoted_string(s):
    s = s[1:] # skip first "
    x = ''
    while not s.startswith('"'):
        if s.startswith('\\"'):
            x += '"'
            s = s[2:]
        elif s.startswith('\\\\'):
            x += '\\'
            s = s[2:]
        else:
            x += s[0]
            s = s[1:]
    s = s[1:] # skip final "
    return (x, s)

def parse_basic_expression(s):
    curly_depth = 0
    r = []
    x = ''
    while s != '':
        if s[0] == ' ':
            if curly_depth == 0: break
            x += ' '
            s = s[1:]
        elif s[0] == '}':
            if curly_depth == 0:
                raise Exception("unmatched }")
            curly_depth -= 1
            x += '}'
            s = s[1:]
        elif s[0] == '{':
            curly_depth += 1
            x += '{'
            s = s[1:]
        elif s[0] == '"':
            if curly_depth != 0: x += '"'
            y, s = parse_quoted_string(s)
            x += y
            if curly_depth != 0: x += '"'
        else:
            x += s[0]
            s = s[1:]
    return (x, s)

def try_parse_braced_expr(s):
    if not s.startswith('{'):
        return None
    r = []
    s = s[1:].lstrip()
    while not s.startswith('}'):
        if s == '': return None
        y, s = parse_basic_expression(s)
        if y == []: return None
        r += [y]
        s = s.lstrip()
    return (r, s[1:])

def split_expansion(s):
    s = s.lstrip()
    r = []
    while s != '':
        y, s = parse_basic_expression(s)
        r += [y]
        s = s.lstrip()
    return r

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
    if active_win != '':
        current_windowtitle = simple_subprocess('xdotool getwindowname ' + active_win)
        current_windowpid = simple_subprocess('xdotool getwindowpid ' + active_win)
        if current_windowpid != '':
            current_windowprocesses = process_family(int(current_windowpid))
    return (current_windowtitle, current_windowprocesses)

def ordinal(s):
    return "first second third fourth fifth sixth seventh eighth ninth tenth eleventh".split().index(s)
