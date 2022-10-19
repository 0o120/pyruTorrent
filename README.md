# esutils

This was used for personal use, consider it experimental and use at own risk.


## Install

    pip install pyruTorrent


## Usage

*Incomplete docs*

### Create Instance
```python
from pyruTorrent import rTorrent

rt = rTorrent(
	host='xxxxxxxxxx',
	port=123456,
	username='xxxxxxxxxx',
	password='xxxxxxxxxx',
	rpc_path='/rutorrent/plugins/httprpc/action.php'
)

# or

rt = rTorrent(
	uri='https://<username>:<password>@<host>:<port>/rutorrent/plugins/httprpc/action.php',
)
```

### Add Torrent
```python

# :torrent_item: accepts multiple formats
# 	Ex: <bytes>     | [<bytes>]     | [<bytes>, <bytes>, <bytes>...]
# 	Ex: <magnet>    | [<magnet>]    | [<magnet>, <magnet>, <magnet>...]
# 	Ex: <path>      | [<path>]      | [<path>, <path>, <path>]
# 	Ex: [<magnet>, [<path>], [<bytes>], <magnet>]
# 		<magnet>    the magnet url
# 		<path>      local filepath to .torrent file
# 		<bytes>     byte contents of a .torrent file
#	Not recommended to send more than 80 torrents at a time.
#	Failiure happens when sending around 100 torrents at once.
#
# :kwargs: Client defaults used if not set

rt.add_torrent(
	torrent_item,
	download_path=None,
	label=None,
	ratio_group=None,
	add_stopped=False,
	add_name_to_path=True,
	save_uploaded_torrent=False
)
```

### Get Torrent
```python
# Returns single torrent

rt.get_torrent(
	'<torrent-hash>',
	include_trackers=False,
	include_files=False,
	include_peers=False
)
```

### Get Torrents
```python
# Note:
# 	With include_trackers, include_files & include_peers enabled,
# 	response sent from RPC will be double or more in size, depending on
# 	number of files, peers and trackers.
# Test:
# 	Test with 1,125 torrents, 1-3 trackers & 0-4 peers per torrent:
# 	- 1.48MB w/ include_trackers, include_files & include_peers disabled
# 	- 3.25MB w/ include_trackers, include_files & include_peers enabled


# Returns all torrents if no hashes or ratio_group specified

rt.get_torrents(
	hashes=None,
	ratio_group=None,
	include_trackers=False,
	include_files=False,
	include_peers=False
)

# Returns torrents matching hashes

rt.get_torrents(['<torrent-hash>', '<torrent-hash>', '<torrent-hash>'])
```

### Start
```python
rt.start('<torrent-hash>')
```

### Stop
```python
rt.stop('<torrent-hash>')
```

### Pause
```python
rt.pause('<torrent-hash>')
```

### Start All
```python
rt.start_all(view='default', ratio_group=None)
```

### Stop All
```python
rt.stop_all(view='default', ratio_group=None)
```

### Pause All
```python
rt.pause_all(view='default', ratio_group=None)
```

### Remove
```python
rt.remove('<torrent-hash>')
```

### Remove and Delete Files
```python
rt.remove_and_delete('<torrent-hash>')
```

### Remove All
```python
rt.remove_all(view='default', ratio_group=None)
```

### Remove All and Delete Files
```python
rt.remove_and_delete_all(view='default', ratio_group=None)
```

### Check Hash
```python
rt.check_hash('<torrent-hash>')
```

### Check Hash All
```python
rt.check_hash_all(view='default', ratio_group=None)
```

### Remote Ratio Group
```python
rt.remove_ratio_group(['<torrent-hash>', '<torrent-hash>', '<torrent-hash>'])
```

### Set Ratio Group
```python
rt.set_ratio_group(['<torrent-hash>', '<torrent-hash>', '<torrent-hash>'], 2)
```

### Get Settings
```python
rt.get_settings()
```

### Set Settings
```python
rt.set_settings({'min_peers': 1, 'max_peers': 200})
```

### Get Download Directory
```python
# Returns default download directory

rt.get_download_directory()
```

### Get Torrent Views
```python
# Returns default download directory

rt.get_views()
```
