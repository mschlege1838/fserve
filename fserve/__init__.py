import time
import os.path
import re
from threading import Thread
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
from traceback import print_exc
from importlib.resources import files


class AcceptItem:
    def __init__(self, primary_type, subtype, quality=1.0):
        self.primary_type = primary_type.casefold()
        self.subtype = subtype.casefold()
        self.quality = quality
    
    def matches(self, other):
        if self.primary_type == '*':
            return True
        if self.primary_type != other.primary_type:
            return False
        if self.subtype == '*':
            return True
        return self.subtype == other.subtype



class FileRequestHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    
    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)
    
    def do_GET(self):
        if self.check_sub_handlers():
            return
        
        base_dir = self.server.base_dir if hasattr(self.server, 'base_dir') else '.'
        
        segs = urlparse(self.server.unquote_fn(self.path)).path.split('/')
        data = None
        try:
            fname = os.path.join(base_dir, *segs)
            with open(fname, 'rb') as f:
                data = f.read()
        except FileNotFoundError:
            for fname in ['index.html', 'index.htm']:
                try:
                    with open(os.path.join(base_dir, *segs, fname), 'rb') as f:
                        data = f.read()
                        break
                except FileNotFoundError:
                    pass
        
        if data:
            self.send_response(200)
            self.send_header('Content-Type', get_content_type(fname))
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)
    
    def do_HEAD(self):
        if self.check_sub_handlers():
            return
        self.send_error(405)
        
    def do_OPTIONS(self):
        if self.check_sub_handlers():
            return
        self.send_error(405)
        
    def do_PUT(self):
        if self.check_sub_handlers():
            return
        self.send_error(405)
        
    def do_DELETE(self):
        if self.check_sub_handlers():
            return
        self.send_error(405)
        
    def do_POST(self):
        if self.check_sub_handlers():
            return
        self.send_error(405)
        
    def do_PATCH(self):
        if self.check_sub_handlers():
            return
        self.send_error(405)
    
    def check_sub_handlers(self):
        if hasattr(self.server, 'sub_handlers') and self.server.sub_handlers:
            for sub_handler in self.server.sub_handlers:
                result = sub_handler.match(self)
                if result:
                    try:
                        sub_handler.handle(self, result)
                    except:
                        print_exc()
                        self.send_error(500)
                    return True
        return False

class BaseDirHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, base_dir='.', sub_handlers=None, unquote_fn=unquote):
        super().__init__(server_address, RequestHandlerClass)
        self.base_dir = base_dir
        if sub_handlers:
            for sub_handler in sub_handlers:
                if not hasattr(sub_handler, 'match') or not callable(sub_handler.match):
                    raise ValueError('Sub-handler does not have callable match attribute: ', sub_handler)
                if not hasattr(sub_handler, 'handle') or not callable(sub_handler.handle):
                    raise ValueError('Sub-handler does not hae callable handle attribute: ', sub_handler)
        self.sub_handlers = sub_handlers
        self.unquote_fn = unquote_fn


class RegexSubHandler:    
    def __init__(self, pattern, full_match=True, extract_path=False, unquote_fn=unquote):
        self.pattern = pattern if isinstance(pattern, re.Pattern) else \
                re.compile(pattern if pattern.endswith('/?') or pattern == '/' else pattern + '/?')
        self.full_match = full_match
        self.extract_path = extract_path
        self.unquote_fn = unquote
    
    def match(self, handler):
        path = self.unquote_fn(handler.path)
        if self.extract_path:
            urlparse_result = urlparse(path)
            match_result = getattr(self.pattern, 'fullmatch' if self.full_match else 'match')(urlparse_result.path)
            return (match_result, urlparse_result) if match_result else None
        else:
            return getattr(self.pattern, 'fullmatch' if self.full_match else 'match')(path)
    
    def handle(self, handler, match):
        target = f'do_{handler.command.upper()}'
        if hasattr(self, target):
            getattr(self, target)(handler, match)
        else:
            handler.send_error(405)


def local_serve(port, base_dir=None, sub_handlers=None, request_handler=FileRequestHandler):
    server = BaseDirHTTPServer(('', port), request_handler, base_dir, sub_handlers)
    server_thread = Thread(target=server.serve_forever)
    server_thread.start()
    
    try:
        print('Server started on local port:', port)
        print('Control-C to stop')
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('Stopping server...')
        server.shutdown()
        server_thread.join(timeout=10)
        print('Server stopped')


