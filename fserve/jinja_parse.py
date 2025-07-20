import unicodedata
from dataclasses import dataclass
from enum import Enum, auto

def is_digit(ch, radix=10):
    if ch == -1:
        return False
    match radix:
        case 10:
            return '0' <= ch <= '9'
        case 16:
            return '0' <= ch <= '9' or 'a' <= ch <= 'f' or 'A' <= ch <= 'F'
        case 8:
            return '0' <= ch <= '7'
        case _:
            raise ValueError('Bad radix:', radix)

def is_alpha(ch):
    if ch == -1:
        return False
    return 'a' <= ch <= 'z' or 'A' <= ch <= 'Z' or ch == '_'

def is_alphanum(ch):
    if ch == -1:
        return False
    return 'a' <= ch <= 'z' or 'A' <= ch <= 'Z' or '0' <= ch <= '9' or ch == '_'

def is_ws(ch):
    if ch == -1:
        return False
    cp = ord(ch)
    if cp == 32 or 9 <= cp <= 13 or 8192 <= cp <= 8202:
        return True
    return cp in (133, 160, 5670, 8232, 8233, 8239, 8287, 12288)

class InvalidSyntaxError(Exception):
    def __init__(self, message, position):
        super().__init__(message, '@', position)

class UnexpectedTokenError(Exception):
    def __init__(self, token, *expected):
        super().__init__(f'Invlid token: {token} @ {token.offset}; expected: {expected}')

def check_tok(tok, *expected):
    if tok.tok_type not in expected:
        raise UnexpectedTokenError(tok, *expected)
    return tok

class TokenType(Enum):
    STATEMENT_START = auto()
    STATEMENT_END = auto()
    INLINE_START = auto()
    INLINE_END = auto()
    COMMENT_START = auto()
    COMMENT_END = auto()
    LINE_STATEMENT_PREFIX = auto()
    LINE_COMMENT_PREFIX = auto()
    COMMENT_DATA = auto()
    TEMPLATE_DATA = auto()
    WS = auto()
    NAME_OR_KEYWORD = auto()
    STR_LIT = auto()
    NUM_LIT = auto()
    L_BRACKET = auto()
    R_BRACKET = auto()
    L_PAREN = auto()
    R_PAREN = auto()
    L_BRACE = auto()
    R_BRACE = auto()
    PIPE = auto()
    EQ = auto()
    COMMA = auto()
    DOT = auto()
    MATH_OP_OR_STAR_ARGS = auto()
    COMPARE_OP = auto()
    COLON = auto()
    EOF = auto()

class Token:
    def __init__(self, tok_type, text, offset, value=None):
        self.tok_type = tok_type
        self.text = text
        self.offset = offset
        self.value = value if value is not None else text
    
    def __str__(self):
        return f'{self.tok_type}: {self.text} ({self.offset}){"; "  + self.value if self.value != self.text else ""}'
    
    __repr__ = __str__

