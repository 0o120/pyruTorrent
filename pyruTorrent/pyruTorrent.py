# Copyright (c) 2022 0x78, <contact@0x78.com>
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import xmlrpc.client
import base64
import requests
import json
import time
import re
import bencodepy
from functools import wraps
from hashlib import sha1
from urllib.parse import quote, unquote


class Misc:
    
    def parseNumber(n):
        if isinstance(n, str) and len(n) > 0:
            try:
                return '.' in n and float(n) or int(n)
            except:
                pass
        if isinstance(n, (int, float)):
            return n
        return None
        
    def to_uri(*args, **kwargs):
        uri = kwargs.get('uri')
        if uri:
            return uri
        scheme = kwargs.get('scheme', 'https')
        host = kwargs.get('host')
        port = kwargs.get('port')
        username = kwargs.get('username')
        password = kwargs.get('password')
        _path = kwargs.get('rpc_path')
        return (f'{scheme}://'
                f'{username or ""}{password and f":{password}" or ""}{username and "@" or ""}'
                f'{host}{port and f":{port}" or ""}{_path or ""}')


class BencodeUtils:
    
    def __init__(self):
        self.bc = bencodepy.Bencode(encoding='utf-8', encoding_fallback='value')
    
    def from_filepath(self, fp):
        result = self.bc.read(fp)
        return result
        
    def from_filepath_as_b64(self, fp):
        obj = self.from_filepath(fp)
        _bytes = self.to_bytes(obj)
        return base64.b64encode(_bytes)
        
    def from_bytes(self, _bytes):
        result = self.bc.decode(_bytes)
        return result
        
    def to_bytes(self, obj):
        return self.bc.encode(obj)
        
    def to_b64(self, obj):
        return base64.b64encode(self.to_bytes(obj))
        
    def to_filepath(self, fp, obj):
        if isinstance(obj, bytes):
            obj = self.read_from_bytes(obj)
        self.bc.write(obj, fp)
        
    def info_to_hash(self, info):
        return sha1(bencodepy.bencode(info)).hexdigest()


class rTorrentRPC:
    
    def __init__(self, **kwargs):
        self.rpc_uri = Misc.to_uri(**kwargs)
        self.client = xmlrpc.client.ServerProxy(uri=self.rpc_uri, verbose=False, allow_none=True)


