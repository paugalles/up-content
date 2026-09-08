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
                
                # Check for Meta's 400 Generic internal error (code -1, subcode 2207085)
                # This needs to be checked BEFORE the standard 400 failure block.
                is_meta_internal_error = False
                if response.status_code == 400 and ("2207085" in response.text or "Generic internal error" in response.text):
                    is_meta_internal_error = True
                    
                if response.status_code not in {429, 500, 502, 503, 504} and not is_meta_internal_error:
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
