"""构建时准备开源字体；成品 App 不需要联网。"""
import hashlib
from pathlib import Path
import shutil
import urllib.request

ASSETS={
    "NotoSansCJKsc-Regular.otf":"2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
    "NotoSansCJKsc-Bold.otf":"b5f0d1a190a7f9b43c310a8850630af12553df32c4c050543f9059732d9b4c0a",
}
UI_ASSETS={
    'NotoSansSC-UI.ttf':('NotoSansSC%5Bwght%5D.ttf','a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da'),
    'NotoSansSC-UI-LICENSE.txt':('OFL.txt','1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9'),
}


def prepare():
    folder=Path(__file__).resolve().parent/"clinical_studio"/"assets"
    folder.mkdir(parents=True,exist_ok=True)
    sources={name:('https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/'+name,checksum) for name,checksum in ASSETS.items()}
    sources.update({name:('https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/'+remote,checksum) for name,(remote,checksum) in UI_ASSETS.items()})
    for name,(url,checksum) in sources.items():
        target=folder/name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==checksum:
            print(f"Verified font: {name}");continue
        temporary=target.with_suffix(".download")
        try:
            with urllib.request.urlopen(url,timeout=120) as response,temporary.open("wb") as output:
                shutil.copyfileobj(response,output)
            if hashlib.sha256(temporary.read_bytes()).hexdigest()!=checksum:
                raise RuntimeError(f"Font checksum mismatch: {name}")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"Prepared and verified font: {name}")


if __name__=="__main__":prepare()
