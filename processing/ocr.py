import re
import os
from difflib import SequenceMatcher
from typing import List, Dict, Any
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps, ImageFilter
from pytesseract import Output


# Configure Tesseract if available in a custom location.
# On Windows this may need to be set explicitly.
# Example: pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_odds_value(raw_value: str) -> float | None:
    value = raw_value.strip()
    value = value.replace("O", "0")
    value = value.replace("I", "1")
    value = value.replace("l", "1")
    value = value.replace("—", "-")
    value = value.replace(" ", "")

    match = re.search(r"\d+(?:[.,]\d+)?", value)
    if not match:
        return None

    candidate = match.group(0)
    if "," in candidate and "." not in candidate:
        candidate = candidate.replace(",", ".")
    if "." in candidate:
        try:
            return float(candidate)
        except ValueError:
            return None
    if len(candidate) == 3:
        try:
            return float(f"{candidate[0]}.{candidate[1:]}")
        except ValueError:
            return None
    return float(candidate)


def preprocess_image(image_path: str):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Unable to read image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return gray


def extract_text_from_image(image_path: str) -> str:
    gray = preprocess_image(image_path)
    config = "--psm 6 --oem 3"
    text = pytesseract.image_to_string(gray, config=config)
    return text


def extract_scores_from_image(image_path: str) -> List[str]:
    """Extract final scores in top-to-bottom order from a results screenshot."""
    text = extract_text_from_image(image_path)
    scores = re.findall(r"(?<!\d)(\d{1,2})\s*(?::|-)\s*(\d{1,2})(?!\d)", text)
    if not scores:
        scores = re.findall(r"(?<!\d)(\d)\s+(\d)(?!\d)", text)
    return [f"{home}:{away}" for home, away in scores]


def extract_results_from_image(image_path: str) -> List[Dict[str, str]]:
    """Extract labeled final scores so results can be matched to odds by teams."""
    text = extract_text_from_image(image_path)
    results = []
    patterns = (
        re.compile(r"^\s*(?P<home>[A-Za-z][A-Za-z .&'’/-]*?)\s+(?P<home_score>[0-9OQD]{1,2})\s*(?::|-)\s*(?P<away_score>[0-9OQD]{1,2})\s+(?P<away>[A-Za-z][A-Za-z .&'’/-]*)\s*$"),
        re.compile(r"^\s*(?P<home>[A-Za-z][A-Za-z .&'’/-]*?)\s+(?P<home_score>[0-9OQD]{1,2})\s+(?P<away_score>[0-9OQD]{1,2})\s+(?P<away>[A-Za-z][A-Za-z .&'’/-]*)\s*$"),
    )
    for line in text.splitlines():
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                def normalize_score_token(token):
                    if set(token) <= {"O", "Q", "D"}:
                        return "0"
                    return token.replace("O", "0").replace("Q", "0").replace("D", "0")

                home_score = normalize_score_token(match.group("home_score"))
                away_score = normalize_score_token(match.group("away_score"))
                results.append({
                    "home_team": clean_team_name(match.group("home")),
                    "away_team": clean_team_name(match.group("away")),
                    "score": f"{home_score}:{away_score}",
                })
                break
    return results


def teams_match(first: str, second: str) -> bool:
    first_key = re.sub(r"[^a-z0-9]", "", first.lower())
    second_key = re.sub(r"[^a-z0-9]", "", second.lower())
    if not first_key or not second_key:
        return False
    if first_key == second_key or first_key in second_key or second_key in first_key:
        return True
    first_words = re.findall(r"[a-z0-9]+", first.lower())
    second_words = re.findall(r"[a-z0-9]+", second.lower())
    if any(len(left) >= 4 and len(right) >= 4 and (left.startswith(right) or right.startswith(left)) for left in first_words for right in second_words):
        return True
    return SequenceMatcher(None, first_key, second_key).ratio() >= 0.72


