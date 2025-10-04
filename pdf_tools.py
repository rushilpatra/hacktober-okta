\
from typing import List, Dict, Any
from pypdf import PdfReader
from io import BytesIO
from PIL import Image

def extract_images(reader: PdfReader) -> List[Dict[str, Any]]:
    images = []
    for page_num, page in enumerate(reader.pages):
        resources = page.get("/Resources")
        if not resources: continue
        xobj = resources.get("/XObject")
        if not xobj: continue
        xobj = xobj.get_object()
        for name in xobj:
            try:
                obj = xobj[name].get_object()
                subtype = obj.get("/Subtype")
                if subtype != "/Image":
                    continue
                data = obj.get_data()
                width = obj.get("/Width"); height = obj.get("/Height")
                filter_ = obj.get("/Filter")
                if filter_ == "/FlateDecode":
                    img = Image.frombytes("RGB", (width, height), data)
                    out = BytesIO(); img.save(out, format="PNG")
                    images.append({"page": page_num, "name": f"img_{page_num}_{name[1:]}.png", "bytes": out.getvalue()})
                else:
                    images.append({"page": page_num, "name": f"img_{page_num}_{name[1:]}.bin", "bytes": data})
            except Exception:
                continue
    return images

def extract_text(reader: PdfReader) -> str:
    chunks = []
    for p in reader.pages:
        try: chunks.append(p.extract_text() or "")
        except Exception: pass
    return "\\n".join(chunks)
