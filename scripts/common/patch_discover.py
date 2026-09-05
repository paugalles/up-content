from urllib.parse import urlparse

def fix():
    with open('/Users/pau.galles/repos/up-content/scripts/common/articles.py', 'r') as f:
        content = f.read()

    # We want to replace the url handling logic
    old_logic = """    urls = []
    for url in locations:
        path = urlparse(url).path.lower()
        if "/blog/" not in path or path.rstrip("/").endswith("/blog"):
            continue
        
        parsed = urlparse(url)
        if parsed.path.startswith("/en/"):
            new_path = f"/{language}/" + parsed.path[4:]
            url = parsed._replace(path=new_path).geturl()
        elif parsed.path.startswith("/es/"):
            new_path = f"/{language}/" + parsed.path[4:]
            url = parsed._replace(path=new_path).geturl()
            
        urls.append(url)
    return list(set(urls))"""

    new_logic = """    urls = []
    for url in locations:
        path = urlparse(url).path.lower()
        if "/blog/" not in path or path.rstrip("/").endswith("/blog"):
            continue
        
        is_en = path.startswith("/en/")
        if language == "en" and not is_en:
            continue
        if language == "es" and is_en:
            continue
            
        urls.append(url)
    return sorted(list(set(urls)))"""
    
    content = content.replace(old_logic, new_logic)
    with open('/Users/pau.galles/repos/up-content/scripts/common/articles.py', 'w') as f:
        f.write(content)

fix()
