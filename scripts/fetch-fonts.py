"""Development-only download of unmodified OFL fonts, verified against Git blobs.

The installed app bundles these files and never downloads fonts at runtime.
"""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILES=[
    ("nanumgothic/NanumGothic-Regular.ttf","NanumGothic-Regular.ttf","2aa2b20905b4136808a0126d8e36e5c0f576715c"),
    ("nanumgothic/NanumGothic-Bold.ttf","NanumGothic-Bold.ttf","79a9bdc1fa190b5786b247bb5db6a00893e620fb"),
    ("nanumgothic/OFL.txt","LICENSE-NanumGothic.txt","69ff40157d0bba4c65e4ecf77564e1f01d0b02a5"),
    ("blackhansans/BlackHanSans-Regular.ttf","BlackHanSans-Regular.ttf","e0d7584294610df5ca721096e03a5c0b1dd2894e"),
    ("blackhansans/OFL.txt","LICENSE-BlackHanSans.txt","3b9b3c49bf1734861e5fc0840e2539a33b82a92b"),
]


def main():
    target=ROOT/"assets"/"fonts";target.mkdir(parents=True,exist_ok=True)
    sources=[]
    for path,name,blob in FILES:
        url="https://raw.githubusercontent.com/google/fonts/main/ofl/"+path
        cached=target/name
        data=cached.read_bytes() if cached.exists() else urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"LocalCut-font-build/0.2"}),timeout=60).read()
        actual=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
        if actual!=blob:raise RuntimeError("Font source changed; review before updating: "+name)
        (target/name).write_bytes(data)
        sources.append({"file":name,"url":url,"gitBlob":blob,"sha256":hashlib.sha256(data).hexdigest(),"modified":False,"license":"SIL OFL 1.1"})
        print("Verified font asset:",name,len(data),"bytes")
    (target/"SOURCES.json").write_text(json.dumps(sources,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":main()
