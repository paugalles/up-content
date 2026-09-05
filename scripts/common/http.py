import time
import requests

from .config import TIMEOUT


class Http:
    def __init__(self, session=None, attempts: int = 4):
        self.session = session or requests.Session()
        self.attempts = attempts

    def request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", TIMEOUT)
        for attempt in range(self.attempts):
            try:
                response = self.session.request(method, url, **kwargs)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    if not response.ok:
                        raise requests.exceptions.HTTPError(f"{response.status_code} Client Error: {response.reason} for url: {response.url} - Response: {response.text}", response=response)
                    return response
                if not response.ok:
                    raise requests.exceptions.HTTPError(f"{response.status_code} Client Error: {response.reason} for url: {response.url} - Response: {response.text}", response=response)
            except requests.RequestException:
                if attempt + 1 == self.attempts:
                    raise
                time.sleep(min(8, 2**attempt))
        raise RuntimeError("unreachable")

    def json(self, method: str, url: str, **kwargs):
        return self.request(method, url, **kwargs).json()
