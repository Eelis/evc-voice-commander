import shutil
import re
import collections
import subprocess
import sys
from typing import Dict, List, Tuple, Optional

def escape(s: str) -> str:
    def f(c: str) -> str:
        if c == '"': return '\\"'
        elif c == '\\': return '\\\\'
        else: return c
    return ''.join(map(f, s))

def quote_if_necessary(s: str) -> str:
    x = try_parse_braced_expr(s)
    if x is not None:
        _, rest = x
        if rest == '': return s
    if ' ' in s or '"' in s or '{' in s or '}' in s:
        return '"' + escape(s) + '"'
    return s

ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
def strip_markup(s: str) -> str:
    return ansi_escape.sub('', s)

def column_width(s: str) -> int:
    return len(strip_markup(s))

def indented_and_wrapped(l: List[str], n: int) -> str:
    cols = (shutil.get_terminal_size().columns if sys.stdout.isatty() else 120)
    cur = n
    r = ''
    while l != []:
        s = l[0]
        w = column_width(s)
        if (cur + w <= cols) or r == '' or r.endswith('\n' + ' ' * n):
            cur += w
            r += s
            l = l[1:]
        else:
            r += '\n' + ' ' * n
            cur = n
    return r

def process_family(pid):
    import psutil # type: ignore
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

def parse_quoted_string(s: str) -> Tuple[str, str]:
    s = s[1:] # skip first "
    x: List[str] = []
    append = x.append
    while not s.startswith('"'):
        if s.startswith('\\"'): append('"'); s = s[2:]
        elif s.startswith('\\\\'): append('\\'); s = s[2:]
        elif s == '': raise Exception('missing "')
        else: append(s[0]); s = s[1:]
    s = s[1:] # skip final "
    return (''.join(x), s)

def parse_basic_expression(s: str) -> Tuple[str, str]:
    curly_depth = 0
    x: List[str] = []
    append = x.append
    while s != '':
        if s[0] == ' ':
            if curly_depth == 0: break
            append(' ')
            s = s[1:]
        elif s[0] == '}':
            if curly_depth == 0:
                raise Exception("unmatched }")
            curly_depth -= 1
            append('}')
            s = s[1:]
        elif s[0] == '{':
            curly_depth += 1
            append('{')
            s = s[1:]
        elif s[0] == '"':
            if curly_depth != 0: append('"')
            y, s = parse_quoted_string(s)
            append(y)
            if curly_depth != 0: append('"')
        else:
            append(s[0])
            s = s[1:]
    return (''.join(x), s)

def try_parse_braced_expr(s: str) -> Optional[Tuple[List[str], str]]:
    if not s.startswith('{'):
        return None
    r: List[str] = []
    s = s[1:].lstrip()
    append = r.append
    while not s.startswith('}'):
        if not s: return None
        y, s = parse_basic_expression(s)
        if not y: return None
        append(y)
        s = s.lstrip()
    return (r, s[1:])

def split_expansion(s: str) -> List[str]:
    s = s.lstrip()
    r: List[str] = []
    append = r.append
    while s:
        y, s = parse_basic_expression(s)
        append(y)
        s = s.lstrip()
    return r

def simple_subprocess(cmd: str) -> str:
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

def italic(s: str) -> str:
    turn_on_italic = "\x1B[3m"
    turn_off_italic = "\x1B[23m"
    return turn_on_italic + s + turn_off_italic

def clear_line() -> None:
    if not sys.stdout.isatty(): return
    sys.stdout.write('\033[2K\033[1G')
    sys.stdout.flush()

def truncate(s: str, n: int) -> str:
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

def ordinal(s: str) -> int:
    return "first second third fourth fifth sixth seventh eighth ninth tenth eleventh".split().index(s)

def commas_or(x: List[str]) -> str:
    if len(x) == 1: return x[0]
    if len(x) == 2: return x[0] + ' or ' + x[1]
    return x[0] + ', ' + commas_or(x[1:])

def a_or_an(s: str) -> str:
    return 'an' if s.startswith('aeoiu') else 'a'
