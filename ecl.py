import util
import termcolor

class ParseResult():
    def __init__(self, retval=None):
        self.longest = 0
        self.missing = []
        self.actions = []
        self.new_mode = None
        self.error = None
        self.retval = retval
        self.resolved = []

    def try_improve(self, other):
        if other.longest == self.longest:
            if other.missing != [] and self.missing != []:
                self.missing += other.missing
            elif self.missing != []:
                self.missing = []
                self.retval = other.retval
        elif other.longest > self.longest:
            self.longest = other.longest
            self.missing = other.missing
            self.actions = other.actions
            self.new_mode = other.new_mode
            self.error = other.error
            self.retval = other.retval
            self.resolved = other.resolved

def is_global_builtin_pattern(pat):
    global_builtins = ['options', 'define', 'builtin']
    pat = pat.split()
    while pat != [] and pat[0][0] == '<': pat = pat[1:]
    return pat != [] and pat[0] in global_builtins

def forms(pattern): return pattern.split('/')
def params(form): return form.split(' ')
def alternatives(param): return param.split('|')

class Context():
    def __init__(self):
        self.modes = {}
        self.enums = {}
        self.script_vars = {}
        self.color = True
        self.builtin_commands = {}
        self.builtin_types = {}
        self.always_on_modes = []

    def colored(self, s, c):     return termcolor.colored(s, c) if self.color else s
    def italic(self, s):         return util.italic(s) if self.color else s
    def color_mode(self, m):     return self.colored(m, 'cyan')
    def color_commands(self, p): return self.colored(p, 'magenta')

    def is_type(self, t):
        return t in self.enums or t in self.builtin_types or t in ['mode', 'command']

    def italic_types_in_alternative(self, alt):
        n=''
        if alt.endswith('+'):
            n = '+'
            alt = alt[:-1]
        return (self.italic(alt[1:-1]) if alt.startswith('<') else alt) + n

    def italic_types_in_pattern(self, pattern):
        return '/'.join(
                [' '.join(
                    ['|'.join(
                        [ self.italic_types_in_alternative(alt)
                            for alt in alternatives(param)
                        ])
                        for param in params(form)
                    ])
                    for form in forms(pattern)])

    def alias_definition_str(self, mode, pattern, start_column=0):
        expansion = self.modes[mode][pattern]
        pat = self.italic_types_in_pattern(pattern)
        r = self.color_mode(mode) + ' ' + self.color_commands(pat) + ' = '
        indent = start_column + len(mode) + len(util.strip_markup(pat)) + len("  = ")
        l = [self.color_commands(e) + ' ' for e in expansion.split()] # todo: handle '' args
        s = l[-1]; l[-1] = s[:-1] # remove last space
        return r + util.indented_and_wrapped(l, indent)

    def match_type(self, param, args, type, enabled_modes):
        x = ParseResult()
        if type in self.builtin_types and self.builtin_types[type](args[0]):
            x.longest = 1
            x.retval = [args[0]]
            return x
        if type == 'mode' and args[0] in self.modes:
            x.longest = 1
            x.retval = [args[0]]
            return x
        x = ParseResult([])
        x.missing = [param]
        if type in self.enums:
            x.try_improve(self.match_pattern(self.enums[type], args, enabled_modes))
        return x

    def match_simple_parameter(self, param, args, enabled_modes):
        arg = args[0]
        r = ParseResult()
        r.missing = [param]
        for alt in alternatives(param):
            if alt == arg:
                r.longest = 1
                r.missing = []
                r.retval = arg
                break
            if alt.startswith('<'):
                type = alt[1:-1]
                r.try_improve(self.match_type(param, args, type, enabled_modes))
                if r.retval is not None:
                    r.retval = ' '.join(r.retval)
        return r

    def match_parameter(self, param, args, enabled_modes):
        if param == '<command>':
            x = self.match_commands(args, enabled_modes, True, True)
            consumed = list(map(util.quote_if_necessary, args[:x.longest]))
            if x.longest == 0:
                x.missing = ['<command>']
                x.retval = None
            elif x.resolved != None:
                consumed = x.resolved
                if consumed[:1] != ['{']:
                    consumed = ['{'] + consumed + ['}']
                x.retval = ' '.join(consumed)
            x.actions = []
            return x
        elif param.endswith('+'):
            sub = param[:-1]
            pr = ParseResult([])
            while args != [] and args[0] != ';':
                x = self.match_parameter(sub, args, enabled_modes)
                pr.longest += x.longest
                if x.longest != 0: pr.missing = x.missing
                if x.error is not None: pr.error = x.error
                if x.retval is None or x.longest == 0 or x.error is not None:
                    pr.retval = None
                    return pr
                pr.retval.append(x.retval)
                args = args[x.longest:]
            pr.retval = ' '.join(map(util.quote_if_necessary, pr.retval))
            return pr
        else:
            return self.match_simple_parameter(param, args, enabled_modes)

    def match_params(self, params, args, enabled_modes):
        pr = ParseResult([])
        while params != [] and args != []:
            x = self.match_parameter(params[0], args, enabled_modes)
            pr.longest += x.longest
            if x.longest != 0: pr.missing = x.missing
            if x.error is not None: pr.error = x.error
            if x.retval is None or x.longest == 0: break
            args = args[x.longest:]
            params = params[1:]
            pr.retval += [x.retval]
        if params != [] and pr.missing == []:
            pr.missing = [params[0]]
        return pr

    def match_pattern(self, pattern, input, enabled_modes):
        pr = ParseResult()
        for form in forms(pattern):
            pr.try_improve(self.match_params(params(form), input, enabled_modes))
        return pr

    def substitute_variables(self, expansion, vars, enabled_modes):
        err = None
        replaced = ''
        quoted = False
        while expansion != '':
            if not quoted and expansion.startswith(')'):
                break
            if expansion[0] == '"':
                quoted = not quoted
                replaced += '"'
                expansion = expansion[1:]
            elif not quoted and expansion.startswith('$('):
                sub = expansion[2:]
                args, rest, _err = self.substitute_variables(sub, vars, enabled_modes)
                pr = self.match_commands(args, enabled_modes, True, False)
                consumed = args[:pr.longest]
                unconsumed = args[pr.longest:]
                if pr.error is not None:
                    err = pr.error
                    break
                if pr.missing != [] or pr.longest != len(args):
                    err = self.describe_cmd_parse_result(pr, args)
                    break
                replaced += str(pr.retval)
                expansion = rest[1:]
            elif expansion.startswith('$'):
                i = 1
                while i < len(expansion) and (expansion[i].isalnum() or expansion[i] == '*'):
                    i += 1
                varname = expansion[1:i]
                expansion = expansion[i:]
                if varname not in vars:
                    err = 'undefined variable $' + varname
                    break
                replaced += (util.escape(vars[varname]) if quoted else vars[varname])
            else:
                replaced += expansion[0]
                expansion = expansion[1:]
        return (util.split_expansion(replaced), expansion, err)

    def describe_cmd_parse_result(self, pr, exp):
        qexp = list(map(util.quote_if_necessary, exp))
        x = [self.colored(s, 'green') + ' ' for s in qexp[:pr.longest]] + \
            [self.colored(s, 'red') + ' ' for s in qexp[pr.longest:]]
        if pr.longest == len(exp): x.append(self.colored('???', 'red'))
        s = util.indented_and_wrapped(x, 4)
        msg = 'invalid command:\n  ' + s + '\n'
        if pr.missing != []:
            msg += ('missing ' if pr.longest == len(exp) else 'expected ')
            msg += ' or '.join(map(self.italic_types_in_pattern, pr.missing)) + '\n'
        elif pr.longest != len(exp):
            msg += "unexpected " + exp[pr.longest]
        return msg

    def match_alias(self, input, enabled_modes, input_modes):
        r = ParseResult((None, None, None, None))
        for m in (["default"] if enabled_modes[:1] == ["default"] else enabled_modes):
            for pattern, exp in self.modes[m].items():
                x = self.match_pattern(pattern, input, input_modes)
                x.retval = (x.retval, m, exp, pattern)
                r.try_improve(x)

        if r.longest == 0 or r.missing != []: return r
        vars, m, expansion, pattern = r.retval

        if expansion == '~builtin':
            return self.match_builtin(input, enabled_modes, False)
        if expansion.startswith('~'):
            mod = expansion[1:]
            return self.match_alias(input, [mod], input_modes)

        r.resolved = vars
        pre = ['{', 'builtin', 'mode', m]
        if vars[:len(pre)] != pre:
            r.resolved = pre + vars + ['}']

        errorpart = 'command ' + self.colored(' '.join(map(util.quote_if_necessary, input[:r.longest])), 'green') + \
            ' matched alias:\n  ' + self.alias_definition_str(m, pattern, 4) + '\n'

        evars = self.script_vars.copy()
        for i, v in enumerate(vars[:r.longest]): evars[str(i)] = v
        exp, _rest, err = self.substitute_variables(expansion, evars, enabled_modes)
        if err is not None: r.error = errorpart + err; return r

        sub = self.match_commands(exp, [m], True, False)
        if sub.error is not None:
            r.error = errorpart + sub.error
        elif sub.missing != [] or sub.longest != len(exp):
            r.error = errorpart + self.describe_cmd_parse_result(sub, exp)
        else:
            r.actions = sub.actions
            r.new_mode = sub.new_mode
            r.retval = sub.retval
            if sub.error is not None:
                r.error = errorpart + sub.error
        return r

    def match_builtin(self, input, enabled_modes, only_global):
        r = ParseResult((None, None, None, None))
        for pattern, (f, act) in self.builtin_commands.items():
            if not only_global or is_global_builtin_pattern(pattern):
                y = self.match_pattern(pattern, input, enabled_modes)
                y.retval = (y.retval, f, act, pattern)
                r.try_improve(y)
        vars, f, act, pattern = r.retval
        r.retval = None
        if vars != None:
            r.resolved = ['builtin'] + vars
            if vars[:1] == ['mode']:
                r.resolved = []
        if r.longest != 0 and r.missing == []:
            if f is not None:
                ctx = {'enabled_modes': enabled_modes, 'ecl': self}
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
                r = self.match_builtin(args, enabled_modes, False)
                r.longest += 1 # to account for 'builtin' itself
        return r

    def match_command(self, words, enabled_modes, handle_builtins=True):
        enabled_modes = enabled_modes[:1] + [m for m in self.modes
            if [m] != enabled_modes[:1] and
                (m in enabled_modes or (enabled_modes[:1] != ['default'] and m in self.always_on_modes))]
                    # todo: don't hard-code 'default' here

        pr = self.match_alias(words, enabled_modes, enabled_modes)
        if handle_builtins and pr.error is None:
            pr.try_improve(self.match_builtin(words, enabled_modes, True))
        return pr

    def match_commands(self, words, enabled_modes,
            handle_builtins=True,
            stop_on_semicolon=False):
        if words == [] or words[:1] == ['}']:
            return ParseResult()

        x = util.try_parse_braced_expr(words[0])
        if x is not None and x[1] == '':
            sub = x[0]
            r = self.match_commands(sub, enabled_modes, handle_builtins, False)
            if r.longest == len(sub) and r.error is None and r.missing == []:
                r.longest = 1
            else:
                if r.error is None:
                    r.error = self.describe_cmd_parse_result(r, sub)
                r.longest = 0
        else:
            r = self.match_command(words, enabled_modes, handle_builtins)

        if r.longest == 0:
            r.missing = ['<command>']
            r.actions = []
        else:
            if r.longest != len(words) and r.error is None and r.missing == []:
                w = words[r.longest:]
                if w != [] and w[0] == ';':
                    if stop_on_semicolon: return r
                    w = w[1:]
                    r.resolved.append(';')
                    r.longest += 1
                if w != []:
                    if r.new_mode is not None:
                        enabled_modes = [r.new_mode] + [m for m in enabled_modes if m != r.new_mode]
                    r2 = self.match_commands(w, enabled_modes, True, stop_on_semicolon)
                    r.longest += r2.longest
                    r.resolved += r2.resolved
                    r.missing = r2.missing
                    r.actions += r2.actions
                    if r2.error is not None: r.error = r2.error
                    if r2.longest != 0:
                        if r2.new_mode is not None:
                            r.new_mode = r2.new_mode
                        r.retval = r2.retval

        return r
