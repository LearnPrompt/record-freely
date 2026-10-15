"""HTTP privacy boundary, byte seek, manifest binding and browser timeline math."""
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import threading

import pytest

from build_review_timeline import build, digest
from serve_review import ASSETS, byte_range, make_server, prepare


def bundle(tmp_path):
    video = tmp_path / 'final.mp4'
    video.write_bytes(b'0123456789abcdefghijklmnopqrstuvwxyz')
    manifest = {'fps': '30', 'output_frames': 120, 'source_frames': 126,
                'source_cuts': [[60, 66]], 'encoded_sha256': digest(video),
                'events': [
                    {'role': 'local_redaction', 'start_frame': 10, 'end_frame': 20, 'category': 'url'},
                    {'role': 'local_redaction', 'start_frame': 19, 'end_frame': 25, 'category': 'path'},
                    {'role': 'local_redaction', 'start_frame': 26, 'end_frame': 27, 'category': 'url'},
                    {'role': 'local_redaction', 'start_frame': 59, 'end_frame': 62, 'category': 'url'},
                    {'role': 'global_protection', 'start_frame': 0, 'end_frame': 120}],
                'checkpoints': [18, 59]}
    source = tmp_path / 'manifest.json'
    source.write_text(json.dumps(manifest))
    timeline = tmp_path / 'timeline.json'
    timeline.write_text(json.dumps(build(manifest)))
    return video, timeline, source


@pytest.fixture
def http_server(tmp_path):
    paths = bundle(tmp_path)
    video, data = prepare(*paths)
    server = make_server(video, data, port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield server, paths
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)


def request(server, path='/', method='GET', headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
    connection.request(method, path, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_binding_and_no_private_manifest_leak(tmp_path):
    video, timeline, source = bundle(tmp_path)
    manifest = json.loads(source.read_text())
    for event in manifest['events']:
        event.update(raw_text='private-sentinel', id='/private/sentinel', geometry=[1, 2, 3, 4])
    manifest['events'][0]['category'] = '/Users/private-sentinel'
    source.write_text(json.dumps(manifest))
    _, data = prepare(video, timeline, source)
    text = json.dumps(data)
    assert 'private-sentinel' not in text
    assert data['events'][0]['category'] == 'local'
    assert data['source_cuts'] == [[60, 66]]
    assert data['video_sha_verified'] is True
    assert all(e['category'] != 'global_protection' for e in data['events'])


def test_wrong_hash_and_changed_manifest_fail_closed(tmp_path):
    video, timeline, source = bundle(tmp_path)
    video.write_bytes(b'wrong version')
    with pytest.raises(ValueError, match='SHA256 differs'):
        prepare(video, timeline, source)
    video, timeline, source = bundle(tmp_path)
    manifest = json.loads(source.read_text())
    manifest['events'][0]['end_frame'] = 18
    source.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='intervals do not match'):
        prepare(video, timeline, source)


def test_only_timeline_explicit_partial_mapping(tmp_path):
    video, timeline, _ = bundle(tmp_path)
    _, data = prepare(video, timeline)
    assert data['source_cuts'] is None
    assert data['events'] == []
    assert data['intervals'][0]['source_start_frame'] == 10


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(schema_version=2),
    lambda d: d.update(output_frames=True),
    lambda d: d.update(fps='0'),
    lambda d: d['intervals'][0].update(source_end_frame=99),
    lambda d: d['intervals'][0].update(start_frame=True),
    lambda d: d['intervals'][1].update(start_frame=9),
])
def test_invalid_timeline_rejected(tmp_path, mutate):
    video, timeline, _ = bundle(tmp_path)
    data = json.loads(timeline.read_text())
    mutate(data)
    timeline.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        prepare(video, timeline)


