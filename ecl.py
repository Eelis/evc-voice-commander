from eclbuiltins import builtin_commands, builtin_types
import util
import termcolor

class ParseResult():
    def __init__(self):
        self.longest = 0
        self.missing = []
        self.actions = []
        self.new_mode = None
        self.error = None
        self.retval = None

    def try_improve(self, other):
        if other.longest > self.longest:
            self.longest = other.longest
            self.missing = other.missing
            self.actions = other.actions
            self.new_mode = other.new_mode
            self.error = other.error
            self.retval = other.retval


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

global_builtins = ['options', 'define', 'builtin']

def is_global_builtin_pattern(pat):
    pat = pat.split()
    while pat != [] and pat[0][0] == '<':
        pat = pat[1:]
    return pat != [] and pat[0] in global_builtins

class EclContext():
    def __init__(self):
        self.modes = {}
        self.enums = {}
        self.script_vars = {}
        self.color = True

    def colored(self, s, c):
        if not self.color: return s
        return termcolor.colored(s, c)

    def color_mode(self, m):
        return self.colored(m, 'cyan')

    def color_commands(self, p):
        return self.colored(p, 'magenta')


    def italic(self, s):
        turn_on_italic = "\x1B[3m"
        turn_off_italic = "\x1B[23m"
        return turn_on_italic + s + turn_off_italic if self.color else s

    def italic_types(self, pattern):
        return '/'.join(
                [' '.join(
                    ['|'.join(
                        [ (self.italic(alt[1:-1]) if alt.startswith('<') else alt)
                            for alt in param.split('|')
                        ])
                        for param in form.split(' ')
                    ])
                    for form in pattern.split('/')])

    def alias_definition_str(self, mode, pattern, start_column=0):
        expansion = self.modes[mode][pattern]
        pat = self.italic_types(pattern)
        r = self.color_mode(mode) + ' ' + self.color_commands(pat) + ' = '
        indent = start_column + len(mode) + len(util.strip_markup(pat)) + len("  = ")
        l = [self.color_commands(e) + ' ' for e in expansion.split()] # todo: handle '' args
        s = l[-1]; l[-1] = s[:-1] # remove last space
        return r + util.indented_and_wrapped(l, indent)

    def handle_alias(self, input, enabled_modes):
        current_mode = enabled_modes[0]
        patterns = [(pat, (m, exp)) for m in enabled_modes for pat, exp in self.modes[m].items()]
        r = ParseResult()
        r.new_mode = current_mode

        r.longest, vars, r.missing, pattern, x = \
            self.longest_matching_pattern(patterns, input, enabled_modes)

        if r.longest == 0 or r.missing != []: return r

        m, expansion = x

        errorpart = 'command ' + self.colored(' '.join(input[:r.longest]), 'green') + ' matched alias:\n' + \
                    '  ' + self.alias_definition_str(m, pattern, 4) + '\n'

        nvars = self.script_vars.copy()
        nvars['*'] = ' '.join(map(quote_if_necessary, vars[:r.longest]))
        for i, v in enumerate(vars):
            nvars[str(i)] = v

        replaced = ''
        quoted = False
        while expansion != '':
            if expansion[0] == '"':
                quoted = not quoted
                replaced += '"'
                expansion = expansion[1:]
            elif expansion.startswith('$'):
                i = 1
                while i < len(expansion) and (expansion[i].isalnum() or expansion[i] == '*'):
                    i += 1
                varname = expansion[1:i]
                expansion = expansion[i:]
                if varname not in nvars:
                    r.error = errorpart + self.colored('undefined variable $' + varname, 'red')
                    return r
                replaced += (escape(nvars[varname]) if quoted else nvars[varname])
            else:
                replaced += expansion[0]
                expansion = expansion[1:]

        exp = util.split_expansion(replaced)
        sub = self.process(exp, [m], True)

        if sub.missing == []:
            r.actions = sub.actions
            r.new_mode = sub.new_mode
            r.retval = sub.retval # todo: maybe there are better choices here

            if sub.error is not None:
                r.error = errorpart + sub.error
        else:
            qexp = list(map(quote_if_necessary, exp))
            s = util.indented_and_wrapped(
                [self.colored(s, 'green') + ' ' for s in qexp[:sub.longest]] +
                [self.colored(s, 'red') + ' ' for s in qexp[sub.longest:]], 4)
            r.error = errorpart + \
                '  invalid expansion:\n    ' + s + '\n' + \
                '  ' + ('missing ' if sub.longest == len(exp) else 'expected ') + \
                ' or '.join(map(self.italic_types, sub.missing)) + '\n'

        return r

    def process(self, words, enabled_modes, handle_builtins=True):
        if words == []: return ParseResult()
        cmd, *_ = words

        r = self.handle_alias(words, enabled_modes)
        if handle_builtins and r.error is None:
            r.try_improve(self.handle_builtin_command(words, enabled_modes, True))

        if r.missing != []: return r

        if r.longest == 0:
            r.missing = ['<command>']
            r.actions = []
            r.new_mode = enabled_modes[0]
        else:
            if r.new_mode is not None:
                enabled_modes[0] = r.new_mode

            if r.longest != len(words) and r.error is None:
                r2 = self.process(words[r.longest:], enabled_modes, True)
                r.longest += r2.longest
                r.missing = (r2.missing if r2.longest != 0 else ['<command>'])
                r.actions += r2.actions
                r.new_mode = r2.new_mode
                r.error = r2.error
                r.retval = r2.retval

        return r

    def params_matched(self, params, args, enabled_modes):
        vars = []
        args_matched = 0
        missing = []
        i = 0
        while i < len(params):
            if args == []:
                break

            varieties = []

            if args[:1] == ['evaluate']:
                sub = args[1:]
                pr = self.process(sub, enabled_modes, True)
                varieties.append((pr.longest, pr.missing, [str(pr.retval)] + sub[pr.longest:], [], i))
                    # not i+1 because still on same parameter
                    # we would need to add 1 to pr.longest to account for having consumed 'evaluate',
                    # but this is canceled out by a -1 to account for the newly inserted argument.

            if params[i] == '<command>':
                pr = self.process(args, enabled_modes, True)
                varieties.append(
                    ( pr.longest, pr.missing, args[pr.longest:]
                    , [enabled_modes[0], ' '.join(map(quote_if_necessary, args[:pr.longest]))]
                    , i + 1))
            elif params[i] == '<words>':
                varieties.append((len(args), [], [], [' '.join(map(quote_if_necessary, args))], i + 1))
            else:
                am, miss = self.param_matched(params[i], args, enabled_modes)
                varieties.append((am, miss, args[am:], [' '.join(args[:am])], i + 1))

            longest_here = 0
            vars_here = []

            for n, mis, a, v, ni in varieties:
                if n == longest_here:
                    if mis == [] and missing != []:
                        missing = []
                        args = a
                        vars_here = v
                        i = ni
                    else:
                        missing += mis
                elif n > longest_here:
                    longest_here = n
                    missing = mis
                    args = a
                    vars_here = v
                    i = ni

            vars += vars_here
            args_matched += longest_here

            if missing != []: # or i is None:
                break

        if i < len(params) and missing == []:
            missing = [params[i]]
        return (args_matched, missing, vars)

    def handle_builtin_command(self, input, enabled_modes, only_global):
        patterns = []
        for pat, f in builtin_commands.items():
            if not only_global or is_global_builtin_pattern(pat):
                patterns.append((pat, f))

        r = ParseResult()

        r.longest, vars, r.missing, pattern, x = self.longest_matching_pattern(patterns, input, enabled_modes)
        if r.longest != 0:
            if r.missing == []:
                f, act = x
                if f is not None:
                    ctx = {'enabled_modes': enabled_modes}
                    r.retval = f(ctx, *vars)
                if act is not None: r.actions = [(act, vars)]
                if pattern == 'mode <mode>': r.new_mode = vars[1]
                    # this applies the mode switch /during/ command evaluation,
                    # which is beyond the capabilities of regular built-ins,
                    # since those only produce actions to be executed later.
                    # hence this special case for the 'mode' command.

        elif input != []:
            cmd, *args = input
            if cmd == 'builtin':
                r = self.handle_builtin_command(args, enabled_modes, False)
                r.longest += 1 # to account for 'builtin' itself
                return r

        return r

    def param_matched(self, param, args, enabled_modes):
        arg = args[0]
        for alt in param.split('|'):
            if alt == arg: return (1, [])
            if alt.startswith('<'): # oh it's a type
                type = alt[1:-1]
                if type in builtin_types and builtin_types[type](arg):
                    return (1, [])
                if type == 'mode' and arg in self.modes:
                    return (1, [])
                if type in self.enums:
                    matched, _v, mis, _pat, _r = self.longest_matching_pattern([(self.enums[type], None)], args, enabled_modes)
                    if matched != 0: return (matched, mis)
        return (0, [param])

    def longest_matching_pattern(self, patterns, input, enabled_modes):
        # if multiple patterns match equally well, the first one of them is returned
        # (this is important because it's how commands in the current mode
        #  override commands in auto-enabled modes)

        longest = 0
        vars = None
        missing = []
        pattern = None
        result = None

        for p, r in patterns:
            for form in p.split('/'):
                params = form.split()
                matched, mis, v = self.params_matched(params, input, enabled_modes)

                if matched == longest:
                    if mis != [] and missing != []:
                        missing += mis
                    elif missing != []:
                        missing = []
                        pattern = p
                        result = r
                        vars = v
                elif matched > longest:
                    longest = matched
                    missing = mis
                    if missing == []:
                        pattern = p
                        result = r
                        vars = v

        return (longest, vars, missing, pattern, result)