def detect_match_rows(image_path: str):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Unable to read image: {image_path}")

    original = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    scale_x = original.shape[1] / resized.shape[1]
    scale_y = original.shape[0] / resized.shape[0]

    # Primary strategy: detect full text lines with OCR. This is more stable than contour-only logic for betting-table screens.
    ocr_data = pytesseract.image_to_data(resized, config="--psm 6 --oem 3", output_type=Output.DICT)
    line_groups = {}
    for i, text in enumerate(ocr_data["text"]):
        cleaned = text.strip()
        if not cleaned:
            continue
        key = (ocr_data["block_num"][i], ocr_data["par_num"][i], ocr_data["line_num"][i])
        line_groups.setdefault(key, []).append(i)

    text_rows = []
    for indices in line_groups.values():
        opts = [ocr_data["text"][idx] for idx in indices if ocr_data["text"][idx].strip()]
        line_text = " ".join(opts)
        lower = line_text.lower()
        decimals = re.findall(r"\d+[.,]\d+", line_text)
        if "vs" not in lower and "v s" not in lower and len(decimals) < 3:
            continue
        xs = [ocr_data["left"][idx] for idx in indices if ocr_data["text"][idx].strip()]
        ys = [ocr_data["top"][idx] for idx in indices if ocr_data["text"][idx].strip()]
        widths = [ocr_data["width"][idx] for idx in indices if ocr_data["text"][idx].strip()]
        heights = [ocr_data["height"][idx] for idx in indices if ocr_data["text"][idx].strip()]
        if not xs or not ys:
            continue
        x1 = int(min(xs) * scale_x)
        y1 = int(min(ys) * scale_y)
        x2 = int(max(x + w for x, w in zip(xs, widths)) * scale_x)
        y2 = int(max(y + h for y, h in zip(ys, heights)) * scale_y)
        box = (x1, y1, max(1, x2 - x1), max(1, y2 - y1))
        text_rows.append(box)

    if text_rows:
        text_rows.sort(key=lambda r: r[1])
        merged = []
        for box in text_rows:
            if not merged:
                merged.append(box)
                continue
            last = merged[-1]
            if abs(box[1] - last[1]) < 60:
                merged[-1] = (
                    min(last[0], box[0]),
                    min(last[1], box[1]),
                    max(last[0] + last[2], box[0] + box[2]) - min(last[0], box[0]),
                    max(last[1] + last[3], box[1] + box[3]) - min(last[1], box[1]),
                )
            else:
                merged.append(box)
        return merged

    # Contour fallback when OCR is not available or the screen is very stylized.
    blur = cv2.GaussianBlur(resized, (5, 5), 0)
    variants = [
        cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1],
        cv2.threshold(blur, 180, 255, cv2.THRESH_BINARY_INV)[1],
        cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10),
    ]

    candidate_rows = []
    for thresh in variants:
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < resized.shape[1] * 0.18:
                continue
            if h < 18 or h > 160:
                continue
            if w > resized.shape[1] * 0.95:
                continue
            candidate_rows.append((
                max(0, int(x * scale_x)),
                max(0, int(y * scale_y)),
                max(1, int(w * scale_x)),
                max(1, int(h * scale_y)),
            ))

    if candidate_rows:
        candidate_rows.sort(key=lambda r: r[1])
        merged = []
        for box in candidate_rows:
            if not merged:
                merged.append(box)
                continue
            last = merged[-1]
            if abs(box[1] - last[1]) < 40 and abs((box[0] + box[2]) - (last[0] + last[2])) < 200:
                merged[-1] = (
                    min(last[0], box[0]),
                    min(last[1], box[1]),
                    max(last[0] + last[2], box[0] + box[2]) - min(last[0], box[0]),
                    max(last[1] + last[3], box[1] + box[3]) - min(last[1], box[1]),
                )
            else:
                merged.append(box)
        return merged

    return []


def calculate_result(home, draw, away, yes, no):
    return home + draw + away + yes + no


