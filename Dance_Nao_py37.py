# -*- coding: utf-8 -*-
"""
Dance_Nao.py
============

Pure Choreography for an Aldebaran / SoftBank NAO robot, timed to the structure of
Queen's "We Are the Champions".

This script contains DANCE ONLY (movements, postures, timing, and vocal lines).
All LED/eye operations have been decoupled into Eye_LED_Nao.py.
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
        test_proxy = ALProxy("ALTextToSpeech", ip, port)
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
# 3. THE DANCER (MOTION ONLY)
# --------------------------------------------------------------------------

ARMS = ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll",
        "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll"]

LEGS = ["LHipRoll", "LHipPitch", "LKneePitch", "LAnklePitch", "LAnkleRoll",
        "RHipRoll", "RHipPitch", "RKneePitch", "RAnklePitch", "RAnkleRoll"]

class ChampionDancer(object):
    def __init__(self, get_services, speak=True):
        if not isinstance(get_services, list):
            get_services = [get_services]
            
        self.motions = []
        self.postures = []
        self.ttss = []
        self.lifes = []
        
        for get_service in get_services:
            self.motions.append(get_service("ALMotion"))
            self.postures.append(get_service("ALRobotPosture"))
            self.ttss.append(get_service("ALTextToSpeech"))
            try: self.lifes.append(get_service("ALAutonomousLife"))
            except: self.lifes.append(None)

        self.speak = speak
        self.t0 = None

    def setup(self):
        for life in self.lifes:
            if life is not None:
                try:
                    if life.getState() != "disabled": life.setState("disabled")
                except: pass

        for motion in self.motions:
            try: motion.wakeUp()
            except: pass
        time.sleep(1.0)

        for motion in self.motions:
            try:
                motion.setStiffnesses("Body", 1.0)
                motion.setFallManagerEnabled(True)
                motion.setExternalCollisionProtectionEnabled("Move", True)
                try:
                    motion.setBreathEnabled("Body", False)
                    motion.setIdlePostureEnabled("Body", False)
                except: pass
            except: pass

        for posture in self.postures:
            try: posture.post.goToPosture("Stand", 0.6)
            except: pass
        time.sleep(2.0)
        self._crouch(0.25, duration=1.2)

    def shutdown(self):
        print("\nShutting down motion...")
        for motion in self.motions:
            try: motion.killAll()
            except: pass
                
        for posture in self.postures:
            try: posture.post.goToPosture("Crouch", 0.5)
            except: pass
        time.sleep(1.5)

        for motion in self.motions:
            try:
                motion.rest()
                motion.setStiffnesses("Body", 0.0)
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

    # ---------------- low-level helpers ----------------
    def _move(self, names, angles, times, blocking=True):
        if isinstance(names, list):
            n = len(names)
            if isinstance(times, list) and len(times) == 1 and n > 1: times = times * n
            elif isinstance(times, (int, float)): times = [times] * n
            
            if isinstance(angles, list) and len(angles) == 1 and n > 1: angles = angles * n
            elif isinstance(angles, (int, float)): angles = [angles] * n

        if isinstance(times, list) and len(times) > 0: duration = max(times)
        elif isinstance(times, (int, float)): duration = times
        else: duration = 1.0

        try:
            for motion in self.motions:
                motion.post.angleInterpolation(names, angles, times, True)
            if blocking: time.sleep(duration)
        except: pass

    def _crouch(self, depth, duration=0.6, blocking=True):
        depth = max(0.05, min(0.7, depth))
        hip = -depth / 2.0
        ankle = -depth / 2.0
        names = ["LHipPitch", "LKneePitch", "LAnklePitch", "RHipPitch", "RKneePitch", "RAnklePitch"]
        angles = [hip, depth, ankle, hip, depth, ankle]
        self._move(names, angles, [duration] * 6, blocking)

    def _sway_to(self, side, amount=0.09, duration=None):
        duration = duration or BEAT
        roll = amount * side
        names = ["LHipRoll", "RHipRoll", "LAnkleRoll", "RAnkleRoll"]
        angles = [roll, roll, -roll, -roll]
        self._move(names, angles, [duration] * 4, blocking=True)

    # ---------------- motifs ----------------
    def m_head_bob(self, count=1, depth=0.18, period=None):
        period = period or BEAT
        for _ in range(count):
            self._move(["HeadPitch"], [depth], [period * 0.5])
            self._move(["HeadPitch"], [-depth * 0.6], [period * 0.5])

    def m_sway_cycle(self, amount=0.09, period=None):
        period = period or BAR
        half = period / 2.0
        for motion in self.motions:
            try: motion.post.angleInterpolation(["HeadYaw"], [0.25], [half], True)
            except: pass
        self._sway_to(-1, amount, half)
        for motion in self.motions:
            try: motion.post.angleInterpolation(["HeadYaw"], [-0.25], [half], True)
            except: pass
        self._sway_to(+1, amount, half)

    def m_arms_low_swing(self, period=None):
        period = period or BAR
        half = period / 2.0
        self._move(ARMS, [1.30, 0.28, -1.2, -0.55, 1.05, -0.16, 1.2, 0.95], [half] * 8)
        self._move(ARMS, [1.05, 0.16, -1.2, -0.95, 1.30, -0.28, 1.2, 0.55], [half] * 8)

    def m_victory_v(self, duration=0.9):
        for motion in self.motions:
            try:
                motion.post.openHand("LHand")
                motion.post.openHand("RHand")
            except: pass
        self._move(ARMS, [-1.15, 0.95, -0.9, -0.35, -1.15, -0.95, 0.9, 0.35], [duration] * 8)

    def m_fist_pump(self, count=2, period=None):
        period = period or BEAT
        for motion in self.motions:
            try:
                motion.post.closeHand("LHand")
                motion.post.closeHand("RHand")
            except: pass
        for i in range(count):
            if i % 2 == 0:
                names = ["RShoulderPitch", "RShoulderRoll", "RElbowRoll", "RElbowYaw"]
                up = [-1.30, -0.20, 0.20, 1.2]
                down = [0.30, -0.25, 1.30, 1.2]
            else:
                names = ["LShoulderPitch", "LShoulderRoll", "LElbowRoll", "LElbowYaw"]
                up = [-1.30, 0.20, -0.20, -1.2]
                down = [0.30, 0.25, -1.30, -1.2]
            self._move(names, up, [period * 0.35])
            self._move(names, down, [period * 0.65])

    def m_wave_crowd(self, count=2, period=None):
        period = period or BEAT
        self._move(["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll"], [-0.9, -0.5, 1.4, 0.9], [period])
        for _ in range(count):
            self._move(["RElbowRoll", "RWristYaw"], [0.35, -1.0], [period * 0.5] * 2)
            self._move(["RElbowRoll", "RWristYaw"], [1.10, 1.0], [period * 0.5] * 2)

    def m_arms_rise(self, duration=2.4):
        for motion in self.motions:
            try:
                motion.post.openHand("LHand")
                motion.post.openHand("RHand")
            except: pass
        self._move(ARMS, [0.20, 0.60, -1.3, -0.60, 0.20, -0.60, 1.3, 0.60], [duration] * 8)

    def m_bounce(self, count=2, depth=0.35, period=None):
        period = period or BEAT
        base = 0.25
        for _ in range(count):
            self._crouch(depth, period * 0.45)
            self._crouch(base, period * 0.55)

    def m_champion_pose(self, duration=1.4):
        for motion in self.motions:
            try:
                motion.post.openHand("LHand")
                motion.post.openHand("RHand")
            except: pass
        names = ARMS + ["HeadPitch", "HeadYaw"]
        angles = [-1.55, 0.55, -1.0, -0.10, -1.55, -0.55, 1.0, 0.10, -0.45, 0.0]
        self._move(names, angles, [duration] * len(names))

    def m_bow(self, duration=2.0):
        self._move(ARMS + ["HeadPitch"], [0.75, 0.30, -1.2, -0.60, 0.75, -0.30, 1.2, 0.60, 0.45], [duration] * 9)
        self._move(["LHipPitch", "RHipPitch"], [-0.45, -0.45], [duration] * 2)
        time.sleep(0.6)
        self._move(["LHipPitch", "RHipPitch"], [-0.15, -0.15], [1.0, 1.0])
        self._move(["HeadPitch"], [0.0], [1.0])

    def m_hip_twist(self, count=2, period=None):
        period = period or BEAT
        half = period / 2.0
        for _ in range(count):
            self._move(["LHipYawPitch", "RHipYawPitch"], [-0.2, -0.2], [half] * 2)
            self._move(["LHipYawPitch", "RHipYawPitch"], [0.2, 0.2], [half] * 2)
        self._move(["LHipYawPitch", "RHipYawPitch"], [0.0, 0.0], [0.2] * 2)

    def m_hip_wiggle(self, count=2, period=None):
        period = period or BEAT
        half = period / 2.0
        for _ in range(count):
            self._sway_to(-1, amount=0.13, duration=half)
            self._sway_to(1, amount=0.13, duration=half)
        self._sway_to(0, amount=0.0, duration=0.2)

    # ---------------- sections ----------------
    def _has_time(self, deadline, need):
        return self.elapsed() + need < deadline

    def sec_intro(self, deadline):
        self._move(["HeadPitch", "HeadYaw"], [-0.25, 0.0], [2.0, 2.0], False)
        self._move(ARMS, [1.35, 0.18, -1.2, -0.55, 1.35, -0.18, 1.2, 0.55], [2.5] * 8)
        while self._has_time(deadline, 0.5): time.sleep(0.2)

    def sec_verse(self, deadline):
        while self._has_time(deadline, BAR + 0.2):
            self.m_arms_low_swing(BAR)
            self.m_head_bob(1, 0.12, BEAT)

    def sec_prechorus(self, deadline):
        self.m_arms_rise(2.0)
        self._crouch(0.40, 1.2, blocking=False)
        while self._has_time(deadline, BEAT):
            self.m_head_bob(1, 0.20, BEAT)

    def sec_chorus(self, deadline):
        self.m_victory_v(BEAT)
        while self._has_time(deadline, BAR + 0.4):
            self.m_fist_pump(2, BEAT)
            self.m_bounce(1, 0.38, BEAT)
            self.m_victory_v(BEAT * 0.8)
            self.m_head_bob(1, 0.18, BEAT)

    def sec_bridge(self, deadline):
        while self._has_time(deadline, BAR + 0.4):
            for motion in self.motions:
                try: motion.post.angleInterpolation(ARMS, [-0.60, 0.85, -1.0, -0.35, 0.90, -0.20, 1.2, 0.80], [BEAT * 1.5]*8, True)
                except: pass
            self._crouch(0.35, duration=BEAT * 1.5)
            
            for motion in self.motions:
                try: motion.post.angleInterpolation(ARMS, [0.90, 0.20, -1.2, -0.80, -0.60, -0.85, 1.0, 0.35], [BEAT * 1.5]*8, True)
                except: pass
            self._crouch(0.25, duration=BEAT * 1.5)
        self._crouch(0.25, duration=0.4)

    def sec_final_build(self, deadline):
        period = BEAT
        while self._has_time(deadline, period * 2):
            self.m_fist_pump(2, period)
            period = max(BEAT * 0.72, period * 0.88)

    def sec_finale(self, deadline):
        self.say("Victory!")
        while self._has_time(deadline, BAR + 0.6):
            self.m_champion_pose(BEAT * 0.9)
            self.m_bounce(2, 0.45, BEAT * 0.7)
            self.m_fist_pump(2, BEAT * 0.7)

    def sec_hold(self, deadline):
        self.m_champion_pose(1.2)
        self._crouch(0.22, 1.2, blocking=False)
        while self._has_time(deadline, 0.5):
            time.sleep(0.25)

    def sec_bow(self, deadline):
        self.m_bow(1.8)
        self.say("Thank you!")
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
    p = argparse.ArgumentParser(description="NAO performs 'We Are the Champions' choreography (Motion Only).")
    p.add_argument("--ip", default=DEFAULT_IP, help="robot IP(s), comma-separated for multiple robots (default %s)" % DEFAULT_IP)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--silent", action="store_true", help="suppress the spoken interjections")
    p.add_argument("--wait-for-key", action="store_true", help="pause after standing; press Enter to start the routine")
    p.add_argument("--start-at", type=float, default=0.0, help="skip N seconds into the choreography (rehearsal aid)")
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
        
    dancer = ChampionDancer(get_services, speak=not args.silent)

    try:
        print("Preparing motion...")
        dancer.setup()
        if args.wait_for_key:
            try: raw_input("Ready. Press Enter to start the routine...")
            except NameError: input("Ready. Press Enter to start the routine...")
        else:
            time.sleep(0.5)
        run_show(dancer, args.start_at)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as exc:
        print("\nError during show: %s" % exc)
        raise
    finally:
        dancer.shutdown()

if __name__ == "__main__":
    main()
