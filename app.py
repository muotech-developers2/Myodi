import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename

from processing.ocr import analyze_image, extract_matches_from_image, calculate_result

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.secret_key = "virtual-odds-analyzer-secret-key"

UPLOAD_FOLDER.mkdir(exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "file" not in request.files:
            return render_template("index.html", error="No file uploaded.")

        file = request.files["file"]
        if file.filename == "":
            return render_template("index.html", error="No file selected.")

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = UPLOAD_FOLDER / filename
            file.save(filepath)
            try:
                result = analyze_image(str(filepath))
                return render_template("index.html", file_name=filename, result=result)
            except Exception as exc:
                return render_template("index.html", error=f"Error processing image: {exc}")

        return render_template("index.html", error="Unsupported file type.")

    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported image format."}), 400

    filename = secure_filename(file.filename)
    filepath = UPLOAD_FOLDER / filename
    file.save(filepath)

    try:
        data = analyze_image(str(filepath))
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/recalculate", methods=["POST"])
def api_recalculate():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows", [])

    updated = []
    for row in rows:
        match = {
            "home_team": row.get("home_team", "").strip(),
            "away_team": row.get("away_team", "").strip(),
            "home_odds": float(row.get("home_odds", 0) or 0),
            "draw_odds": float(row.get("draw_odds", 0) or 0),
            "away_odds": float(row.get("away_odds", 0) or 0),
            "btts_yes": float(row.get("btts_yes", 0) or 0),
            "btts_no": float(row.get("btts_no", 0) or 0),
        }
        match["total"] = calculate_result(
            match["home_odds"],
            match["draw_odds"],
            match["away_odds"],
            match["btts_yes"],
            match["btts_no"],
        )
        updated.append(match)

    return jsonify({"rows": updated})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
