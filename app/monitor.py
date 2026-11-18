import logging
import time
from pathlib import Path
from .database import connect, init, utc_now
from .config import INTERVAL

LOG=logging.getLogger(__name__)

def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()

def synced():
    # timedatectl reports whether system time has been synchronized.
    import subprocess
    try:
        out=subprocess.run(["timedatectl","show","-p","NTPSynchronized","--value"],capture_output=True,text=True,timeout=5)
        return out.returncode==0 and out.stdout.strip().lower()=="yes"
    except Exception:
        return False

def tick(now=None, current_boot=None, mono=None):
    now=now or utc_now()
    current_boot=current_boot or boot_id()
    mono=time.monotonic() if mono is None else mono
    stamp=now.isoformat()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        prev=db.execute("SELECT * FROM state WHERE id=1").fetchone()
        if prev:
            from datetime import datetime
            previous=datetime.fromisoformat(prev["last_seen"])
            gap=(now-previous).total_seconds()
            same_boot=prev["boot_id"]==current_boot
            monotonic_gap=mono-prev["mono"] if same_boot else -1
            # A long pause may indicate downtime, suspend, a hung agent, or clock adjustment.
            if gap > max(45, INTERVAL*3) and (not same_boot or monotonic_gap > max(45, INTERVAL*3)):
                db.execute("INSERT INTO gaps(started_at,ended_at,seconds,kind,note) VALUES(?,?,?,?,?)",
                    (prev["last_seen"],stamp,gap,"unknown","Unobserved interval; not proof of power outage"))
        db.execute("""INSERT INTO state(id,last_seen,boot_id,mono) VALUES(1,?,?,?)
                      ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,
                      boot_id=excluded.boot_id,mono=excluded.mono""",(stamp,current_boot,mono))
        row=db.execute("SELECT id FROM sessions WHERE boot_id=? ORDER BY id DESC LIMIT 1",(current_boot,)).fetchone()
        if row:
            db.execute("UPDATE sessions SET last_seen=? WHERE id=?",(stamp,row["id"]))
        else:
            db.execute("INSERT INTO sessions(boot_id,started_at,last_seen) VALUES(?,?,?)",(current_boot,stamp,stamp))

def main():
    logging.basicConfig(level=logging.INFO)
    init()
    while not synced():
        LOG.warning("Waiting for NTP synchronization; refusing unreliable timestamps")
        time.sleep(10)
    LOG.info("Monitor running, heartbeat %ss", INTERVAL)
    while True:
        try:
            tick()
        except Exception:
            LOG.exception("Heartbeat failed")
        time.sleep(INTERVAL)

if __name__=="__main__":
    main()
