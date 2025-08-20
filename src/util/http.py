import time, requests

DEFAULT_TIMEOUT = 30

def http_get(url, headers=None, params=None, timeout: int = DEFAULT_TIMEOUT):
    backoff = [0, 1.0, 2.0]
    last_exc = None
    for delay in backoff:
        if delay: time.sleep(delay)
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
    raise RuntimeError(f"GET failed: {url} :: {last_exc}")

def post_json(url, payload, headers=None, timeout: int = DEFAULT_TIMEOUT):
    backoff = [0, 1.0, 2.5]
    headers = {"Content-Type": "application/json", **(headers or {})}
    last_exc = None
    for delay in backoff:
        if delay: time.sleep(delay)
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.status_code
        except Exception as e:
            last_exc = e
    raise RuntimeError(f"POST failed: {url} :: {last_exc}")

def post_multipart(url, files, data=None, headers=None, timeout: int = DEFAULT_TIMEOUT):
    # files: dict name-> (filename, bytes, content_type)
    backoff = [0, 1.0, 2.5]
    last_exc = None
    for delay in backoff:
        if delay: time.sleep(delay)
        try:
            r = requests.post(url, files=files, data=data or {}, headers=headers or {}, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
    raise RuntimeError(f"POST multipart failed: {url} :: {last_exc}")