class JinjaStatementLexer:
    def __init__(self, template_text, block_start, block_end, inline_start, inline_end,
                comment_start, comment_end, line_statement_prefix, line_comment_prefix, *ignore_tokens):
        self.template_text = template_text
        self.block_start = block_start
        self.block_end = block_end
        self.inline_start = inline_start
        self.inline_end = inline_end
        self.comment_start = comment_start
        self.comment_end = comment_end
        self.line_statement_prefix = line_statement_prefix
        self.line_comment_prefix = line_comment_prefix
        self.ignore_tokens = set(ignore_tokens)
        self.buf_tok = None
        self.buf_state = None
        
        self.template_pos = 0
        self.ch_buf = []
        self.la_buf = []
        self.state = 0
        self.buf = None
    
    def next_token(self):
        ignore_tokens = self.ignore_tokens
        la_buf = self.la_buf
        while True:
            if la_buf:
                tok = la_buf[0]
                del la_buf[0]
                return tok
            else:
                tok = self._next_token()
                if tok.tok_type in ignore_tokens:
                    continue
                return tok
    
    def la(self, k=1):
        ignore_tokens = self.ignore_tokens
        la_buf = self.la_buf
        i = 0
        for la in la_buf:
            i += 1
            if i == k:
                return la
        
        length = k - i
        j = 0
        while j < length:
            la = self._next_token()
            if la.tok_type in ignore_tokens:
                continue
            la_buf.append(la)
            j += 1
        
        return la
    
    def _next_token(self):
        state = self.state
        
        while True:

            # Initial
            if state == 0:
                start_pos = self.template_pos
                
                block_start = self.block_start
                comment_start = self.comment_start
                line_statement_prefix = self.line_statement_prefix
                line_comment_prefix = self.line_comment_prefix
                inline_start = self.inline_start
                
                buf = []
                while True:
                    ch = self._next()
                    if  ch == -1:
                        return Token(TokenType.TEMPLATE_DATA, ''.join(buf), start_pos) if buf else \
                                Token(TokenType.EOF, '', self.template_pos)
                    
                    for match_token, tok_type in (
                            (block_start, TokenType.STATEMENT_START),
                            (inline_start, TokenType.INLINE_START),
                            (comment_start, TokenType.COMMENT_START),
                            (line_statement_prefix, TokenType.LINE_STATEMENT_PREFIX),
                            (line_comment_prefix, TokenType.LINE_COMMENT_PREFIX)):
                        if not match_token or ch != match_token[0]:
                            continue
                        i = 1
                        match_pos = self.template_pos
                        while i < len(match_token):
                            if self._la(i) != match_token[i]:
                                break
                            i += 1
                        else:
                            self._clear_la()
                            tok = Token(tok_type, match_token, match_pos)
                            
                            match tok_type:
                                case TokenType.STATEMENT_START:
                                    self.state = 1
                                case TokenType.COMMENT_START:
                                    self.state = 2
                                case TokenType.INLINE_START:
                                    self.state = 5
                                # TODO Verify no non-whitespace chars before
                                case TokenType.LINE_STATEMENT_PREFIX:
                                    self.state = 3
                                case TokenType.LINE_COMMENT_PREFIX:
                                    self.state = 4
                                
                                
                            if buf:
                                self.buf_tok = tok
                                self.buf_state = self.state
                                self.state = 6
                                return Token(TokenType.TEMPLATE_DATA, ''.join(buf), start_pos)
                            else:
                                return tok
                    
                    buf.append(ch)
            
            # In statement
            if state in (1, 3, 5):
                match state:
                    case 1:
                        terminator, end_tok_type = self.block_end, TokenType.STATEMENT_END
                    case 3:
                        terminator, end_tok_type = None, TokenType.STATEMENT_END
                    case 5:
                        terminator, end_tok_type = self.inline_end, TokenType.INLINE_END
                rv = self._do_statement(terminator, end_tok_type, state == 3)
                if rv.tok_type == end_tok_type:
                    self.state = 0
                return rv
            
            # In comment
            if state == 2 or state == 4:
                rv = self._do_comment(state == 4)
                if rv.tok_type == TokenType.COMMENT_END:
                    self.state = 0
                return rv
            
            if state == 6:
                tok = self.buf_tok
                self.buf_tok = None
                self.state = self.buf_state
                self.buf_state = None
                return tok
    
    def _do_statement(self, terminator, end_tok_type, single_line):
        start_pos = self.template_pos
        
        ch = self._next()
        if ch == -1:
            return Token(TokenType.EOF, '', self.template_pos)
        
        # Check for end-of-statement
        if terminator:
            if ch == terminator[0]:
                i = 1
                while i < len(terminator):
                    if self._la(i) != terminator[i]:
                        break
                    i += 1
                else:
                    self._clear_la()
                    return Token(end_tok_type, self._clear_buf(), start_pos)
    
        # Otherwise, regular lexicon
        if ch == '(':
            return Token(TokenType.L_PAREN, ch, start_pos)
        elif ch == ')':
            return Token(TokenType.R_PAREN, ch, start_pos)
        elif ch == '[':
            return Token(TokenType.L_BRACKET, ch, start_pos)
        elif ch == ']':
            return Token(TokenType.R_BRACKET, ch, start_pos)
        elif ch == '{':
            return Token(TokenType.L_BRACE, ch, start_pos)
        elif ch == '}':
            return Token(TokenType.R_BRACE, ch, start_pos)
        elif ch == ',':
            return Token(TokenType.COMMA, ch, start_pos)
        elif ch == '|':
            return Token(TokenType.PIPE, ch, start_pos)
        elif ch == ':':
            return Token(TokenType.COLON, ch, start_pos)
        elif ch == '.':
            if is_digit(self._la()):
                return self._do_num(start_pos, ch)
            return Token(TokenType.DOT, ch, start_pos)
        elif ch == '+' or ch == '-':
            if is_digit(self._la()):
                return _do_num(start_pos, ch)
            return Token(TokenType.MATH_OP_OR_STAR_ARGS, ch, start_pos)
        elif ch == '*' or ch == '/':
            if self._la() == ch:
                return Token(TokenType.MATH_OP_OR_STAR_ARGS, f'{ch}{self._next()}', start_pos)
            return Token(TokenType.MATH_OP_OR_STAR_ARGS, ch, start_pos)
        elif ch == '>' or ch == '<':
            if self._la() == '=':
                return Token(TokenType.COMPARE_OP, f'{ch}{self._next()}', start_pos)
            return Token(TokenType.MATH_OP_OR_STAR_ARGS, ch, start_pos)
        elif ch == '=':
            if self._la() == '=':
                self._next()
                return Token(TokenType.COMPARE_OP, '==', start_pos)
            return Token(TokenType.EQ, '=', start_pos)
        elif ch == '"' or ch == "'":
            return self._do_str(start_pos, ch)
        elif is_digit(ch):
            return self._do_num(start_pos, ch)
        elif is_ws(ch):
            self._start_buf(TokenType.WS, ch)
            while True:
                if not is_ws(self._la()):
                    value = self._clear_buf()
                    # TODO Support line continuation (?; seldom used...)
                    if single_line and (value.endswith('\r\n') or value.endswith('\n') or value.endswith('\r')):
                        return Token(end_tok_type, value, start_pos)
                    else:
                        return Token(TokenType.WS, value, start_pos)
                self._next()
        elif is_alpha(ch):
            self._start_buf(TokenType.NAME_OR_KEYWORD, ch)
            while True:
                if not is_alphanum(self._la()):
                    return Token(TokenType.NAME_OR_KEYWORD, self._clear_buf(), start_pos)
                self._next()
        else:
            raise InvalidSyntaxError(f'Invalid token: {ch}', start_pos)
    
    def _do_comment(self, single_line):
        start_pos = self.template_pos
        self._start_buf(TokenType.COMMENT_DATA)
        
        while True:
            ch = self._next()
            if ch == -1:
                return Token(TokenType.EOF, '', self.template_pos)
            
            # Check for end-of-statement
            rv = None
            if single_line:
                if ch == '\r':
                    if self._la() == '\n':
                        self._next()
                    rv = Token(TokenType.COMMENT_END, self._clear_buf(), start_pos)
                elif ch == '\n':
                    rv = Token(TokenType.COMMENT_END, self._clear_buf(), start_pos)
            else:
                comment_end = self.comment_end
                if ch == comment_end[0]:
                    i = 1
                    while i < len(comment_end):
                        if self._la(i) != comment_end[i]:
                            break
                        i += 1
                    else:
                        self._clear_la()
                        rv = Token(TokenType.COMMENT_END, self._clear_buf(), start_pos)
            
            if rv:
                if self.buf:
                    self.la_buf.append(rv)
                    return Token(TokenType.COMMENT_DATA, self._clear_buf(), start_pos)
                else:
                    return rv

    
    def _do_str(self, start_pos, ch):
        value_buf = []
        opening_qchar = ch
        self._start_buf(TokenType.STR_LIT, ch)
        while True:
            ch = self._next()
            if ch == -1:
                return Token(TokenType.EOF, '', self.template_pos)
            
            if ch == opening_qchar:
                return Token(TokenType.STR_LIT, self._clear_buf(), start_pos, ''.join(value_buf))
            elif ch == '\\':
                
                ch = self._next()
                if ch == -1:
                    return Token(TokenType.EOF, '', self.template_pos)
                
                if ch == 'n':
                    value_buf.append('\n')
                elif ch == 'r':
                    value_buf.append('\r')
                elif ch ==  '\n' | '\r':
                    pass
                elif ch == '\r':
                    if self._la() == '\n':
                        self._next()
                elif ch == 't':
                    value_buf.append('\t')
                
                elif ch == 'x':
                    ch1 = self._next()
                    ch2 = self._next()
                    if not is_digit(ch1, 16) or not is_digit(ch2, 16):
                        raise InvalidSyntaxError(f'Bad x escape: {ch1}{ch2}', self.template_pos - 2)
                    value_buf.append(chr(int(f'{ch1}{ch2}', 16)))
                elif is_digit(ch, 8):
                    ch1 = self._next()
                    ch2 = self._next()
                    ch3 = self._next()
                    if not is_digit(ch1, 8) or not is_digit(ch2, 8) or not is_digit(ch3, 8):
                        raise InvalidSyntaxError(f'Bad octal escape: {ch1}{ch2}{ch3}', self.template_pos - 3)
                    value_buf.append(chr(int(f'{ch1}{ch2}{ch3}', 8)))
                
                elif ch == 'N':
                    ch = self._next()
                    if ch != '{':
                        raise InvalidSyntaxError(f'Bad N escape: {ch}', self.template_pos)
                    
                    uni_start_pos = self.template_pos
                    uni_name = []
                    while True:
                        ch = self._next()
                        if ch == '}':
                            break
                        elif ch == opening_qchar or ch == -1:
                            raise InvalidSyntaxError(f'Bad N escape: {"".join(uni_name)}', uni_start_pos)
                        else:
                            uni_name.append(ch)
                    try:
                        value_buf.append(unicodedata.lookup(''.join(uni_name)))
                    except SyntaxError:
                        raise InvalidSyntaxError(f'Bad N escape: {"".join(uni_name)}', uni_start_pos)
                elif ch == 'u':
                    uni_start_pos = self.template_pos
                    uni_num = [self._next(), self._next(), self._next(), self._next()]
                    for ch in uni_num:
                        if not is_digit(ch, 16):
                            raise InvalidSyntaxError(f'Bad u escape: {"".join(uni_name)}', uni_start_pos)
                    value_buf.append(chr(int(''.join(uni_num), 16)))
                elif ch == 'U':
                    uni_start_pos = self.template_pos
                    uni_num = [self._next(), self._next(), self._next(), self._next(),
                                self._next(), self._next(), self._next(), self._next()]
                    for ch in uni_num:
                        if not is_digit(ch, 16):
                            raise InvalidSyntaxError(f'Bad U escape: {"".join(uni_name)}', uni_start_pos)
                    value_buf.append(chr(int(''.join(uni_num), 16)))
                
                elif ch == 'a':
                    value_buf.append('\a')
                elif ch == 'b':
                    value_buf.append('\b')
                elif ch == 'f':
                    value_buf.append('\f')
                elif ch == 'v':
                    value_buf.append('\v')
                else:
                    value_buf.append(ch)
            else:
                value_buf.append(ch)
    
    def _do_num(self, start_pos, ch):
        self._start_buf(TokenType.NUM_LIT, ch)
        
        if ch == '-' or ch == '+':
            ch = self._next()
            if ch == -1:
                return Token(TokenType.EOF, '', self.template_pos)
        
        if ch == '.':
            while True:
                la = self._la()
                if not is_digit(la):
                    break
                self._next()
            value = self._clear_buf()
            return Token(TokenType.NUM_LIT, value, start_pos, float(value))
        
        radix = 10
        if ch == '0':
            la = self._la()
            if la == 'x' or la == 'X':
                radix = 16
                self._next()
            elif la == 'b' or la == 'B':
                radix = 2
                self._next()
            elif la == 'o' or la == 'O':
                radix = 8
                self._next()
        
        while True:
            la = self._la()
            if not is_digit(la, radix):
                break
            self._next()
        
        if radix != 10:
            value = self._clear_buf()
            return Token(TokenType.NUM_LIT, value, start_pos, int(value, radix))
        
        num_conv = int
        
        la = self._la()
        if la == '.':
            num_conv = float
            self._next()
            while True:
                la = self._la()
                if not is_digit(la):
                    break
                self._next()
        
        la = self._la()
        if la == 'e' or la == 'E':
            num_conv = float
            self._next()
            while True:
                la = self._la()
                if not is_digit(la):
                    break
                self._next()
        
        value = self._clear_buf()
        return Token(TokenType.NUM_LIT, value, start_pos, num_conv(value))
        
    def _start_buf(self, buf_token, ch=None):
        if buf_token not in self.ignore_tokens:
            self.buf = []
            if ch:
                self.buf.append(ch)
    
    def _clear_buf(self):
        rv = ''.join(self.buf) if self.buf else ''
        self.buf = None
        return rv
    
    def _next(self):
        rv = self._do_next()
        if self.buf and rv != -1:
            self.buf.append(rv)
        return rv
    
    def _do_next(self):
        ch_buf = self.ch_buf
        if self.ch_buf:
            rv = ch_buf[0]
            del ch_buf[0]
            return rv
        
        template_text = self.template_text
        template_pos = self.template_pos
        if template_pos < len(template_text):
            rv = template_text[template_pos]
            self.template_pos += 1
            return rv
        else:
            return -1
    
    def _la(self, k=1):
        ch_buf = self.ch_buf
        i = 0
        for la in ch_buf:
            i += 1
            if i == k:
                return la
        for j in range(k - i):
            la = self._do_next()
            ch_buf.append(la)
        return la
    
    def _clear_la(self):
        while self.ch_buf:
            self._next()

