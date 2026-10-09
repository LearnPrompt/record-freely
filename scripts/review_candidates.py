"""Local candidate classification. Decisions describe redaction, never platform rules.

Raw text is transient. Public report records only kind, geometry, confidence and
reason codes. Normalization must not change offsets used for character boxes.
"""
from pathlib import Path
import math
import re

DOMAIN = r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?[.．])+[a-z]{2,24}(?![a-z0-9-])"
# Repair spacing only for common TLDs; generic '. Word' is usually sentence
# punctuation, not a link. Never freely join arbitrary prose across spaces.
SPACED_DOMAIN = (r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\s*[.．]\s*)+"
                 r"(?:com|net|org|edu|gov|io|ai|cn|tw|hk|app|dev|pro|co|me|xyz|site|online|tech)(?![a-z0-9-])")
ANY_DOMAIN = r"(?:" + DOMAIN + "|" + SPACED_DOMAIN + ")"
URL_PATTERN = re.compile(
    r"(?<![a-z0-9_@])(?:https?\s*[:：]\s*[/／]{2}\s*[^\s<>\"'，。]+|"
    r"www\s*[.．]\s*" + ANY_DOMAIN + r"(?:[/／?#][^\s<>\"'，。]*)?|"
    + ANY_DOMAIN + r"(?::\d{1,5})?(?:[/／?#][^\s<>\"'，。]*)?)", re.IGNORECASE)
FILE_EXTENSIONS = {"py", "md", "txt", "json", "yaml", "yml", "csv", "ts", "js", "jsx", "tsx",
                   "css", "html", "swift", "png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "pptx",
                   "xlsx", "mp4", "mov", "mkv", "zip", "exe", "dmg", "log", "sh", "opml", "xml",
                   "toml", "ini", "conf", "config", "lock", "sqlite", "svg", "mjs", "cjs", "wasm"}
EMAIL_PATTERN = re.compile(r"[^\s<>\"，。]+@[^\s<>\"，。]+")
TLD_FILE = Path(__file__).with_name("iana-tlds.txt")
KNOWN_TLDS = {line.strip().lower() for line in TLD_FILE.read_text().splitlines() if line and not line.startswith("#")}