@pytest.mark.parametrize('header,expected', [
    (None, (0, 35, 200)), ('bytes=0-0', (0, 0, 206)),
    ('bytes=10-', (10, 35, 206)), ('bytes=-5', (31, 35, 206)),
    ('bytes=-100', (0, 35, 206)), ('bytes=30-100', (30, 35, 206)),
])
def test_range_parser(header, expected):
    assert byte_range(header, 36) == expected


@pytest.mark.parametrize('header', ['bytes=', 'bytes=-0', 'bytes=36-', 'bytes=8-7',
                                   'bytes=0-1,3-4', 'items=0-2', 'bytes=x-2', 'bytes=--'])
def test_invalid_range_parser(header):
    with pytest.raises(ValueError):
        byte_range(header, 36)


@pytest.mark.parametrize('range_header,payload,content_range', [
    ('bytes=0-3', b'0123', 'bytes 0-3/36'),
    ('bytes=15-', b'fghijklmnopqrstuvwxyz', 'bytes 15-35/36'),
    ('bytes=-3', b'xyz', 'bytes 33-35/36'),
    ('bytes=34-1000', b'yz', 'bytes 34-35/36'),
])
def test_real_206_byte_seek(http_server, range_header, payload, content_range):
    server, _ = http_server
    status, headers, body = request(server, '/video', headers={'Range': range_header})
    assert status == 206
    assert body == payload
    assert headers['Content-Range'] == content_range
    assert int(headers['Content-Length']) == len(payload)
    assert headers['Accept-Ranges'] == 'bytes'
    assert headers['Content-Type'] == 'video/mp4'


@pytest.mark.parametrize('range_header', ['bytes=100-', 'bytes=-0', 'bytes=4-2', 'bytes=0-1,5-6', 'bad'])
def test_actual_416_has_required_length(http_server, range_header):
    server, _ = http_server
    status, headers, body = request(server, '/video', headers={'Range': range_header})
    assert status == 416
    assert headers['Content-Range'] == 'bytes */36'
    assert headers['Content-Length'] == '0'
    assert body == b''


def test_head_and_static_resources(http_server):
    server, _ = http_server
    for route in ['/', '/viewer.js', '/viewer.css', '/timeline.json', '/health', '/video']:
        status, headers, body = request(server, route, method='HEAD')
        assert status == 200
        assert int(headers['Content-Length']) > 0
        assert body == b''
    status, headers, body = request(server, '/video', method='HEAD', headers={'Range': 'bytes=2-5'})
    assert status == 206 and headers['Content-Length'] == '4' and body == b''
    status, headers, body = request(server, '/')
    assert status == 200 and b'viewer.js' in body
    assert "default-src 'self'" in headers['Content-Security-Policy']
    assert 'Access-Control-Allow-Origin' not in headers


@pytest.mark.parametrize('path', ['/manifest.json', '/../manifest.json', '/%2e%2e/manifest.json',
                                 '/%2e%2e%2fmanifest.json', '/video/../manifest.json',
                                 '/etc/passwd', '/viewer.js/../manifest.json', '/video%00'])
def test_whitelist_hides_adjacent_files_and_traversal(http_server, path):
    server, paths = http_server
    (paths[0].parent / 'secret.txt').write_text('secret sentinel')
    status, _, body = request(server, path)
    assert status == 404
    assert b'secret sentinel' not in body


def test_dns_rebinding_host_rejected(http_server):
    server, _ = http_server
    status, _, _ = request(server, '/video', headers={'Host': 'attacker.example'})
    assert status == 403
    assert server.server_address[0] == '127.0.0.1'


def test_video_mutation_or_replacement_invalidates_binding(http_server):
    server, paths = http_server
    video = paths[0]
    video.write_bytes(b'changed same-size content is not bound')
    status, _, body = request(server, '/video')
    assert status == 409 and b'restart' in body


def run_js(data, expression):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable; browser independently verifies viewer math')
    code = f'const T=require({json.dumps(str(ASSETS / "viewer.js"))});const D={json.dumps(data)};console.log(JSON.stringify({expression}));'
    result = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=5, check=True)
    return json.loads(result.stdout)


