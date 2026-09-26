#!/usr/bin/env python3
"""
optical_rx.py - host-side decoder for the Optical Data Transfer Concept

Reads raw little-endian uint16 samples (600 S/s) from the Arduino over serial,
recovers the Manchester-coded frame, and prints text / saves files.

Pipeline:  samples -> adaptive threshold (running min/max, slice at midpoint)
           -> Manchester clock recovery off the mid-bit transitions
           -> preamble + sync detection -> type / length / payload / CRC-8

FRAME CONTRACT (matches transmitter/Optical_Tx.html; see docs/PROTOCOL.md):
    preamble : 16 alternating bits, starting with 1   (1010...1010)
    sync     : 0x7E
    type     : 1 byte   0x00 = UTF-8 text, 0x01 = binary file
    length   : 2 bytes, big-endian
    payload  : length bytes
    crc      : CRC-8 poly 0x07, init 0x00, over [type, len_hi, len_lo, payload]
    Manchester: logical 1 -> bright,dark ; logical 0 -> dark,bright
                (bright = higher ADC counts)

Modes:
    --selftest         synth a noisy sample stream and decode it (no hardware)
    --replay FILE      decode raw uint16 samples saved from a prior --record
    --port DEV         live decode from serial; add --record FILE to also save the
                       raw samples for --replay. Start this BEFORE the transmitter.

With no arguments it prints help. Find DEV with:  python3 -m serial.tools.list_ports
"""

import argparse
import bisect
import os
import struct
import sys
import time

# ---- link constants ------------------------------------------------------
BAUD         = 115200
SAMPLE_RATE  = 600
SYNC         = 0x7E
TYPE_TEXT    = 0x00
TYPE_BINARY  = 0x01
ADC_MAX      = 0x3FFF          # 14-bit; top two bits of every byte-pair are 0

# Live mode: the rolling buffer must be longer than the longest frame, or the
# start of a long frame is discarded before its end arrives (a 127-byte file
# takes ~72 s at 15 bps). Decoding a long buffer is expensive, so attempt a
# decode about once per second of new data rather than on every read.
LIVE_BUFFER_S  = 300
DECODE_EVERY_S = 1.0

# clock-recovery search bounds, in samples per logical bit
MIN_SPB = 6
MAX_SPB = 200        # up to ~200 samples/bit => rates down to ~3 bps at 600 S/s

# Software anti-flicker pre-filter. Backlight flicker below the 300 Hz Nyquist
# (e.g. a panel's 135-230 Hz PWM) can't be removed after aliasing, but if it's
# below Nyquist a low-pass here strips it before clock recovery. Passes symbol
# rates up to ~30 Hz (>=15 bps) while cutting >100 Hz flicker hard.
PREFILTER_HZ = 70
PREFILTER_POLES = 2


def lowpass(sig, fc=PREFILTER_HZ, poles=PREFILTER_POLES, fs=SAMPLE_RATE):
    a = 1.0 / (1.0 + fs / (2 * 3.141592653589793 * fc))
    y = list(sig)
    for _ in range(poles):
        acc = y[0]; out = []
        for v in y:
            acc += a * (v - acc); out.append(acc)
        y = out
    return y


# ---- CRC-8 (poly 0x07, init 0x00) ----------------------------------------
def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


# ---- adaptive threshold (peak tracker) -----------------------------------
def threshold_series(samples, relax=0.002):
    """Running min/max that snaps to new extremes and relaxes slowly.
    Returns (thr, lo, hi) per-sample lists. Slice point is the midpoint."""
    n = len(samples)
    thr = [0.0] * n
    mn = mx = samples[0]
    for i, s in enumerate(samples):
        mx = s if s > mx else mx + (s - mx) * relax
        mn = s if s < mn else mn + (s - mn) * relax
        thr[i] = (mn + mx) / 2.0
    return thr


def edges_from(samples, thr, hyst_frac=0.12):
    """Binarize with hysteresis and return (edge_indices, binary)."""
    n = len(samples)
    # amplitude estimate for hysteresis
    span = max(1.0, (max(samples) - min(samples)))
    h = span * hyst_frac / 2.0
    binary = [0] * n
    state = 1 if samples[0] > thr[0] else 0
    edges = []
    for i in range(n):
        if state == 0 and samples[i] > thr[i] + h:
            state = 1; edges.append(i)
        elif state == 1 and samples[i] < thr[i] - h:
            state = 0; edges.append(i)
        binary[i] = state
    return edges, binary


