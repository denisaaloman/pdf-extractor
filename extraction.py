from __future__ import annotations

import json
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.5-flash"

INLINE_SIZE_LIMIT_BYTES = 15 * 1024 * 1024

class TableCategory(str, Enum):
    TEHNIC = "TEHNIC"
    ADMINISTRATIV = "ADMINISTRATIV"


class ExtractedTable(BaseModel):
    title: str = Field(description="Titlul exact al tabelului/listei asa cum apare in document")
    category: TableCategory = Field(
        description="TEHNIC pentru specificatii/echipamente/parametri tehnici, "
                    "ADMINISTRATIV pentru date de contract/facturare/organizatorice"
    )
    columns: list[str] = Field(description="Numele coloanelor, in ordinea din document")
    rows: list[list[str]] = Field(
        description="Fiecare rand ca lista de valori, IN ACEEASI ORDINE ca 'columns'. "
                    "Valorile lipsa se pun ca string gol '' pe pozitia respectiva, nu se omit."
    )


class ExtractionResult(BaseModel):
    tables: list[ExtractedTable]


SYSTEM_PROMPT = """\
Esti un asistent specializat in extragerea datelor structurate din documente
tehnice de constructii/inginerie in limba romana.

Sarcina ta: identifica in document TOATE tabelele si listele care contin
date tehnice sau administrative reale (specificatii de echipamente,
parametri, cantitati, coduri, date de contract etc.) si extrage-le ca JSON,
respectand exact schema ceruta.

IMPORTANT - schemele (paginile cu desene electrice, gen "SCHEMA
MONOFILARA TGD", "SCHEMA MONOFILARA TE402" etc.) contin de obicei, sub desen,
un mic tabel cu coloane. Acest
tabel TREBUIE extras ca tabel de sine statator, cu titlul exact al schemei
respective (ex: "Schema monofilara TGD - Dulap Nr. 1"), chiar daca restul
paginii e un desen/schema electrica. NU ignora aceste tabele doar pentru ca
apar langa un desen tehnic.

REGULI STRICTE DE EXCLUDERE - NU extrage:
- Cuprinsul / tabla de continut (orice lista de tip "sectiune ... pagina X")
- Anteturi/subsoluri repetate, numerotari de pagina, note de subsol generice
- Randuri complet goale sau care sunt doar separatoare vizuale
- Proza descriptiva continua (paragrafe care explica metodologie, context general,
  standarde aplicabile, mod de functionare, protectii, conditii de mediu etc.) -
  chiar daca are subtitluri sau e organizata pe puncte, daca fiecare "punct" e o
  fraza lunga explicativa si nu un item de sine statator, NU e tabel de date.

REGULI PENTRU LISTE NUMEROTATE / CU BULLET-URI (fara chenar vizibil de tabel):
- O lista numerotata (1., 2., 3....) unde FIECARE element e un item concret si
  comparabil (un echipament, un serviciu, o componenta, un livrabil - ex: "Lista
  de echipamente si servicii") SE EXTRAGE ca tabel, cu coloanele ["Nr.", "Descriere"].
- Test practic: daca ai putea pune fiecare element pe un rand de Excel si ar avea
  sens de sine statator (fara sa citesti restul listei ca sa-l intelegi) -> extrage.
  Daca elementele sunt fraze narative care explica DE CE sau CUM, legate una de
  alta prin context (ca intr-un eseu) -> nu extrage, e proza.

REGULI DE EXTRAGERE:
- Decide categoria (TEHNIC vs ADMINISTRATIV) din intelesul continutului,
  nu dupa cuvinte cheie fixe - un tabel de "Date generale contract" e
  ADMINISTRATIV, un tabel de "Parametri tehnici echipament" e TEHNIC.
- Foloseste EXACT coloanele asa cum apar in tabelul original (nu inventa,
  nu uni coloane din tabele diferite).
- Fiecare rand din "rows" trebuie sa aiba EXACT atatea valori cate coloane
  sunt in "columns", IN ACEEASI ORDINE. Daca o valoare lipseste, pune
  string gol "" pe acea pozitie - nu sari peste ea si nu decala restul.
- Cand o valoare e "Idem", "idem ca mai sus", "-„-" sau echivalent,
  rezolva-o cu valoarea reala din randul anterior din ACELASI tabel
  (documentul e complet, deci ai context din toate paginile).
- Daca un tabel continua pe mai multe pagini (acelasi titlu / cap de tabel
  repetat), trateaza-l ca UN SINGUR tabel, nu unul per pagina.
- Pastreaza diacriticele romanesti corect (ă, â, î, ș, ț).
- Cand intalnesti simbolul "÷" (semnul de impartire, folosit in tabele ca
  separator de range intre coduri/repere, ex: "M41 ÷ M46", "4.1M ÷ 4.5M"),
  inlocuieste-l cu "+" in valoarea extrasa (ex: "M41+M46", "4.1M+4.5M").

REGULA PENTRU RANDURI DE SECTIUNE (headere de grup in interiorul tabelului):
- Uneori un tabel are randuri care NU sunt date propriu-zise, ci titluri de
  grup/sectiune pentru randurile de dedesubt (ex: in "Lista de motoare",
  randul "401 - SILOZ GRAU" nu e un motor - grupeaza toate motoarele de sub
  el, pana la urmatorul titlu de sectiune "402 - PRECURATARE"). Aceste
  randuri de obicei ocupa toata latimea tabelului si nu au valori pe
  coloanele normale (Nr., Tip, Putere etc.).
- Cand intalnesti un asemenea rand: NU il adauga ca rand de sine statator.
  In schimb, adauga o coloana suplimentara "Sectiune" (ultima coloana din
  "columns", dupa cele originale), si completeaz-o cu valoarea sectiunii
  curente pentru FIECARE rand de date de sub acel titlu, pana la urmatorul
  titlu de sectiune intalnit.
- Daca tabelul nu are astfel de randuri de grupare, NU adauga coloana
  "Sectiune" deloc.

REGULA PENTRU TYPO-URI EVIDENTE (in header-e SI in valori din rows):
- Daca un cuvant de vocabular romanesc comun (nu cod de produs, nu denumire
  proprie/marca, nu abreviere tehnica, nu termen strain) contine o greseala
  de tipar EVIDENTA - litere lipsa, litere inversate, caracter corupt din
  scanare (ex: "cantitatae" -> "cantitate",
  "diametul" -> "diametrul") - corecteaza-l la forma corecta, indiferent
  daca apare intr-un nume de coloana, titlu de tabel sau valoare de rand.
  Foloseste contextul (restul tabelului) ca sa confirmi ca e intr-adevar
  o greseala si nu un termen tehnic legitim.
- NU corecta: coduri (ex: "M41", "4.1M"), denumiri de produse/firme,
  unitati de masura abreviate, termeni tehnici in alta limba, sau orice
  cuvant despre care ai dubii ca ar putea fi corect asa cum e scris in
  original. In caz de dubiu, pastreaza valoarea exact cum apare in document.
- Aceasta corectare se aplica DOAR la greseli de tipar clare, NU la
  reformulari, prescurtari alternative, sau "imbunatatiri" de exprimare
  ale textului original.

REGULA PENTRU NUMEROTARE SECVENTIALA GRESITA (coloana Nr./Nr. crt.):
- Daca tabelul are o coloana de numerotare secventiala (Nr., Nr. crt.,
  Poz., etc.) care ar trebui sa creasca cu exact 1 la fiecare rand, si
  gasesti un salt gresit (ex: ...30, 32, 33... in loc de ...30, 31, 32...
  sau o repetare/decalaj evident), corecteaza valorile din acea coloana
  ca sa respecte secventa corecta (+1 fata de randul anterior).
- Aplica asta DOAR pe coloana de numerotare in sine (Nr./Nr. crt./Poz.),
  NU pe alte coloane care contin numere cu alt sens (cantitati, coduri,
  ani, puteri etc.) - acelea raman exact cum apar in document.
- Daca nu esti sigur ca respectiva coloana e o simpla numerotare
  secventiala (si nu, de ex., un cod de pozitie cu sens propriu),
  nu corecta - pastreaza valoarea originala.

Raspunde DOAR cu JSON valid conform schemei, fara text explicativ in plus.
"""


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY lipseste din environment (verifica .env si load_dotenv())"
        )
    return genai.Client(api_key=api_key)


