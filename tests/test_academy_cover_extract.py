"""Cover extraction is optional and must not turn course URLs into SSRF."""
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time

import pytest

from journey_api import academy_cover_extract as cover


class Response:
    def __init__(self, status=200, headers=None, data=b''):
        self.status = status
        self.headers = headers or {}
        self.body = io.BytesIO(data)

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read1(self, count):
        return self.body.read(count)


def fake_http(monkeypatch, responses):
    calls = []

    class Connection:
        sock = None

        def __init__(self, host, port, ip, timeout):
            calls.append({'host': host, 'port': port, 'ip': ip, 'timeout': timeout})

        def request(self, method, path, headers):
            calls[-1].update(method=method, path=path, headers=headers)

        def getresponse(self):
            return responses.pop(0)

        def close(self):
            calls[-1]['closed'] = True

    monkeypatch.setattr(cover, '_PinnedHTTP', Connection)
    monkeypatch.setattr(cover, '_PinnedHTTPS', Connection)
    return calls


@pytest.mark.parametrize('address', [
    '127.0.0.1', '10.0.0.1', '172.16.2.3', '192.168.1.1', '169.254.169.254',
    '100.64.1.1', '0.0.0.0', '224.0.0.1', '::1', 'fe80::1', 'fc00::1',
    '::ffff:8.8.8.8', '2002:7f00:0001::',
])
def test_non_public_and_transition_addresses_rejected(address):
    with pytest.raises(cover.CoverUnavailable):
        cover._public_ip(address)


@pytest.mark.parametrize('url', [
    'file:///etc/passwd', 'ftp://example.com/a', 'http://user:secret@example.com/',
    'https://example.com:8000/', 'http://example.com:443/', 'http://example.com:0/', 'https://example.com/\r\nHeader:x',
    'http://example.com\\@localhost/', 'http://[fe80::1%25eth0]/',
])
def test_invalid_url_rejected_before_network(url, monkeypatch):
    monkeypatch.setattr(cover, '_resolve_public', lambda *args: pytest.fail('No DNS expected'))
    assert cover.extract_link_cover(url) is None


def test_all_resolved_addresses_must_be_public(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args: [
        (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('8.8.8.8', 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('127.0.0.1', 443)),
    ])
    with pytest.raises(cover.CoverUnavailable):
        cover._resolve_public('video.example', 443, time.monotonic() + 5)


@pytest.mark.parametrize('answer_name', ['video.public-course.com.', 'video.public-course.com'])
def test_proxy_fake_dns_resolves_only_to_validated_public_ip(monkeypatch, answer_name):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args: [
        (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('198.18.0.148', 443))])
    reply = {'Status': 0, 'Question': [{'name': answer_name, 'type': 1}],
             'Answer': [{'type': 1, 'data': '8.8.8.8'}]}
    calls = fake_http(monkeypatch, [Response(data=json.dumps(reply).encode())])
    assert cover._resolve_public('video.public-course.com', 443, time.monotonic() + 5) == '8.8.8.8'
    assert calls[0]['host'] == 'cloudflare-dns.com' and calls[0]['ip'] == '1.1.1.1'
    assert calls[0]['path'] == '/dns-query?name=video.public-course.com&type=A'


@pytest.mark.parametrize('bad', [
    {'Status': 2}, {'Question': [{'name': 'wrong.com.', 'type': 1}]},
    {'Answer': [{'type': 1, 'data': '127.0.0.1'}]},
    {'Answer': [{'type': 1, 'data': '8.8.8.8'}, {'type': 28, 'data': '::1'}]},
    {'Answer': [{'type': 1, 'data': '198.18.0.148'}]}, {'TC': True},
])
def test_public_dns_fallback_rejects_private_or_mismatched_answers(monkeypatch, bad):
    reply = {'Status': 0, 'Question': [{'name': 'video.public-course.com.', 'type': 1}],
             'Answer': [{'type': 1, 'data': '8.8.8.8'}], **bad}
    fake_http(monkeypatch, [Response(data=json.dumps(reply).encode())])
    with pytest.raises(cover.CoverUnavailable):
        cover._resolve_fake_dns('video.public-course.com', time.monotonic()+5)


