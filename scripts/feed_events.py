import json, time, argparse, requests

def feed(file_path, api_url, realtime=False, batch_size=100):
    events = [json.loads(l) for l in open(file_path)]
    print("Loaded " + str(len(events)) + " events")
    sent = 0
    for i in range(0, len(events), batch_size):
        batch = events[i:i+batch_size]
        r = requests.post(api_url + "/events/ingest", json={"events": batch}, timeout=10)
        d = r.json()
        sent += d.get("accepted", 0)
        print("  Batch " + str(i//batch_size+1) + ": accepted=" + str(d["accepted"]) + " dup=" + str(d["duplicate"]) + " rej=" + str(d["rejected"]))
        if realtime and i + batch_size < len(events):
            time.sleep(0.5)
    print("Done. Total sent: " + str(sent))

if __name__ == "__main__":
    pa = argparse.ArgumentParser()
    pa.add_argument("--file", default="data/events_all.jsonl")
    pa.add_argument("--api",  default="http://localhost:8000")
    pa.add_argument("--realtime", action="store_true")
    args = pa.parse_args()
    feed(args.file, args.api, args.realtime)
