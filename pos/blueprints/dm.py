import os, uuid
from flask import Blueprint, render_template, request, jsonify, current_app, url_for, abort
from flask_login import login_required, current_user
from models import db, DMRoom, DMRoomMember, DMMessage, Employee
from datetime import datetime, timezone, timedelta

dm_bp = Blueprint("dm", __name__)

_TZ_LAO = timezone(timedelta(hours=7))
_ALLOWED = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "xlsx", "xls", "docx", "doc", "txt", "zip"}
_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


def _to_lao(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_TZ_LAO)


def _check_member(room_id):
    if current_user.is_admin():
        return True
    return DMRoomMember.query.filter_by(room_id=room_id, employee_id=current_user.id).first() is not None


def _room_display_name(room):
    if room.is_group:
        return room.name or "ກຸ່ມ"
    other = next((m.employee for m in room.members if m.employee_id != current_user.id), None)
    return other.name if other else room.name or "ສ່ວນຕົວ"


def _room_unread(room_id):
    member = DMRoomMember.query.filter_by(room_id=room_id, employee_id=current_user.id).first()
    q = DMMessage.query.filter(
        DMMessage.room_id == room_id,
        DMMessage.deleted == False,
        DMMessage.employee_id != current_user.id,
    )
    if member and member.last_read_at:
        q = q.filter(DMMessage.created_at > member.last_read_at)
    return q.count()


@dm_bp.route("/")
@login_required
def index():
    employees = Employee.query.filter(
        Employee.active == True,
        Employee.id != current_user.id
    ).order_by(Employee.name).all()

    if current_user.is_admin():
        rooms = DMRoom.query.order_by(DMRoom.created_at.desc()).all()
    else:
        room_ids = [m.room_id for m in DMRoomMember.query.filter_by(employee_id=current_user.id).all()]
        rooms = DMRoom.query.filter(DMRoom.id.in_(room_ids)).order_by(DMRoom.created_at.desc()).all() if room_ids else []

    room_data = []
    for room in rooms:
        last_msg = DMMessage.query.filter_by(room_id=room.id, deleted=False).order_by(DMMessage.created_at.desc()).first()
        unread = _room_unread(room.id)
        room_data.append({
            "room": room,
            "display_name": _room_display_name(room),
            "last_msg": last_msg,
            "unread": unread,
        })

    room_data.sort(
        key=lambda x: _to_lao(x["last_msg"].created_at) if x["last_msg"] else datetime(1970, 1, 1, tzinfo=timezone.utc).astimezone(_TZ_LAO),
        reverse=True,
    )

    return render_template("dm/index.html", room_data=room_data, employees=employees, lao_tz=_TZ_LAO)


