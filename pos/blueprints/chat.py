from flask import Blueprint, render_template
from flask_login import login_required
from models import db, ChatMessage
from datetime import timezone, timedelta

chat_bp = Blueprint("chat", __name__)

_TZ_LAO = timezone(timedelta(hours=7))


@chat_bp.route("/")
@login_required
def index():
    msgs = ChatMessage.query.order_by(ChatMessage.created_at.desc()).limit(100).all()
    msgs.reverse()
    return render_template("chat/index.html", messages=msgs, lao_tz=_TZ_LAO, timezone=timezone)
