import tempfile
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from extraction import extract_tables_from_pdf
from export_utils import build_csv, build_xlsx

app = FastAPI()


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(await file.read())
        tmp.close()
        result = extract_tables_from_pdf(tmp.name, filename=file.filename)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    return result


class ExportRequest(BaseModel):
    results: list[dict]
    format: str  # "xlsx" | "csv"


@app.post("/api/export")
async def export(req: ExportRequest):
    if req.format == "csv":
        data = build_csv(req.results)
        media_type = "text/csv"
        filename = "technical_tables.csv"
    else:
        data = build_xlsx(req.results)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "technical_tables.xlsx"

    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")