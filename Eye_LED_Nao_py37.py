# -*- coding: utf-8 -*-
"""
Eye_LED_Nao.py
==============

Pure Eye & LED Light Show for Aldebaran / SoftBank NAO robots, timed to Queen's
"We Are the Champions".

This script contains EYE & LED FUNCTIONALITY ONLY.
ALMotion is never touched, so the robots can remain seated, standing, or placed on a desk.
Safe to run standalone or alongside Dance_Nao.py in another terminal!
"""

from __future__ import print_function

import argparse
import math
import os
import socket
import sys
import threading
import time

# Runs using the active Python environment.
# The NAOqi Python SDK must be installed for that environment.

# --------------------------------------------------------------------------
# 1. CONFIGURATION
# --------------------------------------------------------------------------

DEFAULT_IP = "172.20.75.252"
DEFAULT_PORT = 9559

BPM = 62.0
BEAT = 60.0 / BPM          
BAR = BEAT * 3             

SECTION_TIMES = {
    "intro":        0.0,
    "verse_1":      4.0,
    "prechorus_1":  16.0,
    "chorus_1":     22.0,
    "bridge":       36.0,
    "final_build":  46.0,
    "finale":       52.0,
    "hold":         60.0,
    "bow":          64.0,
    "END":          70.0,
}

SECTION_COLORS = {
    "intro":       0x101040, # Deep ambient indigo
    "verse_1":     0x2020A0, # Cool Blue
    "prechorus_1": 0x8040A0, # Mystical Purple
    "chorus_1":    0xFFD000, # Radiant Gold
    "bridge":      0xA02020, # Dramatic Red
    "final_build": 0xFF4000, # Intense Orange
    "finale":      0xFF0000, # Blazing Ruby Red
    "hold":        0xFFD000, # Golden Sine Wave Glow
    "bow":         0x203060, # Respectful Deep Blue
}

# --------------------------------------------------------------------------
# 2. CONNECTION LAYER
# --------------------------------------------------------------------------

class _FakeProxy(object):
    def __init__(self, name, verbose=False):
        self._name = name
        self._verbose = verbose
    def __getattr__(self, call):
        if call == "post": return self
        def _stub(*args, **kwargs): return 0
        return _stub

class _AsyncCaller(object):
    def __init__(self, obj): self._obj = obj
    def __getattr__(self, name):
        method = getattr(self._obj, name)
        def _call(*args):
            try: return method(*args, _async=True)
            except TypeError:
                t = threading.Thread(target=method, args=args)
                t.daemon = True
                t.start()
                return t
        return _call

class _QiService(object):
    def __init__(self, obj):
        object.__setattr__(self, "_obj", obj)
        object.__setattr__(self, "post", _AsyncCaller(obj))
    def __getattr__(self, name): return getattr(self._obj, name)

def probe_port(ip, port, timeout=0.8):
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False

def resolve_target(target_str, default_port=DEFAULT_PORT):
    """Resolves 'ip' or 'ip:port'. Auto-detects port if default_port is closed."""
    if ":" in target_str:
        parts = target_str.split(":", 1)
        return parts[0].strip(), int(parts[1].strip())
    
    ip = target_str.strip()
    if probe_port(ip, default_port, timeout=0.8):
        return ip, default_port
    
    # Try alternative NAOqi ports (e.g. 9561 when 9559 is taken)
    candidate_ports = [9559, 9561, 9560, 9562]
    for p in candidate_ports:
        if p != default_port and probe_port(ip, p, timeout=0.5):
            print("  [Auto-detected] Port %d closed on %s, found open NAOqi service on port %d!" % (default_port, ip, p))
            return ip, p
            
    return ip, default_port

def make_service_getter(ip, port, dry_run=False, verbose=False):
    if dry_run: return lambda name: _FakeProxy(name, verbose)
    errors = []
    try:
        from naoqi import ALProxy  
        test_proxy = ALProxy("ALLeds", ip, port)
        print("Connected via naoqi.ALProxy to %s:%d" % (ip, port))
        return lambda name: ALProxy(name, ip, port)
    except Exception as e:
        errors.append("naoqi.ALProxy: %s" % e)

    try:
        import qi  
        session = qi.Session()
        session.connect("tcp://%s:%d" % (ip, port))
        print("Connected via qi to %s:%d" % (ip, port))
        return lambda name: _QiService(session.service(name))
    except Exception as e:
        errors.append("qi.Session: %s" % e)

    print("\n[Error] Could not connect to robot at %s:%d:" % (ip, port))
    for err in errors:
        print("  - %s" % err)
    sys.exit(1)