@dm_bp.route("/create", methods=["POST"])
@login_required
def create_room():
    is_group = request.form.get("is_group") == "1"
    member_ids = request.form.getlist("member_ids", type=int)
    group_name = request.form.get("group_name", "").strip()

    if not member_ids:
        return jsonify({"ok": False, "error": "ກະລຸນາເລືອກສະມາຊິກ"})

    # For 1-on-1: reuse existing room if it exists
    if not is_group and len(member_ids) == 1:
        other_id = member_ids[0]
        my_rooms = {m.room_id for m in DMRoomMember.query.filter_by(employee_id=current_user.id).all()}
        their_rooms = {m.room_id for m in DMRoomMember.query.filter_by(employee_id=other_id).all()}
        for rid in my_rooms & their_rooms:
            room = DMRoom.query.get(rid)
            if room and not room.is_group and len(room.members) == 2:
                return jsonify({"ok": True, "room_id": rid})

    room = DMRoom(
        name=group_name if is_group else "",
        is_group=is_group,
        created_by=current_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(room)
    db.session.flush()

    all_ids = list(set([current_user.id] + member_ids))
    for eid in all_ids:
        db.session.add(DMRoomMember(room_id=room.id, employee_id=eid))
    db.session.commit()
    return jsonify({"ok": True, "room_id": room.id})


@dm_bp.route("/room/<int:room_id>/messages")
@login_required
def room_messages(room_id):
    DMRoom.query.get_or_404(room_id)
    if not _check_member(room_id):
        abort(403)

    before_id = request.args.get("before", type=int)
    q = DMMessage.query.filter_by(room_id=room_id)
    if before_id:
        q = q.filter(DMMessage.id < before_id)
    msgs = q.order_by(DMMessage.created_at.desc()).limit(50).all()
    msgs.reverse()

    result = []
    for msg in msgs:
        ext = msg.file_path.rsplit(".", 1)[-1].lower() if msg.file_path and "." in msg.file_path else ""
        lao_dt = _to_lao(msg.created_at)
        result.append({
            "id": msg.id,
            "user_id": msg.employee_id,
            "name": msg.employee.name if msg.employee else "?",
            "message": msg.message if not msg.deleted else "",
            "deleted": msg.deleted,
            "file_url": url_for("static", filename=f"uploads/dm/{msg.file_path}") if msg.file_path and not msg.deleted else "",
            "file_name": msg.file_name if not msg.deleted else "",
            "is_image": ext in _IMAGE_EXT and not msg.deleted,
            "time": lao_dt.strftime("%H:%M") if lao_dt else "",
            "date": lao_dt.strftime("%d/%m/%Y") if lao_dt else "",
        })

    return jsonify({"ok": True, "messages": result, "has_more": len(msgs) == 50})


@dm_bp.route("/room/<int:room_id>/send", methods=["POST"])
@login_required
def send_message(room_id):
    DMRoom.query.get_or_404(room_id)
    if not _check_member(room_id):
        abort(403)

    text = (request.form.get("message") or "").strip()
    file_path = (request.form.get("file_path") or "").strip()
    file_name = (request.form.get("file_name") or "").strip()

    if not text and not file_path:
        return jsonify({"ok": False, "error": "ບໍ່ມີຂໍ້ຄວາມ"})

    msg = DMMessage(
        room_id=room_id,
        employee_id=current_user.id,
        message=text,
        file_path=file_path,
        file_name=file_name,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(msg)

    member = DMRoomMember.query.filter_by(room_id=room_id, employee_id=current_user.id).first()
    if member:
        member.last_read_at = msg.created_at

    db.session.commit()

    ext = file_path.rsplit(".", 1)[-1].lower() if file_path and "." in file_path else ""
    lao_dt = _to_lao(msg.created_at)
    msg_data = {
        "id": msg.id,
        "room_id": room_id,
        "user_id": current_user.id,
        "name": current_user.name,
        "message": text,
        "deleted": False,
        "file_url": url_for("static", filename=f"uploads/dm/{file_path}") if file_path else "",
        "file_name": file_name,
        "is_image": ext in _IMAGE_EXT,
        "time": lao_dt.strftime("%H:%M"),
        "date": lao_dt.strftime("%d/%m/%Y"),
    }

    from app import socketio
    socketio.emit("dm_message", msg_data, to=f"dm_{room_id}")

    return jsonify({"ok": True, "message": msg_data})


@dm_bp.route("/message/<int:msg_id>/delete", methods=["POST"])
@login_required
def delete_message(msg_id):
    msg = DMMessage.query.get_or_404(msg_id)
    if msg.employee_id != current_user.id and not current_user.is_admin():
        abort(403)
    msg.deleted = True
    db.session.commit()
    from app import socketio
    socketio.emit("dm_deleted", {"id": msg_id, "room_id": msg.room_id}, to=f"dm_{msg.room_id}")
    return jsonify({"ok": True})


@dm_bp.route("/room/<int:room_id>/read", methods=["POST"])
@login_required
def mark_read(room_id):
    member = DMRoomMember.query.filter_by(room_id=room_id, employee_id=current_user.id).first()
    if member:
        member.last_read_at = datetime.now(timezone.utc)
        db.session.commit()
    return jsonify({"ok": True})


@dm_bp.route("/unread")
@login_required
def unread_count():
    members = DMRoomMember.query.filter_by(employee_id=current_user.id).all()
    total = sum(_room_unread(m.room_id) for m in members)
    return jsonify({"count": total})


@dm_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "ບໍ່ມີໄຟລ໌"})
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in _ALLOWED:
        return jsonify({"ok": False, "error": "ປະເພດໄຟລ໌ບໍ່ຮອງຮັບ"})
    fname = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.static_folder, "uploads", "dm")
    os.makedirs(upload_dir, exist_ok=True)
    f.save(os.path.join(upload_dir, fname))
    return jsonify({
        "ok": True,
        "file_path": fname,
        "file_name": f.filename,
        "file_url": url_for("static", filename=f"uploads/dm/{fname}"),
        "is_image": ext in _IMAGE_EXT,
    })