def text_candidates(text, privacy=False, channel="screen_text"):
    """Return offsets into ORIGINAL text and non-sensitive decision reason codes."""
    result = []
    emails = list(EMAIL_PATTERN.finditer(text))
    for match in URL_PATTERN.finditer(text):
        value = match.group().rstrip(".,;:!?)]}，。；：！")
        end = match.start() + len(value)
        compact = re.sub(r"\s+", "", value).replace("．", ".").replace("／", "/")
        explicit = bool(re.match(r"https?[:：]|www\.", compact, re.I))
        if not re.match(r"https?[:：]", compact, re.I) and any(
                m.start() < end and m.end() > match.start() for m in emails):
            continue
        kind = "http(s)" if re.match(r"https?[:：]", compact, re.I) else "www" if compact.lower().startswith("www.") else "domain"
        status, reason = "mask", "visible_address"
        if not explicit:
            host = re.split(r"[/:?#]", compact)[0]
            suffix = host.rsplit(".", 1)[-1].lower()
            tail = len(compact) > len(host) and compact[len(host)] in "/:?#"
            if suffix in FILE_EXTENSIONS and not tail:
                status, reason = "keep", "ordinary_file_extension"
            elif suffix not in KNOWN_TLDS | {"test", "local", "localhost", "internal", "invalid"}:
                continue
            elif re.match(r"\((?:[a-z0-9_'\"]|\))", text[match.end():], re.I) and not tail:
                status, reason = "keep", "code_call"
            elif re.match(r"^\d+[.．]", value):
                status, reason = "needs_review", "numeric_heading_or_domain"
        if value:
            result.append(dict(start=match.start(), end=end, kind=kind, status=status, reason=reason))
    if privacy:
        valid_email = re.compile(r"(?<![a-z0-9._%+\-])[a-z0-9._%+\-]+@(?:[a-z0-9-]+\.)+[a-z]{2,24}(?![a-z0-9-])", re.I)
        for m in valid_email.finditer(text):
            result.append(dict(start=m.start(), end=m.end(), kind="email", status="mask", reason="privacy_email"))
        for m in re.finditer(r"(?<![0-9])(?:\+?86[ -]?)?1[3-9][0-9]{9}(?![0-9])", text):
            result.append(dict(start=m.start(), end=m.end(), kind="phone", status="mask", reason="privacy_mobile_number"))
        labelled = re.compile(r"(?:电话|手机|手机号|联系电话|tel(?:ephone)?|phone)\s*[:：]?\s*(?P<number>\+?[0-9][0-9 ()-]{5,23}[0-9])", re.I)
        for m in labelled.finditer(text):
            if not 7 <= len(re.sub(r"\D", "", m['number'])) <= 15:
                continue
            a, b = m.span('number')
            if not any(r['kind']=='phone' and r['start'] <= a and r['end'] >= b for r in result):
                result.append(dict(start=a, end=b, kind="phone", status="mask", reason="privacy_labelled_phone"))
        # Hide the identity-bearing prefix, leaving workspace purpose/basename.
        # Geometry fallback is disclosed rather than guessed from text length.
        for m in re.finditer(r"(?:/Users/|/home/)[^/\s<>\"']+/?|[A-Za-z]:[\\/]Users[\\/][^\\/\s<>\"']+[\\/]?", text):
            result.append(dict(start=m.start(), end=m.end(), kind="identity_path", status="mask", reason="privacy_identity_prefix"))
    if channel in {'audio','subtitle'}:
        for m in re.finditer(r"[a-z0-9-]+\s+(?:dot|点|點)\s+(?:com|cn|net|org|io|ai|app|dev)\b",text,re.I):
            result.append(dict(start=m.start(),end=m.end(),kind='spoken_address',status='needs_review',reason='spoken_domain_requires_listening'))
        if privacy:
            values={'零':'0','〇':'0','一':'1','幺':'1','二':'2','两':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9'}
            for m in re.finditer(r"[零〇一幺二两三四五六七八九0-9](?:[零〇一幺二两三四五六七八九0-9 、，-]{8,40})[零〇一幺二两三四五六七八九0-9]",text):
                number=''.join(values.get(c,c) for c in m[0] if c in values or c.isdigit())
                if re.fullmatch(r'1[3-9][0-9]{9}',number) and not any(r['kind']=='phone' and r['start']==m.start() for r in result):
                    result.append(dict(start=m.start(),end=m.end(),kind='phone',status='needs_review',reason='spoken_number_requires_listening'))
            for m in re.finditer(r'邮箱|电子邮件|加微信|加我|联系我|email|e-mail|wechat',text,re.I):
                result.append(dict(start=m.start(),end=m.end(),kind='contact_cue',status='needs_review',reason='spoken_contact_context_required'))
    return sorted(result, key=lambda r: (r['start'], r['end'], r['kind']))


def url_spans(text):
    """Compatibility: eligible visual URL spans, excluding unresolved candidates."""
    return [(r['start'], r['end']) for r in text_candidates(text)
            if r['status'] == 'mask']


def _geometry(observation, start, end, width, height, padding):
    outer = observation['box']
    chars = [c for c in observation.get('chars', [])
             if c['start'] < end and c['end'] > start and any(
                 not observation.get('text','')[i].isspace()
                 for i in range(max(start,c['start']), min(end,c['end'])))]
    parts = [c['box'] for c in chars]
    complete = all(any(c['start'] <= i < c['end'] for c in chars)
                   for i in range(start,end) if not observation.get('text','')[i].isspace())
    valid = all(len(b)==4 and all(math.isfinite(v) for v in b)
                and b[2]>0 and b[3]>0 and b[0]>=outer[0]-.01 and b[1]>=outer[1]-.01
                and b[0]+b[2]<=outer[0]+outer[2]+.01 and b[1]+b[3]<=outer[1]+outer[3]+.01 for b in parts)
    repeated = len(parts)>1 and all(all(abs(a-b)<=1e-6 for a,b in zip(p,parts[0])) for p in parts[1:])
    if parts and complete and valid:
        x, y = min(b[0] for b in parts), min(b[1] for b in parts)
        right, bottom = max(b[0]+b[2] for b in parts), max(b[1]+b[3] for b in parts)
        box = [x,y,right-x,bottom-y]
        method = 'repeated_character_boxes' if repeated else 'characters'
    else:
        box, method = outer, 'line_fallback'
    x,y,w,h = box
    x1,y1 = max(0,math.floor(x*width-padding)),max(0,math.floor(y*height-padding))
    x2,y2 = min(width,math.ceil(x*width+w*width+padding)),min(height,math.ceil(y*height+h*height+padding))
    return [x1,y1,max(0,x2-x1),max(0,y2-y1)],method


def observation_candidates(observations, width, height, padding=4, privacy=False):
    """Anonymous records. A candidate's mask status is a user-selected action."""
    result = []
    for index, observation in enumerate(observations):
        if observation.get('kind') == 'qr_code':
            if privacy:
                box,method=_geometry(observation,0,0,width,height,padding)
                result.append(dict(kind='qr_code',status='mask',reason='privacy_qr_code',box=box,
                                   confidence=1.0,box_method=method,observation_index=index,span=[0,0]))
            continue
        confidence = float(observation.get('confidence',1))
        for candidate in text_candidates(observation.get('text',''),privacy):
            row = dict(candidate)
            a,b=row.pop('start'),row.pop('end')
            box,method=_geometry(observation,a,b,width,height,padding)
            if not box[2] or not box[3]:
                continue
            if row['kind']=='identity_path' and method!='characters' and observation.get('text','')[a:b].strip()!=observation.get('text','').strip():
                row.update(status='needs_review',reason='identity_prefix_requires_precise_geometry')
            if row['status']=='mask' and confidence < .5 and row['kind'] not in {'http(s)','www'}:
                row.update(status='needs_review',reason='low_ocr_confidence')
            row.update(box=box,confidence=confidence,box_method=method,observation_index=index,span=[a,b])
            result.append(row)
    result.extend(split_address_candidates(observations,width,height,padding))
    return result


def split_address_candidates(observations, width, height, padding=4):
    """Spatially adjacent pieces are review hints, never automatic rectangles."""
    result=[]
    for i,first in enumerate(observations):
        left=first.get('text','').strip()
        if not re.search(r'(?:https?[:：][/／]{0,2}|www[.．]|[a-z0-9-]+[.．])$',left,re.I):
            continue
        a=first['box']
        for second in observations[i+1:i+5]:
            right=second.get('text','').strip()
            if not right or not re.match(r'^[a-z0-9]',right,re.I):
                continue
            b=second['box'];h=max(a[3],b[3])
            horizontal=abs(a[1]-b[1])<=h*.5 and 0<=b[0]-(a[0]+a[2])<=h*2
            vertical=abs(a[0]-b[0])<=h and 0<=b[1]-(a[1]+a[3])<=h
            if not (horizontal or vertical):
                continue
            joined=left+right
            if not any(r['status']=='mask' and r['kind'] in {'http(s)','www','domain'} for r in text_candidates(joined)):
                continue
            x,y=min(a[0],b[0]),min(a[1],b[1])
            box=[x,y,max(a[0]+a[2],b[0]+b[2])-x,max(a[1]+a[3],b[1]+b[3])-y]
            pixel,_=_geometry({'text':'','box':box},0,0,width,height,padding)
            result.append(dict(kind='split_address',status='needs_review',reason='adjacent_fragments_need_visual_review',
                               box=pixel,confidence=min(float(first.get('confidence',1)),float(second.get('confidence',1))),
                               box_method='adjacent_regions',observation_index=i,span=[0,0]))
    return result