class RPCMethodHelpers:
    
    @staticmethod
    def get(key, method, *args, **kwargs):
        return {'key': key, 'methodName': method, 'params': [*args], **kwargs}
        
    def convert_d_multicall(methods=None, view=None, **kwargs):
        calls = []
        keys = []
        if isinstance(kwargs.get('ratio_group'), (str, int)):
            view = RPCMethodHelpers.parse_ratio_group(kwargs.get('ratio_group'))
        for method in methods:
            _call = ''
            m_key = method['key']
            m_methodName = method['methodName']
            m_params = method['params']
            m_params.pop(0)
            _call += m_methodName
            if not m_methodName.endswith('='):
                _call += '='
            _call += ','.join([str(i) if not i is None else '' for i in m_params])
            calls.append(_call)
            keys.append(m_key)
        return list([RPCMethodHelpers.get('d.multicall2', 'd.multicall2', '', view or '', *calls, keys=keys)])
        
    def formatter(func):
        @wraps(func)
        def inner_func(*args, **kwargs):
            # print(*args, {**kwargs})
            output = []
            methods = func(*args, **kwargs)
            k_filter = kwargs.get('only_keys')
            k_only = kwargs.get('only_keys')
            k_exclude = kwargs.get('exclude_keys')
            if isinstance(k_only, str):
                k_only = [k_only]
            k_only = k_only or []
            if isinstance(k_exclude, str):
                k_exclude = [k_exclude]
            k_exclude = k_exclude or []
            for k in list(methods.keys()):
                if k_exclude and k in k_exclude:
                    del methods[k]
                    continue
                if k_only and k not in k_only:
                    del methods[k]
                    continue
                output.append(RPCMethodHelpers.get(k, *methods[k]))
            return output
        return inner_func
        
    def parse_result(key, val):
        
        if isinstance(val, list) and len(val) == 1:
            val = val[0]
        
        if key == 'comment':
            # Remove the string "VRS24mrker" from comment,
            # it is automatically prepended by rTorrent.
            if isinstance(val, str) and val.startswith('VRS24mrker'):
                val = val[len('VRS24mrker'):]
                val = unquote(val)
        elif key == 'seeding_time':
            val = Misc.parseNumber(val)
            if isinstance(val, int):
                val = int(time.time() - val)
        elif key == 'ratio_group':
            if isinstance(val, list) and len(val) > 0:
                val = val[0]
            if isinstance(val, str):
                val = re.findall('.*?rat_([0-9]+)', val)
                val = len(val) > 0 and int(val[0]) + 1 or None
        elif key == 'ratio':
            if isinstance(val, int):
                val = round(val * .001, 3)
        elif key in KeyMaps._maps_:
            if len(val) > 0:
                if not isinstance(val[0], list):
                    val = list([val])
                val = [{k: r[idx] for idx, k in enumerate(KeyMaps._maps_[key]['_meta_']['keys'])} for r in val]
            else:
                val = None
        return val
        
    def parse_method_result(method_key, method_response, multicall_d_keys=None):
        if multicall_d_keys and len(method_response) > 0:
            output_multicall_d = dict(zip(multicall_d_keys, method_response))
            for m_key, m_result in output_multicall_d.items():
                output_multicall_d[m_key] = RPCMethodHelpers.parse_result(m_key, m_result)
            return output_multicall_d
        return RPCMethodHelpers.parse_result(method_key, method_response)
        
    def parse_method_response(methods, response, count=1):
        result_len = int(len(methods) / count)
        result = []
        
        if len(response) > 0 and isinstance(response[0], dict) and response[0].get('faultCode'):
            raise Exception(f'Error in parse_method_response, error response:\n{pformat(response)}\n')
        idx = 0
        result_idx = -1
        for method, method_resp in zip(methods, response):
            method_multicall_d_keys = method.get('keys')
            method_key = method['key']
            if method_multicall_d_keys:
                if len(method_resp) > 0:
                    method_resp = method_resp[0]
                for sub_method_resp in method_resp:
                    result.append(RPCMethodHelpers.parse_method_result(method_key, sub_method_resp, multicall_d_keys=method_multicall_d_keys))
            else:
                if idx % result_len == 0:
                    result.append({})
                    result_idx += 1
                result[result_idx][method_key] = RPCMethodHelpers.parse_method_result(method_key, method_resp)
                idx += 1
        return result
        
    def parse_ratio_group(ratio_group):
        grp_idx_min = 1
        grp_idx_max = 8
        grp_idx = None
        if isinstance(ratio_group, list):
            ratio_group = ratio_group and ratio_group[0] or None
        if isinstance(ratio_group, int):
            grp_idx = ratio_group - 1
        elif isinstance(ratio_group, str):
            if 'rat_' in ratio_group:
                grp_idx = int(ratio_group.replace('rat_', ''))
            else:
                grp_idx = int(ratio_group) - 1
        if isinstance(grp_idx, int) and not (grp_idx_min <= grp_idx+1 <= grp_idx_max):
            raise ValueError(f'Invalid ratio_group index {grp_idx+1}, must be between {grp_idx_min} and {grp_idx_max}.')
        return isinstance(grp_idx, int) and f'rat_{grp_idx}' or None
        
    def parse_set_settings(settings):
        output = {}
        if isinstance(settings, dict):
            for setting_key, setting_val in settings.items():
                setting_key_name = setting_key
                if setting_key_name.startswith('set_') or setting_key_name.startswith('get_'):
                    setting_key_name = setting_key_name[4:]
                if setting_key.startswith('get_'):
                    setting_key = setting_key[4:]
                if not setting_key.startswith('set_'):
                    setting_key = 'set_' + setting_key
                output[setting_key_name] = (setting_key, '' if setting_val is None else setting_val)
        return output

class KeyMaps:
    
    _tracker_map_ = {
        'url':                  't.url=',
        'type':                 't.type=',
        'is_enabled':           't.is_enabled=',
        'group':                't.group=',
        'scrape_complete':      't.scrape_complete=',
        'scrape_incomplete':    't.scrape_incomplete=',
        'scrape_downloaded':    't.scrape_downloaded=',
        'scrape_counter':       't.scrape_counter=',
        'normal_interval':      't.normal_interval=',
        'scrape_time_last':     't.scrape_time_last=',
        'failed_counter':       't.failed_counter=',
        'success_counter':      't.success_counter=',
        'is_busy':              't.is_busy=',
        'latest_event':         't.latest_event=',
        'latest_new_peers':     't.latest_new_peers=',
        'latest_sum_peers':     't.latest_sum_peers=',
        '_meta_': {
                                'group_name': 'trackers',
                                'methods': [],
                                'keys': []
        }
    }

    _file_map_ = {
        'path':                 'f.path=',
        'frozen_path':          'f.frozen_path=',
        'is_created':           'f.is_created=',
        'is_open':              'f.is_open=',
        'priority':             'f.priority=',
        'chunks_completed':     'f.completed_chunks=',
        'chunks_total':         'f.size_chunks=',
        'is_complete':          'equal=f.size_chunks=,f.completed_chunks=',
        '_meta_': {
                                'group_name': 'files',
                                'methods': [],
                                'keys': []
        }
    }

    _peer_map_ = {
        'id':                   'p.id=',
        'address':              'p.address=',
        'port':                 'p.port=',
        'client_version':       'p.client_version=',
        'completed_percent':    'p.completed_percent=',
        'down_rate':            'p.down_rate=',
        'down_total':           'p.down_total=',
        'up_rate':              'p.up_rate=',
        'up_total':             'p.up_total=',
        'peer_rate':            'p.peer_total=',
        'is_incoming':          'p.is_incoming=',
        'is_obfuscated':        'p.is_obfuscated=',
        'is_preferred':         'p.is_preferred=',
        'is_snubbed':           'p.is_snubbed=',
        'is_banned':            'p.banned=',
        '_meta_': {
                                'group_name': 'peers',
                                'methods': [],
                                'keys': []
        }
    }
    
    _map_array_ = [_tracker_map_, _file_map_, _peer_map_]
    
    _maps_ = {}
    
    for _map_ in _map_array_:
        for key, method in _map_.items():
            if not key.startswith('_') and not key.endswith('_') and isinstance(method, str):
                _map_['_meta_']['keys'].append(key)
                _map_['_meta_']['methods'].append(method)
        _maps_[_map_['_meta_']['group_name']] = _map_



