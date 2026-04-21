import os, uuid
from flask import Blueprint, render_template, request, jsonify, current_app, url_for
from flask_login import login_required, current_user
from models import db, ChatMessage
from datetime import timezone, timedelta

chat_bp = Blueprint("chat", __name__)

_TZ_LAO = timezone(timedelta(hours=7))
_ALLOWED = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "xlsx", "xls", "docx", "doc", "txt", "zip"}
_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


@chat_bp.route("/")
@login_required
def index():
    msgs = ChatMessage.query.order_by(ChatMessage.created_at.desc()).limit(100).all()
    msgs.reverse()
    return render_template("chat/index.html", messages=msgs, lao_tz=_TZ_LAO,
                           timezone=timezone, IMAGE_EXT=_IMAGE_EXT)


@chat_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "ບໍ່ມີໄຟລ໌"})
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in _ALLOWED:
        return jsonify({"ok": False, "error": "ປະເພດໄຟລ໌ບໍ່ຮອງຮັບ"})
    fname = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.static_folder, "uploads", "chat")
    os.makedirs(upload_dir, exist_ok=True)
    f.save(os.path.join(upload_dir, fname))
    return jsonify({
        "ok": True,
        "file_path": fname,
        "file_name": f.filename,
        "file_url": url_for("static", filename=f"uploads/chat/{fname}"),
        "is_image": ext in _IMAGE_EXT,
    })