def get_content_type(fname):
    return file_types.get(os.path.splitext(fname)[1], 'application/octet-stream')


accept_list_pattern = re.compile(r'\s*,\s*')
accept_element_pattern = re.compile(r'(?P<type>\w+)/(?P<subtype>\w+)(?:;q=(?P<quality>\w+))?')
def choose_accept(accept_header, *produces_list):
    if not accept_header:
        return produces_list[0]
    
    accept_list = accept_list_pattern.split(accept_header.strip())
    accept_items = []
    for raw in accept_list:
        match = accept_element_pattern.match(raw)
        if not match:
            continue
            
        quality = 1.0
        if match.group('quality'):
            try:
                quality = float(match.group('quality'))
            except ValueError:
                pass
        
        accept_items.append(AcceptItem(match.group('type'), match.group('subtype'), quality))
    accept_items.sort(key=lambda v: quality, reverse=True)
    
    
    produces_items = []
    for raw in produces_list:
        match = accept_element_pattern.match(raw)
        if not match:
            raise ValueError(raw)
        
        produces_items.append((raw, AcceptItem(match.group('type'), match.group('subtype'))))
    
    for accept_item in accept_items:
        for raw, produces_item in produces_items:
            if accept_item.matches(produces_item):
                return raw
    
    return None


def bool_param(query_values):
    if not query_values:
        return
    value = query_values[0].casefold()
    return value != 'false' and value != '0'


file_types = {
    '.aac': 'audio/aac',
    '.abw': 'application/x-abiword',
    '.apng': 'image/apng',
    '.arc': 'application/x-freearc',
    '.avif': 'image/avif',
    '.avi': 'video/x-msvideo',
    '.azw': 'application/vnd.amazon.ebook',
    '.bin': 'application/octet-stream',
    '.bmp': 'image/bmp',
    '.bz': 'application/x-bzip',
    '.bz2': 'application/x-bzip2',
    '.cda': 'application/x-cdf',
    '.csh': 'application/x-csh',
    '.css': 'text/css',
    '.csv': 'text/csv',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.eot': 'application/vnd.ms-fontobject',
    '.epub': 'application/epub+zip',
    '.gz': 'application/gzip',
    '.gif': 'image/gif',
    '.htm': 'text/html',
    '.html': 'text/html',
    '.ico': 'image/vnd.microsoft.icon',
    '.ics': 'text/calendar',
    '.jar': 'application/java-archive',
    '.jpeg': 'image/jpeg',
    '.jpg': 'image/jpeg',
    '.js': 'text/javascript',
    '.json': 'application/json',
    '.jsonld': 'application/ld+json',
    '.mid': 'audio/midi, audio/x-midi',
    '.midi': 'audio/midi, audio/x-midi',
    '.mjs': 'text/javascript',
    '.mp3': 'audio/mpeg',
    '.mp4': 'video/mp4',
    '.mpeg': 'video/mpeg',
    '.mpkg': 'application/vnd.apple.installer+xml',
    '.odp': 'application/vnd.oasis.opendocument.presentation',
    '.ods': 'application/vnd.oasis.opendocument.spreadsheet',
    '.odt': 'application/vnd.oasis.opendocument.text',
    '.oga': 'audio/ogg',
    '.ogv': 'video/ogg',
    '.ogx': 'application/ogg',
    '.opus': 'audio/ogg',
    '.otf': 'font/otf',
    '.png': 'image/png',
    '.pdf': 'application/pdf',
    '.php': 'application/x-httpd-php',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.rar': 'application/vnd.rar',
    '.rtf': 'application/rtf',
    '.sh': 'application/x-sh',
    '.svg': 'image/svg+xml',
    '.tar': 'application/x-tar',
    '.tif': 'image/tiff',
    '.tiff': 'image/tiff',
    '.ts': 'video/mp2t',
    '.ttf': 'font/ttf',
    '.txt': 'text/plain',
    '.vsd': 'application/vnd.visio',
    '.wav': 'audio/wav',
    '.weba': 'audio/webm',
    '.webm': 'video/webm',
    '.webp': 'image/webp',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.xhtml': 'application/xhtml+xml',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xml': 'application/xml',
    '.xul': 'application/vnd.mozilla.xul+xml',
    '.zip': 'application/zip',
    '.7z': 'application/x-7z-compressed'
}
