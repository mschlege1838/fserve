import os
from importlib.resources import files

from jinja2 import Environment, FunctionLoader, select_autoescape
from jinja2.nodes import ExprStmt, Const, CallBlock
from jinja2.ext import Extension

from .jinja_parse import statement_parse, TemplateStatement, TokenType


class StylesheetExtension(Extension):
    tags = {'stylesheet'}
    
    def __init__(self, environment):
        super().__init__(environment)
    
    def preprocess(self, source, name, filename):
        return source
    
    def parse(self, parser):
        parser.parse_expression()
        return ExprStmt(Const('None')).set_lineno(next(parser.stream).lineno)

class StylesheetsExtension(Extension):
    tags = {'stylesheets'}
    
    def __init__(self, environment):
        super().__init__(environment)
        self.stylesheet_cache = {}
    
    def preprocess(self, source, name, filename):
        stylesheets = self.stylesheet_cache[filename] = []
        self.load_stylesheets(source, stylesheets)
        return source
    
    def load_stylesheets(self, source, stylesheets):
        env = self.environment
        loader = env.loader
        
        doc = statement_parse(source)
        for el in doc.elements:
            if isinstance(el, TemplateStatement):
                # TODO support list-style import (first non-missing)
                if el.command == 'include' and el.tokens[0].tok_type == TokenType.STR_LIT:
                    self.load_stylesheets(loader.get_source(env, el.tokens[0].value)[0], stylesheets)
                elif el.command == 'stylesheet':
                    stylesheets.append(el.tokens[0].value)
            
                
        return source
        
    def parse(self, parser):
        lineno = next(parser.stream).lineno
        return CallBlock(self.call_method('dump_hrefs', [Const(parser.filename)]), [], [], []).set_lineno(lineno)
    
    def dump_hrefs(self, filename, caller):
        stylesheets = self.stylesheet_cache.get(filename)
        return '\n'.join((f'<link rel="stylesheet" href="{e}" />' for e in stylesheets) if stylesheets else '')


def get_jinja_loader(module_name, encoding='utf-8', do_cache=True):
    templates = {}
    
    def get_template(name):
        nonlocal templates, do_cache
        
        target = str(files(module_name).joinpath(*name.split('/')))
        
        current_mtime = os.stat(target).st_mtime
        def up_to_date():
            nonlocal do_cache, templates, target, current_mtime
            if not do_cache:
                return False
            last_mtime = templates.get(target)
            templates[target] = current_mtime
            return last_mtime is not None and last_mtime >= current_mtime
            
        
        try:
            with open(target, encoding=encoding) as f:
                return (f.read(), target, up_to_date)
        except FileNotFoundError:
            return None
    
    return get_template

def get_jinja_env(module_name, extensions=[]):
    return Environment(loader=FunctionLoader(get_jinja_loader(module_name)), autoescape=select_autoescape(), extensions=extensions)