class RPCMethods(RPCMethodHelpers):
    

    @RPCMethodHelpers.formatter
    def get_torrent(_hash, **kwargs):
        _trackers_ = KeyMaps._tracker_map_['_meta_']['group_name']
        _files_ = KeyMaps._file_map_['_meta_']['group_name']
        _peers_ = KeyMaps._peer_map_['_meta_']['group_name']
        return {
            'hash':                 ('d.hash', _hash),
            'name':                 ('d.name', _hash),
            'label':                ('d.custom1', _hash),
            'ratio':                ('d.ratio', _hash),
            'ratio_group':          ('d.views', _hash),
            'priority':             ('d.priority', _hash),              # 0: off | 1: low | 2: normal | 3: high
            'priority_str':         ('d.priority_str', _hash),          # off | low | normal | high
            'seeding_time':         ('d.custom', _hash, 'seedingtime'),
            'file_count':           ('d.size_files', _hash),
            'comment':              ('d.custom2', _hash),
            'bytes_done':           ('d.bytes_done', _hash),
            'bytes_left':           ('d.left_bytes', _hash),
            'bytes_total':          ('d.size_bytes', _hash),
            'bytes_chunk_size':     ('d.size_chunks', _hash),
            'hashing':              ('d.hashing', _hash),               # 0: false | 1: Hashing | 2: Download Finished & Hashing  | 3: Rehashing
            'hashing_checked':      ('d.is_hash_checked', _hash),
            'hashing_checking':     ('d.is_hash_checking', _hash),
            'state':                ('d.state', _hash),                 # 1: Paused|Started 0: Stopped,
            'state_is_active':      ('d.is_active', _hash),
            'state_is_open':        ('d.is_open', _hash),
            'state_counter':        ('d.state_counter', _hash),
            'state_changed':        ('d.state_changed', _hash),
            'peers_complete':       ('d.peers_complete', _hash),
            'peers_accounted':      ('d.peers_accounted', _hash),
            'peers_connected':      ('d.peers_connected', _hash),
            'peers_max':            ('d.peers_max', _hash),
            'peers_min':            ('d.peers_min', _hash),
            'peers_not_connected':  ('d.peers_not_connected', _hash),
            'upload_speed':         ('d.up.rate', _hash),
            'upload_total':         ('d.up.total', _hash),
            'download_speed':       ('d.down.rate', _hash),
            'download_total':       ('d.down.total', _hash),
            'base_parent_path':     ('d.directory', _hash),
            'base_path':            ('d.base_path', _hash),
            'base_filename':        ('d.base_filename', _hash),
            'loaded_file':          ('d.loaded_file', _hash),
            'is_complete':          ('d.complete', _hash),
            'is_active':            ('d.is_active', _hash),
            'is_incomplete':        ('d.incomplete', _hash),
            'is_private':           ('d.is_private', _hash),
            'is_multi_file':        ('d.is_multi_file', _hash),
            'connection_current':   ('d.connection_current', _hash),    # leech | seed
            'timestamp_created':    ('d.creation_date', _hash),         # Timestamp torrent created
            'timestamp_added':      ('d.load_date', _hash),             # Timestamp torrent added
            'timestamp_started':    ('d.timestamp.started', _hash),     # Time started or resumed
            'timestamp_finished':   ('d.timestamp.finished', _hash),
            _trackers_:             ('t.multicall', _hash, '', *KeyMaps._tracker_map_['_meta_']['methods']),
            _files_:                ('f.multicall', _hash, '', *KeyMaps._file_map_['_meta_']['methods']),
            _peers_:                ('p.multicall', _hash, '', *KeyMaps._peer_map_['_meta_']['methods'])

        }
        
    def get_all_torrents(view='', **kwargs):
        return RPCMethodHelpers.convert_d_multicall(methods=RPCMethods.get_torrent(None, **kwargs), view=view, **kwargs)
    
    @RPCMethodHelpers.formatter
    def ratio_group_set(_hash, new_ratio_group):
        return {
            'd.views.push_back_unique': ('d.views.push_back_unique', _hash, new_ratio_group),
            'view.set_visible':         ('view.set_visible', _hash, new_ratio_group),
        }
    
    @RPCMethodHelpers.formatter
    def ratio_group_remove(_hash, old_ratio_group):
        return {
            'view.set_not_visible': ('view.set_not_visible', _hash, old_ratio_group),
            'd.views.remove': ('d.views.remove', _hash, old_ratio_group),
        }
    
    @RPCMethodHelpers.formatter
    def ratio_group_replace(_hash, old_ratio_group, new_ratio_group):
        return {
            'view.set_not_visible': ('view.set_not_visible', _hash, old_ratio_group),
            'd.views.remove': ('d.views.remove', _hash, old_ratio_group),
            'd.views.push_back_unique': ('d.views.push_back_unique', _hash, new_ratio_group),
            'view.set_visible': ('view.set_visible', _hash, new_ratio_group)
        }
        
    @RPCMethodHelpers.formatter
    def events_get(only_keys=None):
        return {
            'event.download.closed':              ('method.get', '', 'event.download.closed'),
            'event.download.erased':              ('method.get', '', 'event.download.erased'),
            'event.download.finished':            ('method.get', '', 'event.download.finished'),
            'event.download.hash_done':           ('method.get', '', 'event.download.hash_done'),
            'event.download.hash_failed':         ('method.get', '', 'event.download.hash_failed'),
            'event.download.hash_final_failed':   ('method.get', '', 'event.download.hash_final_failed'),
            'event.download.hash_queued':         ('method.get', '', 'event.download.hash_queued'),
            'event.download.hash_removed':        ('method.get', '', 'event.download.hash_removed'),
            'event.download.inserted':            ('method.get', '', 'event.download.inserted'),
            'event.download.inserted_new':        ('method.get', '', 'event.download.inserted_new'),
            'event.download.inserted_session':    ('method.get', '', 'event.download.inserted_session'),
            'event.download.opened':              ('method.get', '', 'event.download.opened'),
            'event.download.paused':              ('method.get', '', 'event.download.paused'),
            'event.download.resumed':             ('method.get', '', 'event.download.resumed')
        }
        
    @RPCMethodHelpers.formatter
    def events_set(event, name, method):
        return {
            'method.set_key':   ('method.set_key', '', event, name, method),
            'method.get':       ('method.get', '', event),
        }
        
    @RPCMethodHelpers.formatter
    def events_remove(event, name):
        return {
            'method.erase':     ('method.set_key', '', event, name),
            'method.get':       ('method.get', '', event),
        }

    @RPCMethodHelpers.formatter
    def torrent_add_file(_hash, data, name, comment, label, download_path, ratio_group, add_stopped, add_name_to_path, save_torrent):
        ratio_group = ratio_group and f'if=(not, (d.views)), (cat, $d.views.push_back_unique={ratio_group}, $view.set_visible={ratio_group}, $d.views=), (cat, "")' or ''
        return {
            'add_torrent':   (
                add_stopped and 'load.raw' or 'load.raw_start',
                '',
                data,
                f'd.set_custom1={label}',
                f'd.set_custom2=VRS24mrker{comment}',
                f'd.set_custom=x-filename,{quote(name)}',
                f'{"" if save_torrent else "d.delete_tied="}',
                f'execute=mkdir,-p,"{download_path}"',
                f'{"d.set_directory=" if add_name_to_path else "d.set_directory_base="}"{download_path}"',
                ratio_group
            ),
            'hash': ('cat', '', _hash),
            
        }
        
    @RPCMethodHelpers.formatter
    def torrent_add_magnet(_hash, magnet, label, download_path, ratio_group, add_stopped, add_name_to_path, save_torrent):
        ratio_group = ratio_group and f'if=(not, (d.views)), (cat, $d.views.push_back_unique={ratio_group}, $view.set_visible={ratio_group}, $d.views=), (cat, "")' or ''
        return {
            'add_torrent_magnet':   (
                add_stopped and 'load.normal' or 'load.start',
                '',
                magnet,
                f'd.set_custom1={label}',
                f'{"" if save_torrent else "d.delete_tied="}',
                f'execute=mkdir,-p,"{download_path}"',
                f'{"d.set_directory=" if add_name_to_path else "d.set_directory_base="}"{download_path}"',
                ratio_group
            ),
            'hash':             ('cat', '', _hash)
        }

    @RPCMethodHelpers.formatter
    def start(_hash, **kwargs):
        return {
            'hash':                 ('d.hash', _hash),
            'd.open':               ('d.open', _hash),
            'd.start':              ('d.start', _hash),
        }

    @RPCMethodHelpers.formatter
    def pause(_hash, **kwargs):
        return {
            'hash':                 ('d.hash', _hash),
            'd.stop':              ('d.stop', _hash),
        }

    @RPCMethodHelpers.formatter
    def unpause(_hash, **kwargs):
        return {
            'hash':                 ('d.hash', _hash),
            'd.start':              ('d.start', _hash),
        }

    @RPCMethodHelpers.formatter
    def stop(_hash, **kwargs):
        return {
            'hash':                 ('d.hash', _hash),
            'd.stop':               ('d.stop', _hash),
            'd.close':              ('d.close', _hash)
        }

    @RPCMethodHelpers.formatter
    def check_hash(_hash, **kwargs):
        return {
            'hash':                 ('d.hash', _hash),
            'd.check_hash':         ('d.check_hash', _hash),
        }

    @RPCMethodHelpers.formatter
    def remove(_hash, **kwargs):
        return {
            'hash':                 ('d.hash', _hash),
            'd.stop':               ('d.stop', _hash),
            'd.close':              ('d.close', _hash),
            'd.erase':              ('d.erase', _hash)
        }

    @RPCMethodHelpers.formatter
    def remove_and_delete(_hash, **kwargs):
        return {
            'hash':                 ('d.hash', _hash),
            'd.stop':               ('d.stop', _hash),
            'd.close':              ('d.close', _hash),
            'd.set_custom5':        ('d.set_custom5', _hash, '1'),
            'd.erase':              ('d.erase', _hash)
        }

    # @RPCMethodHelpers.formatter
    # def remove_and_delete_parent_contents(_hash, **kwargs): # Not being used
        # return {
            # 'hash':                 ('d.hash', _hash),
            # 'd.stop':               ('d.stop', _hash),
            # 'd.close':              ('d.close', _hash),
            # 'd.set_custom5':        ('d.set_custom5', _hash, '2'),
            # 'd.erase':              ('d.erase', _hash)
        # }
    
    def start_all(view='', **kwargs):
        return RPCMethodHelpers.convert_d_multicall(methods=RPCMethods.start(None, **kwargs), view=view, **kwargs)
        
    def pause_all(view='', **kwargs):
        return RPCMethodHelpers.convert_d_multicall(methods=RPCMethods.pause(None, **kwargs), view=view, **kwargs)
        
    def unpause_all(view='', **kwargs):
        return RPCMethodHelpers.convert_d_multicall(methods=RPCMethods.unpause(None, **kwargs), view=view, **kwargs)
        
    def stop_all(view='', **kwargs):
        return RPCMethodHelpers.convert_d_multicall(methods=RPCMethods.stop(None, **kwargs), view=view, **kwargs)
        
    def check_hash_all(view='', **kwargs):
        return RPCMethodHelpers.convert_d_multicall(methods=RPCMethods.check_hash(None, **kwargs), view=view, **kwargs)
        
    def remove_all(view='', **kwargs):
        return RPCMethodHelpers.convert_d_multicall(methods=RPCMethods.remove(None, **kwargs), view=view, **kwargs)
        
    def remove_and_delete_all(view='', **kwargs):
        return RPCMethodHelpers.convert_d_multicall(methods=RPCMethods.remove_and_delete(None, **kwargs), view=view, **kwargs)
        
    # def remove_and_delete_parent_contents_all(view='', ratio_group=None, **kwargs): # Not being used
        """
            Notes:
                Dangerous, removes everything in the parent directory where the file\directory is located.
                Feature used in ruTorrent's "Ratio Groups" plugin called "Remove data (All)".
            Example:
                /home/user/torrents/finished/Some.Torrent.Name.Here/    -> Would delete everything in /home/user/torrents/finished/*
                /home/user/torrents/finished/Some.Torrent.Name.Here.mp4 -> Would delete everything in /home/user/torrents/finished/*
                
        """
        # return RPCMethodHelpers.convert_d_multicall(methods=RPCMethods.remove_and_delete_parent_contents(None, **kwargs), view=view, **kwargs)
        
    @RPCMethodHelpers.formatter
    def get_settings(*args, **kwargs):
        return {
           'dht_statistics':        ('dht_statistics', ''),
           'check_hash':            ('get_check_hash', ''),
           'bind':                  ('get_bind', ''),
           'dht_port':              ('get_dht_port', ''),
           'directory':             ('get_directory', ''),
           'download_rate':         ('get_download_rate', ''),
           'http_cacert':           ('get_http_cacert', ''),
           'http_capath':           ('get_http_capath', ''),
           'http_proxy':            ('get_http_proxy', ''),
           'ip':                    ('get_ip', ''),
           'max_downloads_div':     ('get_max_downloads_div', ''),
           'max_downloads_global':  ('get_max_downloads_global', ''),
           'max_file_size':         ('get_max_file_size', ''),
           'max_memory_usage':      ('get_max_memory_usage', ''),
           'max_open_files':        ('get_max_open_files', ''),
           'max_open_http':         ('get_max_open_http', ''),
           'max_peers':             ('get_max_peers', ''),
           'max_peers_seed':        ('get_max_peers_seed', ''),
           'max_uploads':           ('get_max_uploads', ''),
           'max_uploads_global':    ('get_max_uploads_global', ''),
           'min_peers_seed':        ('get_min_peers_seed', ''),
           'min_peers':             ('get_min_peers', ''),
           'peer_exchange':         ('get_peer_exchange', ''),
           'port_open':             ('get_port_open', ''),
           'upload_rate':           ('get_upload_rate', ''),
           'port_random':           ('get_port_random', ''),
           'port_range':            ('get_port_range', ''),
           'preload_min_size':      ('get_preload_min_size', ''),
           'preload_required_rate': ('get_preload_required_rate', ''),
           'preload_type':          ('get_preload_type', ''),
           'proxy_address':         ('get_proxy_address', ''),
           'receive_buffer_size':   ('get_receive_buffer_size', ''),
           'safe_sync':             ('get_safe_sync', ''),
           'scgi_dont_route':       ('get_scgi_dont_route', ''),
           'send_buffer_size':      ('get_send_buffer_size', ''),
           'session':               ('get_session', ''),
           'session_lock':          ('get_session_lock', ''),
           'session_on_completion': ('get_session_on_completion', ''),
           'split_file_size':       ('get_split_file_size', ''),
           'split_suffix':          ('get_split_suffix', ''),
           'timeout_safe_sync':     ('get_timeout_safe_sync', ''),
           'timeout_sync':          ('get_timeout_sync', ''),
           'tracker_numwant':       ('get_tracker_numwant', ''),
           'use_udp_trackers':      ('get_use_udp_trackers', ''),
           'max_uploads_div':       ('get_max_uploads_div', ''),
           'max_open_sockets':      ('get_max_open_sockets', '')
        }

    @RPCMethodHelpers.formatter
    def set_settings(settings, *args, **kwargs):
        return RPCMethodHelpers.parse_set_settings(settings)


