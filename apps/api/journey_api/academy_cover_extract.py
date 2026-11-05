"""Best-effort, bounded cover extraction without exposing external URLs to learners.

Only public HTTP(S) resources are fetched. DNS results are checked and pinned to
the actual socket; redirects and image URLs go through the same validation.
ffmpeg only receives temporary local files with an explicit demuxer and no
network protocols. A missing tool, unsupported site or invalid file is a normal
``None`` result: publishing and learning must not depend on cover extraction.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import math
from pathlib import Path
import re
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit


MAX_COVER_BYTES = 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_HTML_BYTES = 1024 * 1024
MAX_LINK_VIDEO_BYTES = 20 * 1024 * 1024
MAX_LOCAL_VIDEO_BYTES = 500 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
LINK_TIMEOUT = 25.0
VIDEO_TIMEOUT = 25.0
_DNS_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='academy-cover-dns')
_DNS_SLOTS = threading.BoundedSemaphore(2)
_DECODER_SLOTS = threading.BoundedSemaphore(2)
_TLS_CONTEXT = ssl.create_default_context()


class CoverUnavailable(Exception):
    """An expected resource, validation or extraction failure."""


class CoverBusy(Exception):
    """Temporary capacity exhaustion: retry instead of negative-caching a source."""


def _remaining(deadline, cap=8.0):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CoverUnavailable('Cover deadline exceeded')
    return min(remaining, cap)


def _public_ip(value):
    address = ipaddress.ip_address(value)
    if (not address.is_global or address.is_multicast or address.is_reserved
            or address.is_unspecified or address.is_loopback or address.is_link_local
            or getattr(address, 'ipv4_mapped', None) is not None
            or getattr(address, 'sixtofour', None) is not None
            or getattr(address, 'teredo', None) is not None):
        raise CoverUnavailable('Not a public Internet address')
    return str(address)


def _resolve_public(host, port, deadline):
    # Bound outstanding resolver work as well as how long an extraction waits.
    if not _DNS_SLOTS.acquire(blocking=False):
        raise CoverBusy('Resolver busy')
    future = _DNS_POOL.submit(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
    future.add_done_callback(lambda _: _DNS_SLOTS.release())
    try:
        records = future.result(timeout=_remaining(deadline, 3.0))
    except FutureTimeout as error:
        raise CoverUnavailable('DNS timed out') from error
    raw_addresses = {record[4][0] for record in records}
    fake_network = ipaddress.ip_network('198.18.0.0/15')
    if raw_addresses and all(ipaddress.ip_address(value) in fake_network for value in raw_addresses):
        return _resolve_fake_dns(host, deadline)
    addresses = {_public_ip(value) for value in raw_addresses}
    if not addresses:
        raise CoverUnavailable('No address')
    return sorted(addresses)[0]


def _resolve_fake_dns(host, deadline):
    """Resolve proxy fake-IP responses without ever connecting to a private IP.

    Only a public hostname is sent to the fixed, TLS-verified resolver; course
    URL paths, tokens and cookies never leave through the DNS query.
    """
    name = host.lower().rstrip('.')
    if (len(name) > 253 or '.' not in name
            or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in name.split('.'))
            or name.endswith(('.localhost', '.local', '.internal', '.test', '.invalid', '.example', '.onion', '.lan', '.home', '.arpa'))):
        raise CoverUnavailable('Not a public DNS name')
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        raise CoverUnavailable('Literal addresses cannot use public DNS fallback')
    end = min(deadline, time.monotonic() + 5.0)
    connection = _PinnedHTTPS('cloudflare-dns.com', 443, '1.1.1.1', _remaining(end))
    try:
        connection.request('GET', '/dns-query?' + urlencode({'name': name, 'type': 'A'}),
            headers={'Accept': 'application/dns-json', 'Accept-Encoding': 'identity', 'Connection': 'close'})
        read_socket = connection.sock
        response = connection.getresponse()
        if response.status != 200 or response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise CoverUnavailable('Public DNS unavailable')
        body = bytearray()
        while True:
            remaining = _remaining(end)
            if read_socket is not None and read_socket.fileno() >= 0:
                read_socket.settimeout(remaining)
            chunk = response.read1(min(4096, 16385 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > 16384:
                raise CoverUnavailable('Public DNS response too large')
        data = json.loads(body)
        questions = data.get('Question', [])
        if (data.get('Status') != 0 or data.get('TC') or len(questions) != 1
                or questions[0].get('type') != 1
                or str(questions[0].get('name', '')).lower().rstrip('.') != name):
            raise CoverUnavailable('Public DNS answer mismatch')
        addresses = []
        for answer in data.get('Answer', []):
            if answer.get('type') in (1, 28):
                address = _public_ip(answer.get('data', ''))
                if answer['type'] == 1 and ipaddress.ip_address(address).version == 4:
                    addresses.append(address)
        if not addresses:
            raise CoverUnavailable('No public DNS address')
        return sorted(addresses)[0]
    finally:
        connection.close()


def _target(url, deadline):
    if not isinstance(url, str) or len(url) > 4096 or re.search(r'[\s\\\x00-\x1f\x7f]', url):
        raise CoverUnavailable('Invalid URL')
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise CoverUnavailable('Unsupported URL')
    port = parsed.port if parsed.port is not None else (443 if parsed.scheme == 'https' else 80)
    if port != (443 if parsed.scheme == 'https' else 80):
        raise CoverUnavailable('Unsupported port')
    host = parsed.hostname.rstrip('.').encode('idna').decode('ascii')
    if not host or '%' in host:
        raise CoverUnavailable('Invalid host')
    ip = _resolve_public(host, port, deadline)
    path = urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
    return parsed.scheme, host, port, ip, path


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        # A numeric IP is passed to the socket, never the hostname a second time.
        self.sock = socket.create_connection((self._ip, self.port), timeout=self.timeout)


class _PinnedHTTPS(_PinnedHTTP):
    def connect(self):
        super().connect()
        self.sock = _TLS_CONTEXT.wrap_socket(self.sock, server_hostname=self.host)


@dataclass(frozen=True)
class _Fetched:
    url: str
    mime: str
    data: bytes


def _fetch(url, deadline, *, image_only=False):
    """Fetch a small resource with no cookies, proxies, decompression or redirects hidden from validation."""
    visited = set()
    for _ in range(4):
        if url in visited:
            raise CoverUnavailable('Redirect loop')
        visited.add(url)
        scheme, host, port, ip, path = _target(url, deadline)
        connection = (_PinnedHTTPS if scheme == 'https' else _PinnedHTTP)(host, port, ip, _remaining(deadline))
        try:
            connection.request('GET', path, headers={
                'User-Agent': 'MuchenJourney-CourseCover/1.0',
                'Accept': 'image/*' if image_only else 'text/html,video/*,image/*;q=0.8',
                'Accept-Encoding': 'identity', 'Connection': 'close',
            })
            read_socket = connection.sock
            if read_socket is not None:
                read_socket.settimeout(_remaining(deadline))
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise CoverUnavailable('Missing redirect')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise CoverUnavailable('Resource unavailable')
            if response.getheader('Content-Encoding', 'identity').strip().lower() not in ('', 'identity'):
                raise CoverUnavailable('Compressed response not accepted')
            mime = response.getheader('Content-Type', '').partition(';')[0].strip().lower()
            limit = MAX_IMAGE_BYTES if image_only or mime.startswith('image/') else MAX_LINK_VIDEO_BYTES if mime.startswith('video/') or mime == 'application/octet-stream' else MAX_HTML_BYTES
            length = response.getheader('Content-Length')
            if length is not None and (not length.isdigit() or int(length) > limit):
                raise CoverUnavailable('Resource too large')
            body = bytearray()
            while True:
                remaining = _remaining(deadline)
                if read_socket is not None and read_socket.fileno() >= 0:
                    read_socket.settimeout(remaining)
                # read1 avoids a slow server extending one read indefinitely by
                # sending a few bytes before each socket timeout.
                chunk = response.read1(min(65536, limit + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > limit:
                    raise CoverUnavailable('Resource too large')
            return _Fetched(url, mime, bytes(body))
        finally:
            connection.close()
    raise CoverUnavailable('Too many redirects')


class _CoverHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.primary = []
        self.secondary = []
        self.posters = []

    def handle_starttag(self, tag, attrs):
        values = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == 'meta':
            name = (values.get('property') or values.get('name') or '').lower()
            content = values.get('content', '').strip()
            if name in ('og:image', 'og:image:url', 'og:image:secure_url') and content:
                self.primary.append(content)
            elif name in ('twitter:image', 'twitter:image:src') and content:
                self.secondary.append(content)
        elif tag.lower() == 'video' and values.get('poster'):
            self.posters.append(values['poster'].strip())

    def candidates(self, base_url):
        unique = []
        for value in self.primary + self.secondary + self.posters:
            absolute = urljoin(base_url, value)
            if absolute not in unique:
                unique.append(absolute)
        return unique[:3]


def _input_options(prefix, *, image=False):
    if image:
        if prefix.startswith(b'\x89PNG\r\n\x1a\n'):
            demuxer = 'png_pipe'
        elif prefix.startswith(b'\xff\xd8\xff'):
            demuxer = 'jpeg_pipe'
        elif prefix.startswith((b'GIF87a', b'GIF89a')):
            demuxer = 'gif'
        elif prefix[:4] == b'RIFF' and prefix[8:12] == b'WEBP':
            demuxer = 'webp_pipe'
        else:
            raise CoverUnavailable('Unsupported cover image')
        return ['-f', demuxer]
    if len(prefix) >= 12 and prefix[4:8] == b'ftyp':
        return ['-f', 'mov']
    if prefix.startswith(b'\x1a\x45\xdf\xa3') and b'webm' in prefix[:4096].lower():
        return ['-f', 'matroska']
    if prefix.startswith(b'OggS') and b'theora' in prefix:
        return ['-f', 'ogg']
    raise CoverUnavailable('Unsupported video container')


def _run(command, deadline, *, output=False):
    return subprocess.run(command, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if output else subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=_remaining(deadline, 10.0), check=True).stdout


def _extract(path, deadline, *, image=False):
    with path.open('rb') as source:
        options = _input_options(source.read(65536), image=image)
    common = ['-v', 'error', '-max_alloc', str(64 * 1024 * 1024),
              '-protocol_whitelist', 'file,pipe', '-probesize', '5000000', '-analyzeduration', '5000000']
    probe = json.loads(_run(['ffprobe', *common, *options, '-show_entries',
        'stream=codec_type,width,height:format=duration', '-of', 'json', str(path)], deadline, output=True))
    streams = [stream for stream in probe.get('streams', []) if stream.get('codec_type') == 'video']
    if not streams or any(int(s.get('width', 0)) * int(s.get('height', 0)) > MAX_PIXELS for s in streams):
        raise CoverUnavailable('Unsupported frame size')
    try:
        duration = float(probe.get('format', {}).get('duration', 0))
    except (ValueError, TypeError):
        duration = 0
    if not math.isfinite(duration) or duration < 0:
        duration = 0
    seek = 0.0
    with tempfile.TemporaryDirectory(prefix='journey-cover-frame-') as folder:
        folder = Path(folder)
        if not image:
            candidates = [min(5.0, duration * .12), min(30.0, duration * .5), 0.0] if duration else [0.5, 0.0]
            best_score = -1
            for candidate in dict.fromkeys(candidates):
                sample = folder / 'sample.gray'
                try:
                    _run(['ffmpeg', '-nostdin', '-y', *common, '-threads', '1', '-max_pixels', str(MAX_PIXELS),
                        *options, '-ss', str(candidate), '-i', str(path), '-map', '0:v:0', '-an', '-sn', '-dn',
                        '-filter_threads', '1', '-vf', 'scale=64:36,format=gray', '-frames:v', '1',
                        '-threads', '1', '-f', 'rawvideo', '-fs', '2304', str(sample)], deadline)
                    pixels = sample.read_bytes()
                    if len(pixels) != 2304:
                        continue
                    score = sum(pixels) / len(pixels)
                    if score > best_score:
                        best_score, seek = score, candidate
                    if score > 16:
                        break
                except (OSError, subprocess.SubprocessError):
                    continue
        output_path = folder / 'cover.jpg'
        _run(['ffmpeg', '-nostdin', '-y', *common, '-threads', '1', '-max_pixels', str(MAX_PIXELS),
            *options, *([] if image else ['-ss', str(seek)]), '-i', str(path), '-map', '0:v:0', '-an', '-sn', '-dn',
            '-filter_threads', '1', '-vf', "scale=w='min(960,iw)':h='min(540,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
            '-frames:v', '1', '-threads', '1', '-c:v', 'mjpeg', '-q:v', '4', '-pix_fmt', 'yuvj420p',
            '-f', 'image2', '-update', '1', '-fs', str(MAX_COVER_BYTES + 1), str(output_path)], deadline)
        if output_path.stat().st_size > MAX_COVER_BYTES:
            raise CoverUnavailable('Cover too large')
        data = output_path.read_bytes()
        if not data.startswith(b'\xff\xd8\xff') or not data.endswith(b'\xff\xd9'):
            raise CoverUnavailable('Invalid JPEG output')
        return data


def extract_video_cover(path: str | Path) -> bytes | None:
    """Extract a reasonably bright frame from a completed local upload."""
    if not _DECODER_SLOTS.acquire(blocking=False):
        raise CoverBusy('Decoder busy')
    try:
        source = Path(path)
        if not source.is_file() or source.stat().st_size > MAX_LOCAL_VIDEO_BYTES:
            return None
        return _extract(source, time.monotonic() + VIDEO_TIMEOUT)
    except Exception:
        return None
    finally:
        _DECODER_SLOTS.release()


def extract_link_cover(url: str) -> bytes | None:
    """Try public metadata/poster images or a small directly linked video."""
    if not _DECODER_SLOTS.acquire(blocking=False):
        raise CoverBusy('Decoder busy')
    try:
        deadline = time.monotonic() + LINK_TIMEOUT
        resource = _fetch(url, deadline)
        with tempfile.TemporaryDirectory(prefix='journey-cover-link-') as folder:
            source = Path(folder) / 'source'
            # Signature checks ensure neither a playlist nor SVG reaches ffmpeg.
            try:
                _input_options(resource.data[:65536])
                source.write_bytes(resource.data)
                return _extract(source, deadline)
            except CoverUnavailable:
                pass
            if resource.mime.startswith('image/'):
                _input_options(resource.data[:65536], image=True)
                source.write_bytes(resource.data)
                return _extract(source, deadline, image=True)
            if resource.mime not in ('text/html', 'application/xhtml+xml', '') or len(resource.data) > MAX_HTML_BYTES:
                return None
            parser = _CoverHTML()
            parser.feed(resource.data.decode('utf-8', errors='replace'))
            for image_url in parser.candidates(resource.url):
                try:
                    image_resource = _fetch(image_url, deadline, image_only=True)
                    _input_options(image_resource.data[:65536], image=True)
                    source.write_bytes(image_resource.data)
                    return _extract(source, deadline, image=True)
                except (CoverUnavailable, OSError, ValueError, subprocess.SubprocessError, http.client.HTTPException):
                    continue
        return None
    except CoverBusy:
        raise
    except Exception:
        return None
    finally:
        _DECODER_SLOTS.release()
