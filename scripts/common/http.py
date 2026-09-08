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
                if response.status_code not in {429, 500, 502, 503, 504, 400}:
                    if not response.ok:
                        raise requests.exceptions.HTTPError(f"{response.status_code} Client Error: {response.reason} for url: {response.url} - Response: {response.text}", response=response)
                    return response
                
                # Special handling for Meta's 400 Generic internal error (code -1, subcode 2207085)
                # It is technically a 400, but represents an internal sync issue on their end.
                if response.status_code == 400 and "2207085" not in response.text and "Generic internal error" not in response.text:
                     if not response.ok:
                        raise requests.exceptions.HTTPError(f"{response.status_code} Client Error: {response.reason} for url: {response.url} - Response: {response.text}", response=response)
                     return response
                
                if not response.ok:
                    if attempt + 1 == self.attempts:
                         raise requests.exceptions.HTTPError(f"{response.status_code} Client Error: {response.reason} for url: {response.url} - Response: {response.text}", response=response)
                    time.sleep(min(15, 3**attempt))
                    continue
                    
            except requests.RequestException:
                if attempt + 1 == self.attempts:
                    raise
                time.sleep(min(8, 2**attempt))
        raise RuntimeError("unreachable")

    def json(self, method: str, url: str, **kwargs):
        return self.request(method, url, **kwargs).json()
