"""Shared upload limits and file signatures for supported video formats."""
MAX_VIDEO_SIZE = 2 * 1024 ** 3
VIDEO_TYPES = {'mp4': 'video/mp4', 'm4v': 'video/mp4', 'mov': 'video/quicktime',
               'webm': 'video/webm', 'ogv': 'video/ogg', 'ogg': 'video/ogg'}


def media_signature(data, mime):
    if mime in ('video/mp4', 'video/quicktime'):
        return len(data) >= 12 and data[4:8] == b'ftyp'
    if mime == 'video/webm':
        return data.startswith(b'\x1a\x45\xdf\xa3') and b'webm' in data[:4096].lower()
    if mime == 'video/ogg':
        return data.startswith(b'OggS') and b'theora' in data[:65536]
    return False
