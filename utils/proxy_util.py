import os
import tempfile
import zipfile
import shutil
from typing import Optional

def create_proxy_extension(host: str, port: str, user: str, password: str) -> Optional[str]:
    """
    Creates a temporary Chrome Extension to authenticate with the proxy.
    Returns the path to the extension directory.
    """
    if not host or not port:
        return None

    manifest_json = """{
    "version": "1.0.0",
    "manifest_version": 2,
    "name": "Proxy Auth Extension",
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "<all_urls>",
        "webRequest",
        "webRequestBlocking"
    ],
    "background": {
        "scripts": ["background.js"]
    },
    "minimum_chrome_version":"22.0.0"
}
"""

    background_js = """
var config = {
    mode: "fixed_servers",
    rules: {
      singleProxy: {
        scheme: "http",
        host: "%s",
        port: parseInt(%s)
      },
      bypassList: ["localhost"]
    }
  };

chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

function callbackFn(details) {
    return {
        authCredentials: {
            username: "%s",
            password: "%s"
        }
    };
}

chrome.webRequest.onAuthRequired.addListener(
            callbackFn,
            {urls: ["<all_urls>"]},
            ['blocking']
);
""" % (host, port, user, password)

    temp_ext_dir = tempfile.mkdtemp(prefix="proxy_ext_")
    
    with open(os.path.join(temp_ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(manifest_json)
        
    with open(os.path.join(temp_ext_dir, "background.js"), "w", encoding="utf-8") as f:
        f.write(background_js)
        
    return temp_ext_dir
