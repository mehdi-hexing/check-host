import time
import requests
from fastapi import FastAPI, HTTPException

app = FastAPI()

CHECK_HOST_BASE = "https://check-host.net"
HEADERS = {"Accept": "application/json"}


def get_available_nodes_for_country(country_code: str):
    try:
        resp = requests.get(f"{CHECK_HOST_BASE}/nodes/hosts", headers=HEADERS, timeout=10)
        data = resp.json().get("nodes", {})
        
        country_code = country_code.lower()
        matched_nodes = []

        for node_name, info in data.items():
            c_info = info.get("country", [])
            node_country = c_info[2].lower() if len(c_info) > 2 else ""
            
            if country_code == "all":
                matched_nodes.append(node_name)
            elif node_country == country_code or node_name.startswith(country_code):
                matched_nodes.append(node_name)

        if not matched_nodes:
            matched_nodes = [
                f"{country_code}1.node.check-host.net",
                f"{country_code}2.node.check-host.net"
            ]

        return matched_nodes
    except Exception:
        return [
            f"{country_code}1.node.check-host.net",
            f"{country_code}2.node.check-host.net"
        ]


def check_host_reachability(host: str, country: str):
    selected_nodes = get_available_nodes_for_country(country)
    
    node_params = "&".join([f"node={node}" for node in selected_nodes])
    init_url = f"{CHECK_HOST_BASE}/check-ping?host={host}&{node_params}"
    
    try:
        init_response = requests.get(init_url, headers=HEADERS, timeout=10)
        init_data = init_response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    request_id = init_data.get("request_id")
    if not request_id:
        raise HTTPException(status_code=502, detail="Request ID not found in response")

    time.sleep(3)

    result_url = f"{CHECK_HOST_BASE}/check-result/{request_id}"
    try:
        result_response = requests.get(result_url, headers=HEADERS, timeout=10)
        result_data = result_response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    accessible_from_at_least_one_node = False
    details = {}

    for node in selected_nodes:
        node_res = result_data.get(node)
        if node_res and isinstance(node_res, list) and len(node_res) > 0:
            if isinstance(node_res[0], list):
                ping_samples = node_res[0]
                ok_pings = [
                    sample for sample in ping_samples 
                    if isinstance(sample, list) and len(sample) > 0 and sample[0] == "OK"
                ]
                
                if ok_pings:
                    accessible_from_at_least_one_node = True
                    latencies = [p[1] for p in ok_pings if len(p) > 1 and isinstance(p[1], (int, float))]
                    avg_latency = round(sum(latencies) / len(latencies) * 1000, 2) if latencies else None
                    details[node] = {"status": "OK", "ping_ms": avg_latency}
                else:
                    details[node] = {"status": "FAIL", "ping_ms": None}
            else:
                details[node] = {"status": "UNKNOWN", "raw": node_res}
        else:
            details[node] = {"status": "TIMEOUT", "ping_ms": None}

    return {
        "host": host,
        "country": country,
        "is_accessible": accessible_from_at_least_one_node,
        "nodes_checked": len(selected_nodes),
        "details": details,
        "report_url": f"{CHECK_HOST_BASE}/check-report/{request_id}"
    }


@app.get("/{country}/{host}")
@app.get("/check/{country}/{host}")
def check_by_path(country: str, host: str):
    return check_host_reachability(host=host, country=country)


@app.get("/")
def check_by_query(host: str = None, country: str = "ir"):
    if not host:
        return {"status": "running", "usage": "/{country}/{host}"}
    return check_host_reachability(host=host, country=country)