class Torrent():
    
    def add_torrent(self, torrent_item, download_path=None, label=None, ratio_group=None, add_stopped=False, add_name_to_path=True, save_uploaded_torrent=False):
        """
           :torrent_item: accepts multiple formats
                Ex: <bytes>     | [<bytes>]     | [<bytes>, <bytes>, <bytes>...]
                Ex: <magnet>    | [<magnet>]    | [<magnet>, <magnet>, <magnet>...]
                Ex: <path>      | [<path>]      | [<path>, <path>, <path>]
                Ex: [<magnet>, [<path>], [<bytes>], <magnet>]
                <magnet>    the magnet url
                <path>      local filepath to .torrent file
                <bytes>     byte contents of a .torrent file
            Not recommended to send more than 80 torrents at a time.
            Failiure happens when sending around 100 torrents at once.
        """
        methods = []
        if isinstance(torrent_item, list):
            torrent_list = torrent_item
        else:
            torrent_list = [torrent_item]
            
        for torrent in torrent_list:

            is_magnet = False
            is_filepath = False
            is_bytes = False
            
            t_magnet = None
            t_data = None
            t_hash = None
            t_obj = None
            t_comment = None
            t_name = None
            t_path = download_path
            t_label = quote(label or '')
            t_ratio_group = RPCMethods.parse_ratio_group(ratio_group)

            if isinstance(torrent, str) and (torrent.startswith('magnet') or 'xt=urn:btih:' in torrent):
                t_hash = torrent.split('btih:', 1)
                t_hash = len(t_hash) == 2 and t_hash[1].split('&', 1)[0]
                if isinstance(t_hash, str) and len(t_hash) in [32, 40]:
                    is_magnet = True
                    t_magnet = torrent
                else:
                    raise ValueError('Magnet parse error,', f'failed to parse magnet: {torrent}')
            elif isinstance(torrent, str):
                is_filepath = True
                t_obj = self.bencode.from_filepath(torrent)
            elif isinstance(torrent, bytes):
                is_bytes = True
                t_obj = self.bencode.from_bytes(torrent)
            
            if t_obj:
                t_hash = self.bencode.info_to_hash(t_obj['info'])
                t_data = self.bencode.to_bytes(t_obj)
                t_comment = quote(t_obj.get('comment') or '')
                t_name = t_obj.get('info', {}).get('name')
            
            if isinstance(t_hash, str) and len(t_hash) == 32:
                    t_hash = base64.b32decode(t_hash.encode()).hex()
                    
            if t_path is None:
                t_path = self.get_download_directory() or '~/torrents/downloads'
                
            if is_magnet:
                methods += RPCMethods.torrent_add_magnet(t_hash, t_magnet, t_label, t_path, t_ratio_group, add_stopped, add_name_to_path, save_uploaded_torrent)
            elif is_filepath or is_bytes:
                methods += RPCMethods.torrent_add_file(t_hash, t_data, t_name, t_comment, t_label, t_path, t_ratio_group, add_stopped, add_name_to_path, save_uploaded_torrent)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=len(torrent_list))

    def start(self, hashes):
        methods = []
        if isinstance(hashes, str):
            hashes = [hashes]
        for _hash in hashes:
            methods += RPCMethods.start(_hash)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=len(hashes))
        
    def pause(self, hashes):
        methods = []
        if isinstance(hashes, str):
            hashes = [hashes]
        for _hash in hashes:
            methods += RPCMethods.pause(_hash)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=len(hashes))
        
    def unpause(self, hashes):
        methods = []
        if isinstance(hashes, str):
            hashes = [hashes]
        for _hash in hashes:
            methods += RPCMethods.unpause(_hash)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=len(hashes))

    def stop(self, hashes):
        methods = []
        if isinstance(hashes, str):
            hashes = [hashes]
        for _hash in hashes:
            methods += RPCMethods.stop(_hash)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=len(hashes))

    def check_hash(self, hashes):
        methods = []
        if isinstance(hashes, str):
            hashes = [hashes]
        for _hash in hashes:
            methods += RPCMethods.check_hash(_hash)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=len(hashes))
        
    def remove(self, hashes):
        methods = []
        if isinstance(hashes, str):
            hashes = [hashes]
        for _hash in hashes:
            methods += RPCMethods.remove(_hash)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=len(hashes))
        
    def remove_and_delete(self, hashes):
        methods = []
        if isinstance(hashes, str):
            hashes = [hashes]
        for _hash in hashes:
            methods += RPCMethods.remove_and_delete(_hash)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=len(hashes))
        
    def start_all(self, view='default', ratio_group=None):
        """
            Valid view:
                'main', 'default', 'name', 'active', 'started', 'stopped',
                'complete', 'incomplete', 'hashing', 'seeding', 'leeching',
                'rat_0', 'rat_1', 'rat_2', 'rat_3', 'rat_4', 'rat_5', 'rat_6', 'rat_7'
        """
        methods = []
        methods += RPCMethods.start_all(view=view, ratio_group=ratio_group)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=1)
        
    def pause_all(self, view='default', ratio_group=None):
        methods = []
        methods += RPCMethods.pause_all(view=view, ratio_group=ratio_group)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=1)
        
    def unpause_all(self, view='default', ratio_group=None):
        methods = []
        methods += RPCMethods.unpause_all(view=view, ratio_group=ratio_group)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=1)

    def stop_all(self, view='default', ratio_group=None):
        methods = []
        methods += RPCMethods.stop_all(view=view, ratio_group=ratio_group)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=1)

    def check_hash_all(self, view='default', ratio_group=None):
        methods = []
        methods += RPCMethods.check_hash_all(view=view, ratio_group=ratio_group)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=1)
        
    def remove_all(self, view='default', ratio_group=None):
        methods = []
        methods += RPCMethods.remove_all(view=view, ratio_group=ratio_group)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=1)
        
    def remove_and_delete_all(self, view='default', ratio_group=None):
        methods = []
        methods += RPCMethods.remove_and_delete_all(view=view, ratio_group=ratio_group)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=1)

    # def remove_and_delete_parent_contents_all(view='default', ratio_group=None):
        # methods = []
        # methods += RPCMethods.remove_and_delete_parent_contents_all(view=view, ratio_group=ratio_group)
        # response = self.client.system.multicall(methods)
        # return RPCMethods.parse_method_response(methods, response, count=1)
                
    def get_torrent(self, _hash, only_keys=None, exclude_keys=None, include_trackers=False, include_files=False, include_peers=False):
        return self.get_torrents(
            hashes=_hash,
            only_keys=only_keys,
            exclude_keys=exclude_keys,
            include_trackers=include_trackers,
            include_files=include_files,
            include_peers=include_peers
        )[0]
        
    def get_torrents(self, hashes=None, ratio_group=None, include_trackers=False, include_files=False, include_peers=False, **kwargs):
        """
            Note:
                With include_trackers, include_files & include_peers enabled,
                response sent from RPC will be double or more in size, depending on
                number of files, peers and trackers.
            Test:
                Test with 1,125 torrents, 1-3 trackers & 0-4 peers per torrent:
                - 1.48MB w/ include_trackers, include_files & include_peers disabled
                - 3.25MB w/ include_trackers, include_files & include_peers enabled
                
        """
        exclude_keys = kwargs.get('exclude_keys')
        if exclude_keys is None:
            exclude_keys = list()
        elif isinstance(exclude_keys, str):
            exclude_keys = [exclude_keys]
        not include_trackers    and exclude_keys.append(KeyMaps._tracker_map_['_meta_']['group_name'])
        not include_files       and exclude_keys.append(KeyMaps._file_map_['_meta_']['group_name'])
        not include_peers       and exclude_keys.append(KeyMaps._peer_map_['_meta_']['group_name'])
        kwargs['exclude_keys'] = exclude_keys
        if isinstance(hashes, (list, str)):
            methods = []
            if isinstance(hashes, str):
                hashes = list([hashes])
            for _hash in hashes:
                methods += RPCMethods.get_torrent(_hash=_hash, **kwargs)
        else:
            methods = RPCMethods.get_all_torrents(ratio_group=ratio_group, **kwargs)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response, count=hashes and len(hashes) or len(methods))
        
    def remove_ratio_group(self, hashes):
        return self.set_ratio_group(hashes, None)

    def set_ratio_group(self, hashes, ratio_group):
        current = self.get_torrents(hashes=hashes, only_keys=['hash', 'ratio_group'])
        methods = []
        ratio_group = RPCMethods.parse_ratio_group(ratio_group)
        for torrent in current:
            current_hash = torrent.get('hash')
            current_ratio_group = RPCMethods.parse_ratio_group(torrent.get('ratio_group'))
            if not current_hash:
                continue
            if ratio_group and not current_ratio_group:
                methods += RPCMethods.ratio_group_set(current_hash, ratio_group)
            elif ratio_group and current_ratio_group:
                methods += RPCMethods.ratio_group_replace(current_hash, current_ratio_group, ratio_group)
            elif ratio_group is None and current_ratio_group:
                methods += RPCMethods.ratio_group_remove(current_hash, current_ratio_group)
        resp = self.client.system.multicall(methods)
        return resp