def clean_team_name(name: str) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"\s+", " ", name.strip())
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r"(?i)\s+(?:vas|fat|het|rat|fet)$", "", cleaned)
    cleaned = re.sub(r"(?i)(?:\d+[A-Za-z]+|[A-Za-z]+\d+)$", "", cleaned)
    cleaned = re.sub(r"(?i)(?:\d+\s*[A-Za-z]+)$", "", cleaned)
    cleaned = re.sub(r"(?i)(?:[lI]{1,2}\d+|[lI]+)$", "", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9 .&'’/-]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_match_row(row_text: str) -> Dict[str, Any]:
    lines = [line.strip() for line in row_text.splitlines() if line.strip()]
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()

    match = re.search(
        r"(?P<home>[A-Za-z][A-Za-z0-9 .&'’/-]*)\s+(?:vs|v s)\s*(?P<away>[A-Za-z][A-Za-z .&'’/-]*?)(?=\s+\d)",
        text,
        re.IGNORECASE,
    )
    if match:
        home = match.group("home").strip()
        away = match.group("away").strip()
        odds_text = text[match.end():]
    else:
        number_matches = list(re.finditer(r"\d+(?:[.,]\d+)?", text))
        odds_values = []
        for m in number_matches:
            num = normalize_odds_value(m.group(0))
            if num is not None and 1.0 <= num <= 20.0:
                odds_values.append((m.start(), m.group(0), num))

        if not odds_values:
            return {
                "home_team": "",
                "away_team": "",
                "home_odds": None,
                "draw_odds": None,
                "away_odds": None,
                "btts_yes": None,
                "btts_no": None,
                "confidence": "low",
                "raw_text": row_text,
            }

        first_odd_start = odds_values[0][0]
        prefix = text[:first_odd_start].strip()
        odds_text = text[first_odd_start:]

        prefix_lines = lines
        away = ""
        home_tokens = []
        noise = {
            "p", "i", "v", "s", "n", "m", "t", "c", "e", "g", "r", "u", "d", "x", "y", "z",
            "sl", "os", "ee", "nn", "tse", "bine", "iv", "way", "tye", "ves", "yes", "mo", "no",
        }
        if prefix_lines:
            odds_line = prefix_lines[-1]
            odds_line_words = re.split(r"\d", odds_line, maxsplit=1)[0]
            away_tokens = [
                word for word in re.findall(r"[A-Za-z]+", odds_line_words)
                if len(word) >= 2 and word.lower() not in noise
            ]
            if away_tokens:
                away = " ".join(away_tokens)

            first_line_words = prefix_lines[0]
            first_tokens = [
                word for word in re.findall(r"[A-Za-z]+", first_line_words)
                if len(word) >= 2 and word.lower() not in noise
            ]
            if first_tokens:
                home_tokens = first_tokens[:2]

            last_line = prefix_lines[-1]
            last_words = [w for w in re.findall(r"[A-Za-z]+", last_line) if len(w) >= 2]
            last_words = [w for w in last_words if w.lower() not in noise]
            if not away and last_words:
                away = last_words[-1]
            if not home_tokens:
                home_source = " ".join(prefix_lines[:-1])
                home_tokens = [w for w in re.findall(r"[A-Za-z]+", home_source) if len(w) >= 2 and w.lower() not in noise]

            if home_tokens:
                if home_tokens[-1].lower() in noise:
                    home_tokens.pop()
                home = " ".join(home_tokens) if not away else " ".join(home_tokens)
            else:
                home = ""

    home = clean_team_name(home)
    away = clean_team_name(away)

    if not home and not away:
        row_words = [w for w in re.findall(r"[A-Za-z]+", text) if len(w) >= 2]
        if len(row_words) >= 2:
            away = row_words[-1]
            home = " ".join(row_words[:-1])

    odds_candidates = re.findall(r"(?<![A-Za-z])\d+(?:[.,]\d+)?", odds_text)
    cleaned_odds = []
    for val in odds_candidates:
        num = normalize_odds_value(val)
        if num is not None and 1.0 <= num <= 20.0:
            cleaned_odds.append(num)

    unique = []
    seen = set()
    for num in cleaned_odds:
        key = round(num, 2)
        if key not in seen:
            unique.append(float(key))
            seen.add(key)

    selected = unique[-5:] if len(unique) >= 5 else unique
    if len(selected) < 5:
        return {
            "home_team": home,
            "away_team": away,
            "home_odds": None,
            "draw_odds": None,
            "away_odds": None,
            "btts_yes": None,
            "btts_no": None,
            "confidence": "low",
            "raw_text": row_text,
        }

    return {
        "home_team": home,
        "away_team": away,
        "home_odds": selected[0],
        "draw_odds": selected[1],
        "away_odds": selected[2],
        "btts_yes": selected[3],
        "btts_no": selected[4],
        "confidence": "medium",
        "raw_text": row_text,
    }


def extract_matches_from_image(image_path: str) -> List[Dict[str, Any]]:
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Unable to read image: {image_path}")

    rows = detect_match_rows(image_path)
    if not rows:
        return []

    matches = []
    for x, y, w, h in rows:
        margin = 24
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(image.shape[1], x + w + margin)
        y2 = min(image.shape[0], y + h + margin)
        roi = image[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        text = pytesseract.image_to_string(gray, config="--psm 6 --oem 3")
        if not text.strip():
            continue
        match = parse_match_row(text)
        if match.get("home_team") and match.get("away_team"):
            matches.append(match)

    for match in matches:
        result = [
            match.get("home_odds"),
            match.get("draw_odds"),
            match.get("away_odds"),
            match.get("btts_yes"),
            match.get("btts_no"),
        ]
        valid = all(v is not None for v in result)
        if valid:
            match["total"] = calculate_result(*result)
        else:
            match["total"] = None

    return matches


def analyze_image(image_path: str, results_image_path: str | None = None) -> Dict[str, Any]:
    extracted = extract_matches_from_image(image_path)
    extracted_results = []
    if results_image_path:
        extracted_results = extract_results_from_image(results_image_path)

    rows = []
    for idx, match in enumerate(extracted, start=1):
        cleaned = {
            "id": idx,
            "home_team": match.get("home_team", "Unknown").strip(),
            "away_team": match.get("away_team", "Unknown").strip(),
            "home_odds": match.get("home_odds"),
            "draw_odds": match.get("draw_odds"),
            "away_odds": match.get("away_odds"),
            "btts_yes": match.get("btts_yes"),
            "btts_no": match.get("btts_no"),
            "total": match.get("total"),
            "result_score": next(
                (
                    result["score"]
                    for result in extracted_results
                    if teams_match(match.get("home_team", ""), result["home_team"])
                    and teams_match(match.get("away_team", ""), result["away_team"])
                ),
                None,
            ),
            "confidence": match.get("confidence", "low"),
            "raw_text": match.get("raw_text", ""),
        }
        rows.append(cleaned)

    return {
        "matches": rows,
        "row_count": len(rows),
        "result_score_count": len(extracted_results),
        "message": f"Detected {len(rows)} match rows.",
    }