@pytest.mark.parametrize('host', ['127.0.0.1', 'localhost', 'video.local', 'video.internal', 'video.test'])
def test_private_names_never_reach_public_dns_fallback(monkeypatch, host):
    calls = fake_http(monkeypatch, [])
    with pytest.raises(cover.CoverUnavailable):
        cover._resolve_fake_dns(host, time.monotonic()+5)
    assert not calls


def test_decoder_capacity_is_retryable_not_an_unavailable_cover():
    cover._DECODER_SLOTS.acquire()
    cover._DECODER_SLOTS.acquire()
    try:
        with pytest.raises(cover.CoverBusy):
            cover.extract_link_cover('https://example.com/')
        with pytest.raises(cover.CoverBusy):
            cover.extract_video_cover('/missing.mp4')
    finally:
        cover._DECODER_SLOTS.release()
        cover._DECODER_SLOTS.release()


def test_connection_uses_pinned_ip_and_tls_keeps_original_host(monkeypatch):
    addresses, tls_hosts = [], []
    raw_socket = object()
    monkeypatch.setattr(socket, 'create_connection', lambda target, timeout: addresses.append(target) or raw_socket)

    class TLS:
        def wrap_socket(self, sock, server_hostname):
            assert sock is raw_socket
            tls_hosts.append(server_hostname)
            return sock

    monkeypatch.setattr(cover, '_TLS_CONTEXT', TLS())
    connection = cover._PinnedHTTPS('video.example', 443, '8.8.8.8', 2)
    # DNS changing after validation cannot alter the socket destination.
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args: pytest.fail('Must not resolve hostname again'))
    connection.connect()
    assert addresses == [('8.8.8.8', 443)]
    assert tls_hosts == ['video.example']


def test_redirect_to_private_address_is_not_requested(monkeypatch):
    def addresses(host, port, *args):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('127.0.0.1' if host == 'internal.example' else '8.8.8.8', port))]

    monkeypatch.setattr(socket, 'getaddrinfo', addresses)
    calls = fake_http(monkeypatch, [Response(302, {'Location': 'http://internal.example/secrets'})])
    assert cover.extract_link_cover('https://video.example/lesson') is None
    assert len(calls) == 1
    assert calls[0]['closed']
    assert 'Cookie' not in calls[0]['headers'] and 'Authorization' not in calls[0]['headers']