def test_category_filter_rebuilds_without_gaps_and_cut_bridges(tmp_path):
    video, timeline, source = bundle(tmp_path)
    _, data = prepare(video, timeline, source)
    url = run_js(data, 'T.categoryIntervals(D,"url")')
    assert [(r['start_frame'], r['end_frame']) for r in url] == [(10, 20), (26, 27), (59, 60), (60, 62)]
    assert url[-1]['source_start_frame'] == 66
    path = run_js(data, 'T.categoryIntervals(D,"path")')
    assert [(r['start_frame'], r['end_frame']) for r in path] == [(19, 25)]
    data['events'].append({'start_frame': 59, 'end_frame': 63, 'category': 'url'})
    overlap = run_js(data, 'T.categoryIntervals(D,"url")')
    assert [(r['start_frame'], r['end_frame']) for r in overlap] == [(10, 20), (26, 27), (59, 60), (60, 63)]


def test_source_mapping_cut_prefix_suffix_and_unknown_gaps(tmp_path):
    video, timeline, source = bundle(tmp_path)
    _, data = prepare(video, timeline, source)
    assert run_js(data, '[59,60,61,119].map(f=>T.outputToSource(D,f))') == [59, 66, 67, 125]
    assert run_js(data, '[59,60,65,66].map(f=>T.sourceToOutput(D,f))') == [
        {'frame': 59, 'deleted': False}, {'frame': 60, 'deleted': True},
        {'frame': 60, 'deleted': True}, {'frame': 60, 'deleted': False}]
    data['source_cuts'] = [[0, 2], [7, 10], [17, 20], [28, 31]]
    data['output_frames'] = 20
    assert run_js(data, '[0,4,5,11,12,19].map(f=>T.outputToSource(D,f))') == [2, 6, 10, 16, 20, 27]
    assert run_js(data, 'T.sourceToOutput(D,30)') == {'frame': 19, 'deleted': True}
    _, data = prepare(video, timeline)
    assert run_js(data, '[9,10,19,25,60].map(f=>T.outputToSource(D,f))') == [None, 10, 19, None, 66]
    assert run_js(data, 'T.sourceToOutput(D,30)') is None


def test_internal_checkpoints_rational_rate(tmp_path):
    video, timeline, source = bundle(tmp_path)
    _, data = prepare(video, timeline, source)
    data['fps'] = '30000/1001'
    data['checkpoints'] = [601, 2000]
    points = run_js(data, 'T.checkpoints(D,{start_frame:0,end_frame:1800})')
    assert points[0] == 0 and points[-1] == 1799
    assert 601 in points and 2000 not in points
    assert max(b - a for a, b in zip(points, points[1:])) <= 300


def test_manual_jump_selects_matching_interval_without_crossing_gap(tmp_path):
    video, timeline, manifest = bundle(tmp_path)
    data = prepare(video, timeline, manifest)[1]
    data['intervals'] = [dict(start_frame=0, end_frame=10),
                         dict(start_frame=15, end_frame=20)]
    rows = 'T.categoryIntervals(D)'
    assert run_js(data, f'T.intervalAtFrame({rows},0).key') == 'all:0:10'
    assert run_js(data, f'T.intervalAtFrame({rows},15).key') == 'all:15:20'
    assert run_js(data, f'T.intervalAtFrame({rows},19).key') == 'all:15:20'
    for frame in (10, 14, 20):
        assert run_js(data, f'T.intervalAtFrame({rows},{frame})') is None


