"""Native glyph geometry acceptance on public synthetic teaching text."""
import sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont
from redact_video import VisionOCR, detection_boxes, cover


@pytest.mark.skipif(sys.platform != 'darwin', reason='Native macOS Vision geometry')
def test_native_retention_preserves_suffix_or_explicitly_requires_review(tmp_path):
    font_path=Path('/System/Library/Fonts/Supplemental/Courier New.ttf')
    if not font_path.exists():
        pytest.skip('Synthetic monospaced fixture font unavailable')
    font=ImageFont.truetype(str(font_path),28)
    image=Image.new('RGB',(1100,240),'white');draw=ImageDraw.Draw(image)
    url='https://github.com/example-org/example-skill'
    path='/Users/example-user/project/demo.py'
    draw.text((30,25),url,font=font,fill='black')
    draw.text((30,95),path,font=font,fill='black')
    draw.text((30,165),'README.md  sp.read_text()',font=font,fill='black')
    frame=np.asarray(image)[:,:,::-1].copy()
    worker=VisionOCR(tmp_path);worker.privacy=True
    try:
        observations=worker.read(frame)
    finally:
        worker.close()
    ledger=[]
    boxes=detection_boxes(observations,1100,240,4,privacy=True,
                          path_policy='parent',github_policy='host',review=ledger)
    assert any(r['kind']=='http(s)' and r['status'] in ('mask','needs_review') for r in ledger)
    assert any(r['kind']=='identity_path' and r['status'] in ('mask','needs_review') for r in ledger)
    result=cover(frame,boxes,'solid')
    for prefix,suffix,y in [('https://github.com','/example-org/example-skill',25),
                             ('/Users/example-user/project/','demo.py',95)]:
        start=30+round(draw.textlength(prefix,font=font))
        left,top,right,bottom=draw.textbbox((start,y),suffix,font=font)
        # Tolerate rasterizer's subpixel kerning at the first boundary only.
        assert np.array_equal(result[top:bottom,left+2:right],frame[top:bottom,left+2:right])
    assert np.array_equal(result[165:220],frame[165:220])
    assert boxes or any(r['status']=='needs_review' for r in ledger)