# --------------------------------------------------------------------------
# 3. THE EYE & LED CONTROLLER
# --------------------------------------------------------------------------

class ChampionEyeController(object):
    def __init__(self, get_services, speak=True):
        if not isinstance(get_services, list):
            get_services = [get_services]
            
        self.ledss = []
        self.ttss = []
        
        for get_service in get_services:
            self.ledss.append(get_service("ALLeds"))
            try: self.ttss.append(get_service("ALTextToSpeech"))
            except: pass

        self.speak = speak
        self.t0 = None

    def setup(self):
        # Set all robot eyes to gentle white on start
        for leds in self.ledss:
            try:
                leds.post.fadeRGB("FaceLeds", 0xFFFFFF, 0.5)
                leds.post.fadeRGB("ChestLeds", 0xFFFFFF, 0.5)
            except: pass
        time.sleep(0.5)

    def shutdown(self):
        print("\nShutting down LEDs...")
        for leds in self.ledss:
            try:
                leds.post.fadeRGB("FaceLeds", 0xFFFFFF, 0.5)
                leds.post.fadeRGB("ChestLeds", 0xFFFFFF, 0.5)
            except: pass
        print("Done.")

    def say(self, text):
        if not self.speak: return
        for tts in self.ttss:
            try: tts.post.say(text)
            except: pass

    # ---------------- clock ----------------
    def start_clock(self):
        self.t0 = time.time()

    def elapsed(self):
        return time.time() - self.t0

    def sleep_until(self, track_time):
        gap = track_time - self.elapsed()
        if gap > 0: time.sleep(gap)

    # ---------------- LED helpers ----------------
    def leds_section(self, name):
        color = SECTION_COLORS.get(name, 0x404040)
        for leds in self.ledss:
            try:
                leds.post.fadeRGB("FaceLeds", color, 0.4)
                leds.post.fadeRGB("ChestLeds", color, 0.4)
            except: pass

    def leds_flash(self, color=0xFFFFFF, duration=0.15):
        for leds in self.ledss:
            try: leds.post.fadeRGB("FaceLeds", color, duration)
            except: pass

    def m_unison_proclaim(self, text, color=0xFF0000, fade=0.25):
        """Threaded call to turn eyes red and speak simultaneously."""
        def _one(tts, leds):
            try: leds.fadeRGB("FaceLeds", color, fade)
            except: pass
            if self.speak and tts is not None:
                try: tts.post.say(text)
                except: pass

        threads = []
        for i in range(len(self.ledss)):
            leds = self.ledss[i]
            tts = self.ttss[i] if i < len(self.ttss) else None
            t = threading.Thread(target=_one, args=(tts, leds))
            t.daemon = True
            threads.append(t)
        for t in threads: t.start()
        for t in threads: t.join()

    # ---------------- sections ----------------
    def _has_time(self, deadline, need):
        return self.elapsed() + need < deadline

    def sec_intro(self, deadline):
        self.leds_section("intro")
        while self._has_time(deadline, 0.5): time.sleep(0.2)

    def sec_verse(self, deadline):
        self.leds_section("verse_1")
        while self._has_time(deadline, 0.5): time.sleep(0.2)

    def sec_prechorus(self, deadline):
        self.leds_section("prechorus_1")
        while self._has_time(deadline, 0.5): time.sleep(0.2)

    def sec_chorus(self, deadline):
        self.leds_section("chorus_1")
        self.leds_flash(0xFFFFFF, 0.1)
        while self._has_time(deadline, BAR):
            self.leds_flash(0xFFFFFF, 0.1)
            time.sleep(BEAT)

    def sec_bridge(self, deadline):
        self.leds_section("bridge")
        while self._has_time(deadline, 0.5): time.sleep(0.2)

    def sec_final_build(self, deadline):
        self.leds_section("final_build")
        period = BEAT
        while self._has_time(deadline, period):
            self.leds_flash(0xFFFFFF, 0.08)
            time.sleep(period)
            period = max(BEAT * 0.5, period * 0.88)

    def sec_finale(self, deadline):
        # UNISON RED EYES
        self.m_unison_proclaim("Victory!", color=0xFF0000)
        while self._has_time(deadline, 0.5):
            self.leds_flash(0xFFD000, 0.1)
            time.sleep(1.0)

    def sec_hold(self, deadline):
        phase = 0.0
        while self._has_time(deadline, 0.25):
            phase += 0.25
            level = int(120 + 120 * math.sin(phase))
            color = (level << 16) | (level << 8) | (level // 3)
            for leds in self.ledss:
                try: leds.post.fadeRGB("FaceLeds", color, 0.22)
                except: pass
            time.sleep(0.25)

    def sec_bow(self, deadline):
        self.leds_section("bow")
        while self._has_time(deadline, 0.3): time.sleep(0.2)

# --------------------------------------------------------------------------
# 4. TIMELINE
# --------------------------------------------------------------------------

def build_timeline(d):
    routines = {
        "intro":       d.sec_intro,
        "verse_1":     d.sec_verse,
        "prechorus_1": d.sec_prechorus,
        "chorus_1":    d.sec_chorus,
        "bridge":      d.sec_bridge,
        "final_build": d.sec_final_build,
        "finale":      d.sec_finale,
        "hold":        d.sec_hold,
        "bow":         d.sec_bow,
    }
    items = [(SECTION_TIMES[name], name, routines[name]) for name in routines]
    items.sort(key=lambda x: x[0])
    return items

def run_show(d, start_at=0.0):
    timeline = build_timeline(d)
    end_time = SECTION_TIMES["END"]

    print("\n%-6s  %-13s" % ("TIME", "SECTION"))
    print("-" * 24)

    d.start_clock()
    if start_at > 0:
        d.t0 -= start_at
        print("(starting %.1fs into the routine)" % start_at)

    for i, (start, name, routine) in enumerate(timeline):
        deadline = timeline[i + 1][0] if i + 1 < len(timeline) else end_time
        if deadline <= d.elapsed(): continue
        d.sleep_until(start)
        print("%5.1fs  %-13s" % (d.elapsed(), name))
        routine(deadline)

    d.sleep_until(end_time)
    print("%5.1fs  %-13s" % (d.elapsed(), "finished"))

# --------------------------------------------------------------------------
# 5. ENTRY POINT
# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="NAO 'We Are the Champions' Eye & LED Light Show (No Motors).")
    p.add_argument("--ip", default=DEFAULT_IP, help="robot IP(s), comma-separated for multiple robots (default %s)" % DEFAULT_IP)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--silent", action="store_true", help="suppress the spoken interjections")
    p.add_argument("--wait-for-key", action="store_true", help="pause before starting; press Enter to start")
    p.add_argument("--start-at", type=float, default=0.0, help="skip N seconds into the light show")
    p.add_argument("--dry-run", action="store_true", help="no robot; print the timeline in real time")
    p.add_argument("--verbose", action="store_true", help="print every stubbed call")
    args = p.parse_args()

    raw_targets = [ip.strip() for ip in args.ip.split(",") if ip.strip()]

    get_services = []
    for raw in raw_targets:
        if args.dry_run:
            if ":" in raw:
                parts = raw.split(":", 1)
                ip, port = parts[0].strip(), int(parts[1].strip())
            else:
                ip, port = raw, args.port
        else:
            ip, port = resolve_target(raw, args.port)

        print("Connecting to robot at %s:%d..." % (ip, port))
        get_service = make_service_getter(ip, port, args.dry_run, args.verbose)
        get_services.append(get_service)
        
    eye_controller = ChampionEyeController(get_services, speak=not args.silent)

    try:
        print("Preparing LEDs...")
        eye_controller.setup()
        if args.wait_for_key:
            try: raw_input("Ready. Press Enter to start the light show...")
            except NameError: input("Ready. Press Enter to start the light show...")
        else:
            time.sleep(0.5)
        run_show(eye_controller, args.start_at)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as exc:
        print("\nError during show: %s" % exc)
        raise
    finally:
        eye_controller.shutdown()

if __name__ == "__main__":
    main()