def test_real_viewer_navigation_preserves_notes_and_loops_at_eof():
    """Execute the actual UI handlers, including seeks outside a selected row."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for browser handler regression')
    data = {'fps': '30', 'output_frames': 40, 'source_cuts': [],
            'encoded_sha256': 'a' * 64, 'events': [], 'checkpoints': [],
            'intervals': [dict(start_frame=a, end_frame=b, source_start_frame=a, source_end_frame=b)
                          for a, b in [(0, 10), (15, 25), (35, 40)]]}
    harness = r'''
const D=JSON.parse(process.argv[1]), elements={}, storage={}, listeners={};
function element() {return {value:'',textContent:'',dataset:{},children:[],checked:false,
 classList:{toggle(){}},append(...items){this.children.push(...items)},
 replaceChildren(){this.children=[]},addEventListener(name,fn){listeners[name]=fn}};}
const $=id => elements[id] || (elements[id]=element());
const video=$('#video'); Object.assign(video,{currentTime:0,paused:true,readyState:4,
 duration:D.output_frames/30,pause(){this.paused=true},
 play(){this.paused=false;this.ended=false;return Promise.resolve()}});
const frameButtons=[element(),element()]; frameButtons[0].dataset.frame='-1';frameButtons[1].dataset.frame='1';
global.document={querySelector:$,createElement:element,querySelectorAll(){return frameButtons},activeElement:{tagName:'BUTTON'}};
global.window={addEventListener(){}};
global.localStorage={getItem(){return null},setItem(k,v){storage[k]=v}};
global.fetch=async()=>({ok:true,json:async()=>D});
require(process.argv[2]);
setImmediate(()=>{
 const out=[]; const record=()=>out.push({frame:Math.round(video.currentTime*30),selection:$('#selection').textContent,note:$('#note').value});
 $('#note').value='first interval note'; $('#middle').onclick();record();
 $('#note').value='middle note'; $('#last').onclick();record();
 $('#first').onclick();record();
 $('#scrubber').value='24';$('#scrubber').oninput();record();
 frameButtons[1].onclick();record();
 $('#scrubber').value='35';$('#scrubber').oninput();record();
 video.currentTime=12/30;listeners.seeked();record();
 $('#last').onclick();video.currentTime=video.duration;video.paused=true;video.ended=true;
 listeners.ended();const disabledLoop={frame:Math.round(video.currentTime*30),paused:video.paused};
 $('#loop').checked=true;listeners.ended();const wrapped={frame:Math.round(video.currentTime*30),paused:video.paused};
 console.log(JSON.stringify({out,disabledLoop,wrapped,notes:JSON.parse(Object.values(storage)[0])}));
});
'''
    result = json.loads(subprocess.check_output(
        [node, '-e', harness, json.dumps(data), str(ASSETS / 'viewer.js')], text=True, timeout=5))
    rows = result['out']
    assert [row['frame'] for row in rows] == [20, 39, 0, 24, 25, 35, 12]
    assert rows[0]['selection'].startswith('00:00.500–00:00.833')
    assert rows[1]['selection'].startswith('00:01.167–00:01.333')
    assert rows[2]['note'] == 'first interval note'
    assert rows[3]['note'] == 'middle note'
    for index in (4, 6):
        assert rows[index]['selection'] == '当前筛选未包含此时间'
        assert rows[index]['note'] == ''
    assert result['notes']['all:0:10']['text'] == 'first interval note'
    assert result['notes']['all:15:25']['text'] == 'middle note'
    assert result['disabledLoop'] == {'frame': 40, 'paused': True}
    assert result['wrapped'] == {'frame': 35, 'paused': False}


def test_microsecond_media_clock_does_not_reseek_loop_start():
    data = {'fps': '30'}
    assert run_js(data, 'T.loopTarget(D,1.866666,{start_frame:56,end_frame:439})') is None
    assert run_js(data, 'T.loopTarget(D,2.0,{start_frame:56,end_frame:439})') is None
    assert run_js(data, 'T.loopTarget(D,14.633333,{start_frame:56,end_frame:439})') == 56
    assert run_js(data, 'T.loopTarget(D,1.8,{start_frame:56,end_frame:439})') == 56
    data['fps'] = '30000/1001'
    assert run_js(data, 'T.loopTarget(D,1.868533,{start_frame:56,end_frame:439})') is None