class rTorrent(rTorrentRPC, Torrent):

    def __init__(self, uri=None, scheme='https', host=None, port=None, username=None, password=None, rpc_path='/rutorrent'):
        self.config = dict(
            uri=uri,
            scheme=scheme,
            host=host,
            port=port,
            username=username,
            password=password,
            rpc_path=rpc_path
        )
        self.bencode = BencodeUtils()
        super().__init__(**self.config)

    def exec_shell(self, cmd):
        resp = self.client.execute.capture('', ['sh', '-v', '-c', f'{cmd}']).strip()
        return ('\r\n' in resp) and resp.split('\r\n') or resp.split('\n')

    def add_script_on_event(self, event, name, script_path=None):
        action = f'execute={{sh,{script_path},torrent,$d.name=}}' # TODO: Add all torrent arguments
        
    def get_server_time(self):
        return self.client.system.time()
        
    def get_views(self):
        return self.client.view_list()
    
    def remove_event(self, event, name):
        methods = RPCMethods.events_remove(event, name)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response)

    def set_event(self, event, name, method):
        methods = RPCMethods.events_set(event, name, method)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response)
        
    def get_events(self, only_keys=None):
        methods = RPCMethods.events_get(only_keys=only_keys)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response)[0]
        
    def get_settings(self, only_keys=None):
        methods = RPCMethods.get_settings(only_keys=only_keys)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response)[0]
        
    def set_settings(self, settings, only_keys=None):
        """
            :settings: setting_key, setting_val dict
                Example:
                    {'min_peers': 1, 'max_peers': 200}
        """
        methods = RPCMethods.set_settings(settings, only_keys=only_keys)
        response = self.client.system.multicall(methods)
        return RPCMethods.parse_method_response(methods, response)[0]
        
    def get_max_xmlrpc_size_limit_in_MB(self):
        return round(self.client.network.xmlrpc.size_limit() / 2**10 / 2**10)
        
    def set_max_xmlrpc_size_limit_in_MB(self, MB=64):
        """
            Max size is 64MB (67108864 bytes - 1)
        """
        ONE_MB = (2 ** 20)
        MAX_SIZE = ONE_MB * 64 - 1
        size_limit_bytes = ONE_MB * MB
        if MB == 64 and size_limit_bytes > MAX_SIZE:
            size_limit_bytes = MAX_SIZE
        elif size_limit_bytes > MAX_SIZE:
            raise Exception(f'Invalid response size "{MB} MB", max size allowed is "64 MB"')
        return self.client.network.xmlrpc.size_limit.set('', size_limit_bytes)
        
    def get_download_directory(self):
        return self.client.directory.default()