# ---- clock recovery ------------------------------------------------------
def recover_clock(edges):
    """Find the preamble: a run of near-equal edge intervals. That interval is
    T_bit (mid-bit edges are one bit apart during an alternating preamble).
    Returns (t_bit, anchor_edge_index) or None."""
    if len(edges) < 9:
        return None
    ivals = [edges[i + 1] - edges[i] for i in range(len(edges) - 1)]
    best = None
    i = 0
    while i < len(ivals):
        j = i
        # grow a run whose intervals stay within +/-30% of the run's first
        ref = ivals[i]
        while j < len(ivals) and abs(ivals[j] - ref) <= 0.30 * ref:
            # keep ref as a running median-ish anchor
            ref = 0.7 * ref + 0.3 * ivals[j]
            j += 1
        run_len = j - i
        if run_len >= 8:
            run = sorted(ivals[i:j])
            t_run = run[len(run) // 2]           # median interval of the run
            # Manchester edge spacing is only ever T/2 or T. The preamble's run
            # is spaced T, but a run of repeated bits in the payload (e.g. a
            # 0x00 byte) is spaced T/2 and is bounded by T-length intervals.
            # If a neighbor of this run is ~2x its spacing, it is such a run:
            # the true bit period is 2x, and the edge that ends that longer
            # interval is a real mid-bit edge. This lets the decoder lock on
            # correctly even when it starts listening partway through a frame.
            def _about(k, target):
                return 0 <= k < len(ivals) and abs(ivals[k] - target) <= 0.30 * target
            t_bit, anchor = t_run, edges[i]
            if _about(i - 1, 2 * t_run):
                t_bit, anchor = 2 * t_run, edges[i]
            elif _about(j, 2 * t_run):
                t_bit, anchor = 2 * t_run, edges[j]
            if MIN_SPB <= t_bit <= MAX_SPB:
                # anchor: a real mid-bit edge to start decoding from
                return float(t_bit), anchor
        i = j if j > i else i + 1
    return best


# ---- Manchester decode with per-bit edge tracking ------------------------
def _mean(samples, a, b):
    a = max(0, a); b = min(len(samples), b)
    if b <= a:
        return 0.0
    return sum(samples[a:b]) / (b - a)


def _nearest_edge(edges, pos, window):
    """Nearest edge index to pos within +/-window, else None.
    edges is sorted, so binary-search to the window instead of scanning."""
    best = None; bd = window + 1
    k = bisect.bisect_left(edges, pos - window)
    while k < len(edges) and edges[k] <= pos + window:
        d = abs(edges[k] - pos)
        if d < bd:
            best = edges[k]; bd = d
        k += 1
    return best


def decode_bits(samples, edges, t_bit, start_center, max_bits):
    """Decode logical bits from start_center forward, re-anchoring each bit to
    the real mid-bit edge so slow clock drift can't accumulate."""
    bits = []
    half = t_bit / 2.0
    center = float(start_center)
    track_win = t_bit * 0.35          # excludes boundary edges (~0.5*t_bit away)
    while len(bits) < max_bits:
        a0 = int(round(center - half)); a1 = int(round(center)); a2 = int(round(center + half))
        if a2 >= len(samples):
            break
        first = _mean(samples, a0, a1)
        second = _mean(samples, a1, a2)
        bits.append(1 if first > second else 0)     # bright-then-dark = 1
        e = _nearest_edge(edges, center, track_win)
        center = (e if e is not None else center) + t_bit
    return bits


# ---- frame parse ---------------------------------------------------------
def _bits_to_byte(bits, o):
    v = 0
    for k in range(8):
        v = (v << 1) | bits[o + k]
    return v


def parse_frames(bits):
    """Search a decoded bit list for sync-aligned frames; yield (ftype, payload).
    Returns (frames, need_more) - need_more True if a valid header wanted more bits."""
    frames = []
    need_more = False
    o = 0
    N = len(bits)
    while o + 8 <= N:
        if _bits_to_byte(bits, o) != SYNC:
            o += 1
            continue
        # require an alternating preamble tail just before the sync
        if o >= 4 and not (bits[o-4] != bits[o-3] and bits[o-3] != bits[o-2] and bits[o-2] != bits[o-1]):
            o += 1
            continue
        p = o + 8
        if p + 24 > N:
            need_more = True; break
        ftype = _bits_to_byte(bits, p)
        length = (_bits_to_byte(bits, p + 8) << 8) | _bits_to_byte(bits, p + 16)
        p += 24
        need = length * 8 + 8       # payload + crc
        if p + need > N:
            need_more = True; break
        payload = bytes(_bits_to_byte(bits, p + 8 * k) for k in range(length))
        crc = _bits_to_byte(bits, p + 8 * length)
        if crc8(bytes([ftype, (length >> 8) & 0xFF, length & 0xFF]) + payload) == crc:
            frames.append((ftype, payload))
            o = p + need              # jump past this frame
        else:
            o += 1                    # false sync; keep hunting
    return frames, need_more


def decode_buffer(samples):
    """Full decode of a sample buffer. Returns (frames, consumed_upto_index)."""
    if len(samples) < 64:
        return [], 0
    samples = lowpass(samples)          # strip sub-Nyquist backlight flicker
    thr = threshold_series(samples)
    edges, _ = edges_from(samples, thr)
    clk = recover_clock(edges)
    if clk is None:
        return [], 0
    t_bit, anchor = clk
    # anchor is a real mid-bit edge; decode forward from it, on the mid-bit grid
    max_bits = int((len(samples) - anchor) / t_bit)
    bits = decode_bits(samples, edges, t_bit, anchor, max_bits)
    frames, _ = parse_frames(bits)
    return frames, len(samples)


# ---- output helpers ------------------------------------------------------
def emit(ftype, payload, outdir="."):
    if ftype == TYPE_TEXT:
        print(f"[RX] TEXT ({len(payload)} B): {payload.decode('utf-8', 'replace')}")
    else:
        if payload[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif payload.isascii() and b"," in payload and b"\n" in payload:
            ext = ".csv"          # printable ASCII with commas + newline => looks like CSV
        else:
            ext = ".bin"
        name = os.path.join(outdir, f"received_{int(time.time())}{ext}")
        with open(name, "wb") as f:
            f.write(payload)
        print(f"[RX] FILE ({len(payload)} B) -> {name}  (open it)")


# ---- live serial ---------------------------------------------------------
def read_aligned(ser, buf):
    """Pull available bytes, keep 2-byte sample alignment using the 14-bit rule
    (a correctly aligned high byte is always <= 0x3F)."""
    data = ser.read(4096)
    if not data:
        return []
    buf.extend(data)
    # one-time / occasional alignment: if many high bytes exceed 0x3F, shift 1
    if len(buf) >= 64:
        hi_bad = sum(1 for k in range(1, 64, 2) if buf[k] > 0x3F)
        if hi_bad > 8:
            del buf[0]
    out = []
    n = len(buf) - (len(buf) % 2)
    for k in range(0, n, 2):
        out.append(buf[k] | (buf[k + 1] << 8))
    del buf[:n]
    return out


def live(port, record=None):
    try:
        import serial
    except ImportError:
        sys.exit("[RX] pyserial not installed:  pip3 install pyserial")
    print(f"[RX] Opening {port} @ {BAUD} (close any other program holding it)")
    ser = serial.Serial(port, BAUD, timeout=0.2)
    rec = open(record, "wb") if record else None
    raw = bytearray()
    samples = []
    seen = set()
    MAXBUF = SAMPLE_RATE * LIVE_BUFFER_S
    pending = 0                     # samples received since the last decode attempt
    try:
        while True:
            new = read_aligned(ser, raw)
            if new:
                if rec:
                    rec.write(struct.pack(f"<{len(new)}H", *new))
                samples.extend(new)
                pending += len(new)
                if len(samples) > MAXBUF:
                    samples = samples[-MAXBUF:]
            if len(samples) >= SAMPLE_RATE and pending >= SAMPLE_RATE * DECODE_EVERY_S:
                pending = 0
                frames, upto = decode_buffer(samples)
                for ftype, payload in frames:
                    key = (ftype, hash(payload))
                    if key not in seen:
                        seen.add(key)
                        emit(ftype, payload)
                if frames:
                    samples = samples[upto:]
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n[RX] stopped")
    finally:
        ser.close()
        if rec:
            rec.close()


def replay(path):
    with open(path, "rb") as f:
        raw = f.read()
    n = len(raw) // 2
    samples = list(struct.unpack(f"<{n}H", raw[:2 * n]))
    frames, _ = decode_buffer(samples)
    if not frames:
        print("[RX] no frame recovered")
    seen = set()                        # a looped capture holds repeated copies
    for ftype, payload in frames:
        if (ftype, payload) not in seen:
            seen.add((ftype, payload))
            emit(ftype, payload)


# ---- self-test (synthetic loopback) --------------------------------------
def _tx_bits(payload, ftype):
    header = bytes([ftype, (len(payload) >> 8) & 0xFF, len(payload) & 0xFF])
    crc = crc8(header + payload)
    frame = bytes([SYNC]) + header + payload + bytes([crc])
    bits = [1, 0] * 8
    for byte in frame:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _synthesize(payload, ftype, spb, bright=12000, dark=3000, noise=30, ripple=400, drift=0.0):
    """Build a sample stream like the Arduino would produce.
    spb = samples per bit (may be fractional via drift)."""
    import random, math
    bits = _tx_bits(payload, ftype)
    symbols = []
    for b in bits:
        symbols += [1, 0] if b else [0, 1]      # 1=bright,0=dark
    samples = [dark] * int(1.0 * spb * 4)        # idle lead-in
    t = 0.0
    sps = spb / 2.0                              # samples per symbol
    for s in symbols:
        cur = sps * (1.0 + drift)                # simulate a small rate error
        cnt = int(round(cur))
        level = bright if s else dark
        for _ in range(cnt):
            samples.append(level)
    samples += [dark] * int(spb * 4)             # idle tail
    # add flicker ripple (<1.6 kHz) + gaussian noise, clamp to 14-bit
    out = []
    for i, v in enumerate(samples):
        v += ripple * math.sin(2 * math.pi * 110.0 * i / SAMPLE_RATE)
        v += random.gauss(0, noise)
        out.append(max(0, min(ADC_MAX, int(v))))
    return out


def selftest():
    import random
    random.seed(1)
    png = None
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in ("smiley-16.png",
                 os.path.join(here, "smiley-16.png"),
                 os.path.join(here, "..", "demo-assets", "smiley-16.png")):
        if os.path.exists(cand):
            png = open(cand, "rb").read(); break

    cases = [
        ("text @spb=40 (15bps)", b"HELLO OPTICAL WORLD", TYPE_TEXT, 40, 0.0),
        ("text @spb=20 (30bps)", b"HELLO OPTICAL WORLD", TYPE_TEXT, 20, 0.0),
        ("text @spb=30 +0.4% drift", b"Optical link check 12345", TYPE_TEXT, 30, 0.004),
    ]
    if png:
        cases.append((f"smiley PNG {len(png)}B @spb=24", png, TYPE_BINARY, 24, 0.0))
        cases.append((f"smiley PNG {len(png)}B @spb=20 +0.3% drift", png, TYPE_BINARY, 20, 0.003))

    ok = 0
    for name, payload, ftype, spb, drift in cases:
        samples = _synthesize(payload, ftype, spb, drift=drift)
        frames, _ = decode_buffer(samples)
        got = frames[0][1] if frames else b""
        passed = (len(frames) == 1 and got == payload)
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: "
              f"{len(samples)} samples -> {len(frames)} frame(s)"
              + ("" if passed else f"  (recovered {len(got)}/{len(payload)} B)"))
        ok += passed
    print(f"\n{ok}/{len(cases)} cases passed")
    return ok == len(cases)


# ---- entry ---------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Optical link host decoder.")
    ap.add_argument("--port", help="serial device for live decode, e.g. /dev/cu.usbmodem1101, COM5")
    ap.add_argument("--record", metavar="FILE", help="also save raw uint16 samples while live")
    ap.add_argument("--replay", metavar="FILE", help="decode raw uint16 samples from a file")
    ap.add_argument("--selftest", action="store_true", help="synthetic loopback, no hardware")
    ap.add_argument("--live", action="store_true", help="force live decode from --port")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if selftest() else 1)
    if args.replay:
        replay(args.replay); return
    if args.port:
        live(args.port, args.record); return
    if args.live:
        ap.error("--live needs --port DEV (find it with: python3 -m serial.tools.list_ports)")
    ap.print_help()


if __name__ == "__main__":
    main()
