import ecl
import subprocess
import util

def linear_suggestions(suggestions):
    r, type_sugs, _ = suggestions
    return r + [x for _, l in type_sugs for x, _ in l]

def only_choice(sugs):
    lits, types, empty_types = sugs
    if empty_types != []: return None
    if len(lits) == 1 and types == []:
        return lits[0][0]
    return None

def types_in_param(param):
    r = []
    for alt in ecl.alternatives(param):
        if alt.endswith('+'): alt = alt[:-1]
        t = ecl.parse_type(alt)
        if t is not None: r.append(t)
    return r

def literals_in_param(param):
    r = []
    for alt in ecl.alternatives(param):
        if alt.endswith('+'): alt = alt[:-1]
        if ecl.parse_type(alt) is None: r.append(alt)
    return r

def definite_missing_arguments(context, goodwords, enabled_modes, handle_builtins):
    more = []
    incomplete = True
    while True:
        pr = context.match_commands(goodwords + more, enabled_modes, handle_builtins)
        if pr.longest == len(goodwords + more) and pr.error is None and pr.missing == []:
            incomplete = False
            break
        if pr.longest < len(goodwords) + len(more): break
        if pr.missing == [] or pr.error is not None: break
        sugs = get_suggestions(context, goodwords + more, pr.missing, enabled_modes, handle_builtins)
        c = only_choice(sugs)
        if c is None: break
        more += c
    return (more, incomplete)

def get_suggestions(context, goodwords, missing, enabled_modes, handle_builtins):
    if missing == []:
        return ([], [], [])

    # find all types the command could continue with:
    types_todo = []
    for param in missing: types_todo += types_in_param(param)
    types_done = []
    while types_todo != []:
        t, *types_todo = types_todo
        if t in types_done: continue
        types_done.append(t)
        if t in context.enums:
            for form in ecl.forms(context.enums[t]):
                types_todo += types_in_param(ecl.params(form)[0])

    # find their completions:
    rt = []
    for type in types_done:
        l = []
        if type in context.completions:
            l = subprocess.Popen(context.completions[type], shell=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL).stdout.read().decode('utf-8').strip().split('\n')
        if type in context.enums:
            for form in ecl.forms(context.enums[type]):
                l += literals_in_param(ecl.params(form)[0])
        if l != [] or type not in context.enums:
            ul = []
            for x in l:
                more, incomplete = definite_missing_arguments(context, goodwords + [x], enabled_modes, handle_builtins)
                ul.append(([x] + more, incomplete))
            rt.append((type, ul))

    # get literals (that aren't already listed for one of the types):
    lits = list(set(
        [l for param in missing
            for l in literals_in_param(param)
             if not any([l == y for _, x in rt for y, _ in x])]))
    lits.sort()

    # extend literals
    newlits = []
    for x in lits:
        y, incomplete = definite_missing_arguments(context, goodwords + [x], enabled_modes, handle_builtins)
        newlits.append(([x] + y, incomplete))

    # partition types by whether they have suggestions:
    ne = [(x, l) for x, l in rt if l != []]
    e = [x for x, l in rt if l == []]

    return (newlits, ne, e)

def print_suggestions(eclc, suggestions):

    def decorate_type(t):
        return eclc.italic_types_in_alternative('<' + t + '>')

    literal_sugs, type_sugs, emptytype_sugs = suggestions
    if len(literal_sugs) == 1 and type_sugs == [] and emptytype_sugs == []:
        print(eclc.colored("error: did you mean '" + ' '.join(literal_sugs[0][0]) + "'?", 'red'))
    elif literal_sugs == [] and len(emptytype_sugs) == 1 and type_sugs == []:
        t = emptytype_sugs[0]
        print(eclc.colored('error: expected ' + util.a_or_an(t) + ' ' + decorate_type(t), 'red'))
    elif literal_sugs == [] and emptytype_sugs == [] and len(type_sugs) == 1:
        t, sugs = type_sugs[0]
        print(eclc.colored('error: expected ' + util.a_or_an(t) + ' ' + decorate_type(t) + ':\n  ', 'red'), end='')
        i = 1
        first = True
        for s, more in sugs:
            if not first: print(' / ', end='')
            print(eclc.color_commands(s) + ' ', end='')
            if more: print('... ', end='')
            print("(" + str(i) + ')', end='')
            i += 1
            first = False
        print()
    else:
        print(eclc.colored('error: expected:', 'red'))
        i = 1
        for l, incomplete in literal_sugs:
            print('-', eclc.color_commands(' '.join(l)), end='')
            if incomplete: print(' ...', end='')
            print(' (' + str(i) + ')')
            i += 1
        for t, sugs in type_sugs:
            print('-', util.a_or_an(t), eclc.color_commands(decorate_type(t)), end='')
            print(': ', end='')
            first = True
            for s, more in sugs:
                if not first: print(' / ', end='')
                print(eclc.color_commands(' '.join(s)) + ' ', end='')
                if more: print('... ', end='')
                print("(" + str(i) + ')', end='')
                i += 1
                first = False
            print()
        if emptytype_sugs != []:
            print('-', util.commas_or([util.a_or_an(t) + ' ' + eclc.color_commands(decorate_type(t)) for t in emptytype_sugs]))
