import shutil
import re
import collections

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
    names = {}
    for p in psutil.process_iter():
        try:
            children[p.ppid()].append(p.pid)
            names[p.pid] = p.name()
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
    start = [pid]
    return pstree_branch(start, names, children)

terminal_apps = ['urxvt']

def pstree_branch(pids, names, children, stop_on_terminal=False):
    r = {}
    for pid in pids:
        name = (names[pid] if pid in names else '?')
        if stop_on_terminal and name in terminal_apps: continue
        b = (pstree_branch(children[pid], names, children, True) if pid in children else {})
        b['name'] = name
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
    if 'name' in t:
        print(t['name'])
    else:
        print('?')
    for k, v in t.items():
        if k != 'name':
            print(' ' * indent + '- ', end='')
            print_pstree(v, indent + 2)

def italic(s):
    turn_on_italic = "\x1B[3m"
    turn_off_italic = "\x1B[23m"
    return turn_on_italic + s + turn_off_italic