def test_http_connection_close_with_content_length_reads_complete_body(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = b'<html><video poster="cover.png"></video></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # This test-only target is our disposable HTTP server, not a real URL input.
    monkeypatch.setattr(cover, '_target', lambda url, deadline: ('http', 'video.example', server.server_port, '127.0.0.1', '/'))
    try:
        fetched = cover._fetch('http://video.example/', time.monotonic() + 5)
        assert fetched.data == b'<html><video poster="cover.png"></video></html>'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize('response', [
    Response(headers={'Content-Type': 'text/html', 'Content-Length': '33'}),
    Response(headers={'Content-Type': 'text/html'}, data=b'x' * 33),
    Response(headers={'Content-Type': 'text/html', 'Content-Encoding': 'gzip'}, data=b'compressed'),
    Response(401, {'Content-Type': 'text/html'}, b'Please login'),
])
def test_oversized_compressed_and_error_responses_fall_back(response, monkeypatch):
    monkeypatch.setattr(cover, '_resolve_public', lambda *args: '8.8.8.8')
    monkeypatch.setattr(cover, 'MAX_HTML_BYTES', 32)
    fake_http(monkeypatch, [response])
    monkeypatch.setattr(cover, '_extract', lambda *args, **kwargs: pytest.fail('No decoder expected'))
    assert cover.extract_link_cover('https://video.example/lesson') is None


def test_metadata_relative_urls_use_final_page_and_try_alternative_images(monkeypatch):
    fetched = []
    jpeg = b'\xff\xd8\xffsample\xff\xd9'

    def fetch(url, deadline, image_only=False):
        fetched.append((url, image_only))
        if not image_only:
            return cover._Fetched('https://video.example/lessons/latest/', 'text/html', b'''
                <meta property="og:image" content="missing.png">
                <meta name="twitter:image" content="../../covers/lesson.jpg">
                <video poster="/unused.png"></video>''')
        if url.endswith('missing.png'):
            raise cover.CoverUnavailable('Not found')
        return cover._Fetched(url, 'image/jpeg', jpeg)

    monkeypatch.setattr(cover, '_fetch', fetch)
    monkeypatch.setattr(cover, '_extract', lambda path, deadline, image=False: path.read_bytes() if image else None)
    assert cover.extract_link_cover('https://video.example/start') == jpeg
    assert fetched == [
        ('https://video.example/start', False),
        ('https://video.example/lessons/latest/missing.png', True),
        ('https://video.example/covers/lesson.jpg', True),
    ]


def test_svg_playlist_and_login_page_use_default_cover(monkeypatch):
    for mime, body in [('image/svg+xml', b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
                       ('application/vnd.apple.mpegurl', b'#EXTM3U\nhttp://127.0.0.1/secret'),
                       ('text/html', b'<html><h1>Login required</h1></html>')]:
        monkeypatch.setattr(cover, '_fetch', lambda url, deadline, image_only=False: cover._Fetched(url, mime, body))
        monkeypatch.setattr(cover, '_extract', lambda *args, **kwargs: pytest.fail('No decoder expected'))
        assert cover.extract_link_cover('https://video.example/lesson') is None


def test_missing_decoder_and_invalid_upload_never_escape(tmp_path, monkeypatch):
    assert cover.extract_video_cover(tmp_path / 'missing.mp4') is None
    file = tmp_path / 'course.mp4'
    file.write_bytes(b'\x00\x00\x00\x18ftypisom' + bytes(32))
    monkeypatch.setattr(cover, '_run', lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    assert cover.extract_video_cover(file) is None


def ffmpeg_available():
    return shutil.which('ffmpeg') and shutil.which('ffprobe')


def run_media(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, timeout=15, **kwargs).stdout


@pytest.mark.skipif(not ffmpeg_available(), reason='Real media checks run in the API image with ffmpeg')
def test_real_short_uploaded_video_avoids_black_intro_and_outputs_small_jpeg(tmp_path):
    file = tmp_path / 'short.mp4'
    run_media(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=160x90:r=10:d=1',
        '-f', 'lavfi', '-i', 'color=c=white:s=160x90:r=10:d=1',
        '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0', '-filter_complex_threads', '1',
        '-c:v', 'mpeg4', '-threads', '1', str(file)])
    result = cover.extract_video_cover(file)
    assert result and result.startswith(b'\xff\xd8\xff') and len(result) < cover.MAX_COVER_BYTES
    pixels = run_media(['ffmpeg', '-v', 'error', '-f', 'jpeg_pipe', '-i', 'pipe:0',
        '-vf', 'scale=16:9,format=gray', '-filter_threads', '1', '-frames:v', '1', '-threads', '1',
        '-f', 'rawvideo', 'pipe:1'], input=result)
    assert sum(pixels) / len(pixels) > 150


@pytest.mark.skipif(not ffmpeg_available(), reason='Real media checks run in the API image with ffmpeg')
def test_real_metadata_image_is_normalized_and_resized(tmp_path, monkeypatch):
    image = tmp_path / 'cover.png'
    run_media(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=1600x900',
        '-frames:v', '1', '-threads', '1', str(image)])

    def fetch(url, deadline, image_only=False):
        return cover._Fetched(url, 'image/png', image.read_bytes()) if image_only else cover._Fetched(
            url, 'text/html', b'<meta property="og:image" content="/cover.png">')

    monkeypatch.setattr(cover, '_fetch', fetch)
    result = cover.extract_link_cover('https://video.example/course')
    assert result and len(result) < cover.MAX_COVER_BYTES
    output = tmp_path / 'result.jpg'
    output.write_bytes(result)
    dimensions = json.loads(run_media(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height',
        '-of', 'json', str(output)]))['streams'][0]
    assert dimensions == {'width': 960, 'height': 540}
