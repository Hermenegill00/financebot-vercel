from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import pytesseract, re, io, os, requests
from PIL import Image
from pdf2image import convert_from_bytes
from datetime import datetime

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

ZAPIER_URL = os.getenv("ZAPIER_WEBHOOK_URL")

# Helpers
def ocr_image(img):
    return pytesseract.image_to_string(img, lang="eng+fra")

def parse_transactions(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    txns = []
    year = None
    month_map = {m.lower(): f"{i:02d}" for i, m in enumerate(
        ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"],1)}
    month_map.update({m.lower(): f"{i:02d}" for i, m in enumerate(
        ["january","february","march","april","may","june","july","august","september","october","november","december"],1)})

    date_rx = re.compile(r'(\d{1,2})[\/\-\s](\d{1,2})(?:[\/\-\s](\d{2,4}))?')
    amount_rx = re.compile(r'(-?\d+[\.\,]\d{2})')

    pending = {}
    for l in lines:
        dm = date_rx.search(l)
        am = amount_rx.search(l.replace(',', '.'))
        if dm and am:
            d, m, y = dm.groups()
            y = y or year or datetime.now().year
            y = f"{int(y):04d}"
            mon = m.zfill(2)
            day = d.zfill(2)
            desc = l[:dm.start()].strip() or ("Unknown")
            amt = am.group(1).replace(',', '.')
            amt = float(amt)
            txns.append({
                "date": f"{y}-{mon}-{day}",
                "description": re.sub(r'\s+', ' ', desc)[:60],
                "amount": amt
            })
        else:
            # try to catch year line
            ym = re.match(r'(\w+)\s+(\d{4})', l)
            if ym:
                _, year = ym.groups()
    return txns

@app.post("/api/parse")
async def parse(file: UploadFile = File(...)):
    try:
        b = await file.read()
        images = []
        if file.filename.lower().endswith(('.png','.jpg','.jpeg','.tiff','bmp','gif')):
            images = [Image.open(io.BytesIO(b))]
        elif file.filename.lower().endswith('.pdf'):
            images = convert_from_bytes(b)
        else:
            return JSONResponse(status_code=400, content={"status":"parse-fail","file":file.filename,"reason":"Unsupported file type"})
        full_text = ""
        for img in images:
            full_text += ocr_image(img) + "\n"
        txns = parse_transactions(full_text)
        if not txns:
            return JSONResponse(status_code=200, content={"status":"parse-fail","file":file.filename,"reason":"No transactions found"})
        if ZAPIER_URL:
            try:
                requests.post(ZAPIER_URL, json=txns, timeout=5)
            except:
                pass
        return JSONResponse(status_code=200, content=txns)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status":"parse-fail","file":file.filename,"reason":str(e)})
