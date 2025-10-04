\
import re, json, os, hashlib
from typing import Dict, List, Tuple
import phonenumbers

PSEUDO_PATH = os.path.join(os.path.dirname(__file__), "pseudonym_map.json")

def _load_map() -> Dict[str, str]:
    if os.path.exists(PSEUDO_PATH):
        try:
            with open(PSEUDO_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_map(mapping: Dict[str, str]) -> None:
    with open(PSEUDO_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

class Pseudonymizer:
    def __init__(self):
        self.mapping: Dict[str, str] = _load_map()
        self.counters: Dict[str, int] = {}

    def get_alias(self, value: str, label: str) -> str:
        key = f"{label}:{value}"
        if key in self.mapping:
            return self.mapping[key]
        idx = self.counters.get(label, 0) + 1
        self.counters[label] = idx
        alias = f"{label.title()}_{idx}"
        self.mapping[key] = alias
        _save_map(self.mapping)
        return alias

def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

def mask(value: str) -> str:
    n = len(value)
    return "*" * max(6, min(n, 32))

WS = r"[ \t\r\n]"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IPV4_RE = re.compile(rf"\b(?:\d{{1,3}}\.){{3}}\d{{1,3}}\b")
SSN_RE = re.compile(rf"\b(?!000|666|9\d\d)\d{{3}}(?:[-{WS}]?)(?!00)\d{{2}}(?:[-{WS}]?)(?!0000)\d{{4}}\b")
DOB_ISO_RE = re.compile(rf"\b(19|20)\d{{2}}(?:[-/])(?:0[1-9]|1[0-2])(?:[-/])(?:0[1-9]|[12]\d|3[01])\b")
DOB_US_RE  = re.compile(rf"\b(?:0[1-9]|1[0-2])(?:[-/])(?:0[1-9]|[12]\d|3[01])(?:[-/])(?:19|20)\d{{2}}\b")
ADDRESS_RE = re.compile(rf"\b\d{{1,5}}{WS}+[A-Za-z]{{2,}}(?:[,\.]?{WS}+[A-Za-z]{{2,}}){{0,4}}{WS}+(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Boulevard|Blvd|Drive|Dr)\b", re.IGNORECASE)

SEP = r"[\s\u00A0\u200B-\u200D\u2060\u2212\u2010-\u2015\-]"
CC_RE = re.compile(rf"\b(?:\d(?:{SEP}?)){13,19}\b")

PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
AADHAAR_RE = re.compile(rf"\b\d{{4}}(?:{WS}?){1}\d{{4}}(?:{WS}?){1}\d{{4}}\b")

def find_cc_spans(text: str) -> List[Tuple[int,int,str]]:
    spans = []
    for m in CC_RE.finditer(text):
        spans.append((m.start(), m.end(), "CREDIT_CARD"))
    return spans

def find_phone_spans(text: str) -> List[Tuple[int,int,str]]:
    spans = []
    for m in re.finditer(rf"[+\(]?\d[\d\)\- {WS}\.]{{5,}}\d", text):
        s, e = m.start(), m.end()
        cand = text[s:e]
        try:
            for match in phonenumbers.PhoneNumberMatcher(cand, None):
                abs_s = s + match.start
                abs_e = s + match.end
                spans.append((abs_s, abs_e, "PHONE"))
        except Exception:
            pass
    return spans

def find_regex_spans(text: str, level: str="standard") -> List[Tuple[int,int,str]]:
    spans = []
    patterns = [("EMAIL", EMAIL_RE), ("IP", IPV4_RE), ("SSN", SSN_RE), ("DOB", DOB_ISO_RE), ("DOB", DOB_US_RE)]
    if level in ("standard","strict"):
        patterns += [("ADDRESS", ADDRESS_RE), ("PAN", PAN_RE), ("AADHAAR", AADHAAR_RE)]
    for name, rx in patterns:
        for m in rx.finditer(text):
            spans.append((m.start(), m.end(), name))
    return spans

LABEL_PATTERNS = [
    ("PASSPORT", r"(?i)passport(?:\s*(?:no|number))?\s*[:\-]\s*([A-Z0-9]{6,12})"),
    ("EMPLOYEE_ID", r"(?i)employee\s*id\s*[:\-]\s*([A-Za-z0-9\-]{4,20})"),
    ("MRN", r"(?i)(?:medical\s*record\s*number|MRN)\s*[:\-]\s*([A-Za-z0-9\-]{4,20})"),
    ("INSURANCE_ID", r"(?i)insurance\s*policy\s*[:\-]\s*([A-Za-z0-9\-]{4,25})"),
    ("DRIVER_LICENSE", r"(?i)driver[’']?s?\s*license\s*[:\-]\s*([A-Za-z0-9\-]{4,20})"),
    ("BANK_ACCT", r"(?i)account\s*number\s*[:\-]\s*(\d{6,20})"),
    ("ROUTING", r"(?i)routing\s*number\s*[:\-]\s*(\d{9})"),
    ("KTN", r"(?i)(?:TSA\s*PreCheck|KTN)\s*[:\-]\s*([A-Za-z0-9\-]{6,20})"),
    ("BOOKING_REF", r"(?i)flight\s*booking\s*ref(?:erence)?\s*[:\-]\s*([A-Z0-9]{5,8})"),
    ("FFN", r"(?i)frequent\s*flyer\s*(?:no|number)?\s*[:\-]\s*([A-Z0-9]{6,20})"),
    ("ADDRESS", r"(?i)address\s*[:\-]\*?[\s]*([\s\S]{5,140})"),
]

def find_label_spans(text: str) -> List[Tuple[int,int,str]]:
    spans: List[Tuple[int,int,str]] = []
    for label, pattern in LABEL_PATTERNS:
        rx = re.compile(pattern)
        for m in rx.finditer(text):
            if label == "ADDRESS":
                val = m.group(1)
                cutoff = len(val)
                for sep in ["\n\n", "\r\n\r\n"]:
                    idx = val.find(sep)
                    if idx != -1:
                        cutoff = min(cutoff, idx)
                lines = val[:cutoff].splitlines()
                trimmed = []
                for line in lines:
                    if line.strip().endswith(":"):
                        break
                    trimmed.append(line.strip())
                v = " ".join([x for x in trimmed if x])
                if v:
                    start = m.start(1)
                    end = m.start(1) + len(m.group(1))
                    inner = text[start:end]
                    inner_idx = inner.find(v)
                    if inner_idx >= 0:
                        spans.append((start+inner_idx, start+inner_idx+len(v), "ADDRESS"))
            else:
                start = m.start(1); end = m.end(1)
                spans.append((start, end, label))
    return spans

def merge_spans(spans: List[Tuple[int,int,str]]) -> List[Tuple[int,int,str]]:
    spans = sorted(spans, key=lambda x: (x[0], -(x[1]-x[0])))
    merged = []
    cur = None
    for s, e, lab in spans:
        if cur is None:
            cur = [s, e, lab]; continue
        if s <= cur[1]:
            cur[1] = max(cur[1], e)
        else:
            merged.append(tuple(cur)); cur = [s, e, lab]
    if cur: merged.append(tuple(cur))
    return merged

def redact_text(text: str, mode: str = "mask", level: str = "standard") -> Dict:
    pseudo = Pseudonymizer()
    spans = []
    spans += find_regex_spans(text, level=level)
    spans += find_phone_spans(text)
    spans += find_cc_spans(text)
    spans += find_label_spans(text)
    spans = merge_spans(spans)

    out = []; last = 0; counts: Dict[str,int] = {}
    for s, e, lab in spans:
        if s < last: continue
        out.append(text[last:s])
        chunk = text[s:e]
        rep = mask(chunk) if mode=="mask" else (short_hash(chunk) if mode=="hash" else pseudo.get_alias(chunk, lab))
        out.append(rep)
        counts[lab] = counts.get(lab, 0) + 1
        last = e
    out.append(text[last:])
    redacted = "".join(out)
    total = sum(counts.values())
    risk = "low" if total == 0 else ("medium" if total < 5 else "high")
    return {"text": redacted, "counts": counts, "residual_risk": risk}
