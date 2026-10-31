#!/usr/bin/env python3
"""img-diff headless E2E verification via raw geckodriver HTTP (no selenium).

Run:  python3 tests/verify.py
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = "file://" + os.path.join(os.path.dirname(HERE), "img-diff.html")
SHOT = os.path.join(os.path.dirname(HERE), "tests", "shot.png")
PORT = 4483
GECKO = os.path.expanduser("~/.local/bin/geckodriver")

# bypass any exported proxy (FlClash would swallow 127.0.0.1 WebDriver calls)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(sid, path, method="POST", body=None):
    url = "http://127.0.0.1:%d%s" % (PORT, path if path.startswith("/") else "/session/%s/%s" % (sid, path))
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with OPENER.open(req, timeout=180) as r:
        return json.loads(r.read().decode())


SUITE = r"""
const done = arguments[arguments.length - 1];
const R = { pass: 0, fail: 0, log: [], errors: [] };
function ok(name, cond, extra) {
  if (cond) { R.pass++; R.log.push('PASS ' + name); }
  else { R.fail++; R.log.push('FAIL ' + name + (extra !== undefined ? ' :: ' + JSON.stringify(extra) : '')); }
}
window.addEventListener('error', e => R.errors.push(String(e.message)));
function cv(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
function fileOf(c, name) {
  return new Promise(res => c.toBlob(b => res(new File([b], name, { type: 'image/png' })), 'image/png'));
}
const H = window.__imgdiff;
(async () => {
  ok('boot-hook', !!H, typeof window.__imgdiff);

  // T2 auto align: 100x80, black 30x30 square moved 5px -> exact 550 diff px
  {
    const a = cv(100, 80), b = cv(100, 80);
    const ca = a.getContext('2d'), cb = b.getContext('2d');
    ca.fillStyle = '#fff'; ca.fillRect(0, 0, 100, 80);
    cb.fillStyle = '#fff'; cb.fillRect(0, 0, 100, 80);
    ca.fillStyle = '#000'; ca.fillRect(20, 20, 30, 30);
    cb.fillStyle = '#000'; cb.fillRect(25, 25, 30, 30);
    const g = await H.loadPair(await fileOf(a, 'a.png'), await fileOf(b, 'b.png'));
    ok('auto-grid-100x80', g.w === 100 && g.h === 80, g);
    ok('auto-diff-exact-550', H.diffCount() === 550, H.diffCount());
    H.setThreshold(255);
    ok('thr-255-zero', H.diffCount() === 0, H.diffCount());
    H.setThreshold(20);
  }

  // T4 identical images -> 0
  {
    const a = cv(60, 50);
    const x = a.getContext('2d');
    x.fillStyle = '#ccc'; x.fillRect(0, 0, 60, 50);
    x.fillStyle = '#3344aa'; x.fillRect(10, 10, 20, 15);
    await H.loadPair(await fileOf(a, 's1.png'), await fileOf(a, 's2.png'));
    ok('identical-diff-0', H.diffCount() === 0, H.diffCount());
  }

  // T5 color-based (not gray-based): R/B swap, luma differs only ~8.8 < thr 20
  {
    const a = cv(40, 40), b = cv(40, 40);
    const x = a.getContext('2d'); x.fillStyle = 'rgb(77,150,29)'; x.fillRect(0, 0, 40, 40);
    const y = b.getContext('2d'); y.fillStyle = 'rgb(29,150,77)'; y.fillRect(0, 0, 40, 40);
    await H.loadPair(await fileOf(a, 'g.png'), await fileOf(b, 'h.png'));
    ok('color-not-gray-1600', H.diffCount() === 1600, H.diffCount());
  }

  // T5b directional colors: A brighter square -> A side red, B side blue, overlap purple
  {
    const a = cv(60, 40), b = cv(60, 40);
    const x = a.getContext('2d'), y = b.getContext('2d');
    x.fillStyle = 'rgb(128,128,128)'; x.fillRect(0, 0, 60, 40);
    y.fillStyle = 'rgb(128,128,128)'; y.fillRect(0, 0, 60, 40);
    x.fillStyle = '#fff'; x.fillRect(10, 10, 20, 20);
    y.fillStyle = '#000'; y.fillRect(10, 10, 20, 20);
    await H.loadPair(await fileOf(a, 'd1.png'), await fileOf(b, 'd2.png'));
    ok('dir-count-400', H.diffCount() === 400, H.diffCount());
    ok('dir-A-larger', H.dirAt(20, 20) === 1, H.dirAt(20, 20));
    ok('dir-nodiff-bg', H.dirAt(2, 2) === 0 && H.diffAt(2, 2) === 0, H.dirAt(2, 2));
    const pa = H.layerPixel('A', 20, 20), pb = H.layerPixel('B', 20, 20), po = H.layerPixel('overlap', 20, 20);
    ok('color-A-red', pa[0] === 255 && pa[1] === 23 && pa[2] === 68 && pa[3] === 255, pa);
    ok('color-B-blue', pb[0] === 0 && pb[1] === 176 && pb[2] === 255, pb);
    ok('color-overlap-purple', po[0] === 168 && po[1] === 85 && po[2] === 247, po);
    const pOut = H.layerPixel('A', 2, 2);
    ok('color-nodiff-transparent', pOut[3] === 0, pOut);
  }

  // T5c luma tie (77*150 == 150*77): channel diff > thr but equal brightness -> purple both sides
  {
    const a = cv(50, 50), b = cv(50, 50);
    const x = a.getContext('2d'); x.fillStyle = 'rgb(150,0,0)'; x.fillRect(0, 0, 50, 50);
    const y = b.getContext('2d'); y.fillStyle = 'rgb(0,77,0)'; y.fillRect(0, 0, 50, 50);
    await H.loadPair(await fileOf(a, 't1.png'), await fileOf(b, 't2.png'));
    ok('tie-count-2500', H.diffCount() === 2500, H.diffCount());
    ok('tie-dir-0', H.dirAt(25, 25) === 0, H.dirAt(25, 25));
    const pa = H.layerPixel('A', 25, 25);
    ok('tie-purple-A', pa[0] === 168 && pa[1] === 85 && pa[2] === 247, pa);
    const pb = H.layerPixel('B', 25, 25);
    ok('tie-purple-B', pb[0] === 168 && pb[1] === 85 && pb[2] === 247, pb);
  }

  // T6 anchor similarity math (exact) + degenerate rejection
  {
    H.setAnchors([{x:20,y:30},{x:95,y:80}], [{x:10,y:10},{x:60,y:10}]);
    const m = H.solveAnchors();
    ok('solve-exists', !!m);
    if (m) {
      const p1 = m.transformPoint(new DOMPoint(10.5, 10.5));
      const p2 = m.transformPoint(new DOMPoint(60.5, 10.5));
      ok('solve-a1-exact', Math.abs(p1.x-20.5) < 1e-9 && Math.abs(p1.y-30.5) < 1e-9, p1);
      ok('solve-a2-exact', Math.abs(p2.x-95.5) < 1e-9 && Math.abs(p2.y-80.5) < 1e-9, p2);
    }
    H.setAnchors([{x:10,y:10},{x:10,y:10}], [{x:5,y:5},{x:9,y:5}]);
    ok('solve-degenerate-null', H.solveAnchors() === null);
  }

  // T7 manual identity E2E: same anchors both sides -> exact 0 diff, grid = A dims
  {
    const a = cv(120, 90);
    const x = a.getContext('2d');
    x.fillStyle = '#eeeeee'; x.fillRect(0, 0, 120, 90);
    x.fillStyle = '#aa3333'; x.beginPath(); x.arc(60, 45, 30, 0, 7); x.fill();
    x.fillStyle = '#33aa66'; x.fillRect(15, 15, 25, 20);
    await H.loadPair(await fileOf(a, 'i1.png'), await fileOf(a, 'i2.png'));
    H.setAnchors([{x:10,y:10},{x:100,y:70}], [{x:10,y:10},{x:100,y:70}]);
    H.applyManual();
    ok('manual-identity-0', H.diffCount() === 0, H.diffCount());
    ok('manual-mode-set', H.S.align === 'manual', H.S.align);
    const gi = H.gridInfo();
    ok('manual-grid-is-A', gi.w === 120 && gi.h === 90, gi);
  }

  // T8 manual similarity E2E: B = A under rotate15+scale1.25+translate; anchors restore
  {
    const A = cv(300, 300);
    const x = A.getContext('2d');
    x.fillStyle = '#c9b98a'; x.fillRect(0, 0, 300, 300);       // solid bg (transform-invariant)
    x.fillStyle = '#7a3b2e'; x.beginPath(); x.arc(150, 150, 80, 0, 7); x.fill();
    x.fillStyle = '#2f5d3a'; x.fillRect(40, 40, 70, 50);
    const B = cv(520, 520);
    const y = B.getContext('2d');
    y.fillStyle = '#c9b98a'; y.fillRect(0, 0, 520, 520);
    const M0 = new DOMMatrix().translate(40, 30).rotate(15).scale(1.25);
    y.setTransform(M0); y.drawImage(A, 0, 0); y.setTransform(1, 0, 0, 1, 0, 0);
    const a1 = {x:60, y:60}, a2 = {x:240, y:200};
    const q1 = M0.transformPoint(new DOMPoint(a1.x+0.5, a1.y+0.5));
    const q2 = M0.transformPoint(new DOMPoint(a2.x+0.5, a2.y+0.5));
    const b1 = {x:Math.round(q1.x-0.5), y:Math.round(q1.y-0.5)};
    const b2 = {x:Math.round(q2.x-0.5), y:Math.round(q2.y-0.5)};
    await H.loadPair(await fileOf(A, 'A.png'), await fileOf(B, 'B.png'));
    H.setAnchors([a1, a2], [b1, b2]);
    H.applyManual();
    const d = H.diffCount(), total = 300*300;
    ok('manual-sim-ratio<5%', d / total < 0.05, {d: d, total: total});
    ok('manual-sim-interior-circle0', H.diffAt(150, 150) === 0, H.diffAt(150, 150));
    ok('manual-sim-interior-rect0', H.diffAt(75, 65) === 0, H.diffAt(75, 65));
    ok('manual-sim-interior-bg0', H.diffAt(20, 280) === 0, H.diffAt(20, 280));
    const gi = H.gridInfo();
    ok('manual-sim-grid-A', gi.w === 300 && gi.h === 300, gi);
  }

  // T9 replace: manual -> replace B with identical copy of A -> auto align, 0 diff, anchors cleared
  {
    const A = cv(300, 300);
    const x = A.getContext('2d');
    x.fillStyle = '#c9b98a'; x.fillRect(0, 0, 300, 300);
    x.fillStyle = '#7a3b2e'; x.beginPath(); x.arc(150, 150, 80, 0, 7); x.fill();
    x.fillStyle = '#2f5d3a'; x.fillRect(40, 40, 70, 50);
    await H.replaceSlot('B', await fileOf(A, 'repl.png'));
    ok('replace-back-to-auto', H.S.align === 'auto', H.S.align);
    ok('replace-anchors-B-cleared', H.S.anchors.B.length === 0, H.S.anchors.B.length);
    ok('replace-diff-0', H.diffCount() === 0, H.diffCount());
    const gi = H.gridInfo();
    ok('replace-grid-max', gi.w === 300 && gi.h === 300, gi);
  }

  // T10 view modes via real button clicks
  {
    document.querySelector('#grpView button[data-v="hsplit"]').click();
    ok('hsplit-2canvases', document.querySelectorAll('#stage canvas').length === 2, document.querySelectorAll('#stage canvas').length);
    ok('grpShow-removed', document.getElementById('grpShow') === null);
    document.querySelector('#grpView button[data-v="vsplit"]').click();
    ok('vsplit-class', document.getElementById('stage').className === 'vsplit', document.getElementById('stage').className);
    document.querySelector('#grpView button[data-v="overlap"]').click();
    ok('overlap-1canvas', document.querySelectorAll('#stage canvas').length === 1);
  }

  // T11 threshold slider UI
  {
    const sl = document.getElementById('thRange');
    sl.value = 90;
    sl.dispatchEvent(new Event('input', { bubbles: true }));
    ok('thr-ui-90', H.S.threshold === 90 && document.getElementById('thVal').textContent === '90',
       [H.S.threshold, document.getElementById('thVal').textContent]);
    H.setThreshold(20);
  }

  // T12 focus buttons
  {
    document.querySelector('#grpFocus button[data-v="A"]').click();
    ok('focus-A', H.S.focus === 'A', H.S.focus);
    document.querySelector('#grpFocus button[data-v="all"]').click();
    ok('focus-back-all', H.S.focus === 'all', H.S.focus);
  }

  // T13 align overlay open/close via real buttons
  {
    document.querySelector('#grpAlign button[data-v="manual"]').click();
    ok('ao-opens', document.getElementById('ao').hidden === false);
    document.getElementById('aoCancel').click();
    ok('ao-closes', document.getElementById('ao').hidden === true);
  }

  // demo view for screenshot: offset square on grayscale + red band
  {
    const a = cv(240, 180), b = cv(240, 180);
    const ca = a.getContext('2d'), cb = b.getContext('2d');
    ca.fillStyle = '#e8e8e8'; ca.fillRect(0, 0, 240, 180);
    cb.fillStyle = '#e8e8e8'; cb.fillRect(0, 0, 240, 180);
    ca.fillStyle = '#404040'; ca.fillRect(60, 50, 70, 70);
    cb.fillStyle = '#404040'; cb.fillRect(72, 58, 70, 70);
    ca.fillStyle = '#909090'; ca.beginPath(); ca.arc(170, 40, 22, 0, 7); ca.fill();
    cb.fillStyle = '#909090'; cb.beginPath(); cb.arc(170, 40, 22, 0, 7); cb.fill();
    await H.loadPair(await fileOf(a, 'demo1.png'), await fileOf(b, 'demo2.png'));
    ok('demo-diff-positive', H.diffCount() > 500, H.diffCount());
    document.querySelector('#grpView button[data-v="hsplit"]').click();
  }

  ok('no-page-errors', R.errors.length === 0, R.errors);
  done(R);
})().catch(e => { R.fail++; R.log.push('SUITE-THROW ' + String(e && e.stack || e)); R.errors.push(String(e)); done(R); });
"""


def main():
    proc = subprocess.Popen(
        [GECKO, "--port", str(PORT), "--log", "error"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.2)
        cap = api(None, "/session", body={
            "capabilities": {"alwaysMatch": {"moz:firefoxOptions": {"args": ["-headless"]}}}
        })
        sid = cap["value"]["sessionId"]
        api(sid, "timeouts", body={"script": 180000})
        api(sid, "window/rect", body={"width": 1280, "height": 860})
        api(sid, "url", body={"url": PAGE})
        time.sleep(0.8)
        res = api(sid, "execute/async", body={"script": SUITE, "args": []})["value"]

        print("\n".join(res["log"]))
        print("\nPASS %d  FAIL %d  pageErrors %d" % (res["pass"], res["fail"], len(res["errors"])))

        time.sleep(0.6)
        shot = api(sid, "screenshot", method="GET")
        with open(SHOT, "wb") as f:
            f.write(base64.b64decode(shot["value"]))
        print("screenshot:", SHOT)
        api(sid, "", method="DELETE")
        return 0 if res["fail"] == 0 and len(res["errors"]) == 0 else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