@dataclass
class TemplateDocument:
    elements: list

@dataclass
class TemplateStatement:
    l_ws_control: str
    command: str
    tokens: list
    r_ws_control: str

@dataclass
class TemplateInline:
    tokens: list

@dataclass
class TemplateText:
    text: str

class JinjaStatementParser:
    
    def __init__(self, lexer):
        self.lexer = lexer
    
    def document(self):
        lexer = self.lexer
        
        elements = []
        while True:
            la = lexer.la()
            match la.tok_type:
                case TokenType.TEMPLATE_DATA:
                    element = TemplateText(lexer.next_token().value)
                case TokenType.STATEMENT_START:
                    element = self.statement()
                case TokenType.INLINE_START:
                    element = self.inline()
                case TokenType.LINE_STATEMENT_PREFIX:
                    element = self.statement()
                case TokenType.EOF:
                    break
                case _:
                    raise UnexpectedTokenError(la, TokenType.TEMPLATE_DATA, TokenType.STATEMENT_START,
                            TokenType.INLINE_START, TokenType.LINE_STATEMENT_PREFIX)
                
            elements.append(element)
        
        return TemplateDocument(elements)
    
    def statement(self):
        lexer = self.lexer
        
        tok = lexer.next_token()
        check_tok(tok, TokenType.STATEMENT_START, TokenType.LINE_STATEMENT_PREFIX)
        is_block = tok.tok_type == TokenType.STATEMENT_START
        
        l_ws_control = None
        if is_block and lexer.la().value in ('+', '-'):
            l_ws_control = lexer.next_token().value
        
        command = check_tok(lexer.next_token(), TokenType.NAME_OR_KEYWORD).value
        
        tokens = []
        r_ws_control = None
        while True:
            tok = lexer.next_token()
            if tok.tok_type == TokenType.STATEMENT_END:
                break
            
            if is_block and tok.value in ('+', '-') and lexer.la().tok_type == TokenType.STATEMENT_END:
                r_ws_control = tok.value
            else:
                tokens.append(tok)
        
        return TemplateStatement(l_ws_control, command, tokens, r_ws_control)
    
    def inline(self):
        lexer = self.lexer
        check_tok(lexer.next_token(), TokenType.INLINE_START)
        
        tokens = []
        while True:
            tok = lexer.next_token()
            if tok.tok_type == TokenType.INLINE_END:
                break
            tokens.append(tok)
        
        return TemplateInline(tokens)


def statement_parse(text):
    lexer = JinjaStatementLexer(text, '{%', '%}', '{{', '}}', '{#', '#}', None, None,
                                TokenType.WS, TokenType.COMMENT_START, TokenType.COMMENT_DATA, TokenType.COMMENT_END,
                                TokenType.LINE_COMMENT_PREFIX)
    parser = JinjaStatementParser(lexer)

    return parser.document()