RETRYABLE_STATUS_CODES = {429, 500, 503, 504}
MAX_RETRIES = 5
BASE_DELAY_SECONDS = 2


def _generate_with_retry(client: genai.Client, **kwargs):
    """
    Apeleaza client.models.generate_content cu retry + backoff exponential
    pentru erori tranzitorii (model supraincarcat, rate limit etc.).
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.models.generate_content(**kwargs)
        except genai_errors.APIError as exc:
            status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            last_exc = exc
            if status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
                raise
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "Gemini a raspuns cu %s (incercarea %d/%d), reincerc peste %ds",
                status_code, attempt, MAX_RETRIES, delay,
            )
            time.sleep(delay)
    raise last_exc


def _build_pdf_part(client: genai.Client, pdf_path: Path):
    size = pdf_path.stat().st_size
    if size <= INLINE_SIZE_LIMIT_BYTES:
        return types.Part.from_bytes(
            data=pdf_path.read_bytes(), mime_type="application/pdf"
        )
    # fisiere mari: Files API - se poate pasa direct obiectul incarcat in contents
    return client.files.upload(file=str(pdf_path), config={"mime_type": "application/pdf"})


def extract_tables_from_pdf(pdf_path: str | Path, filename: Optional[str] = None) -> dict:
    """
    Extrage tabelele tehnice/administrative dintr-un PDF.
    """
    pdf_path = Path(pdf_path)
    filename = filename or pdf_path.name

    try:
        client = _get_client()
        pdf_part = _build_pdf_part(client, pdf_path)

        response = _generate_with_retry(
            client,
            model=MODEL_NAME,
            contents=[SYSTEM_PROMPT, pdf_part],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=ExtractionResult,
            ),
        )

        parsed: ExtractionResult = response.parsed
        if parsed is None:
            parsed = ExtractionResult.model_validate(json.loads(response.text))

        tables = [t.model_dump() for t in parsed.tables]

        if not tables:
            return {"filename": filename, "status": "no_tables", "tables": []}

        return {"filename": filename, "status": "success", "tables": tables}

    except Exception as exc:
        logger.exception("Extractie esuata pentru %s", filename)
        return {
            "filename": filename,
            "status": "error",
            "errorMessage": str(exc),
            "tables": [],
        }