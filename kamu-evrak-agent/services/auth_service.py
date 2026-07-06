from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import streamlit as st


ROLE_LABELS = {
    "admin": "Admin",
    "yazi_isleri": "Yazı İşleri Personeli",
    "birim_yetkilisi": "Birim Yetkilisi",
    "onayci": "Onay Yetkilisi",
    "viewer": "Görüntüleyen Kullanıcı",
}

ROLE_PERMISSIONS = {
    "admin": {
        "can_analyze": True,
        "can_download_outputs": True,
        "can_save_archive": True,
        "can_view_archive": True,
        "can_manage_resources": True,
        "can_run_tests": True,
        "can_give_feedback": True,
        "can_view_agent_debug": True,
        "can_edit_docx_settings": True,
        "can_view_workflow": True,
        "can_manage_workflow": True,
        "can_approve_workflow": True,
    },
    "yazi_isleri": {
        "can_analyze": True,
        "can_download_outputs": True,
        "can_save_archive": True,
        "can_view_archive": True,
        "can_manage_resources": False,
        "can_run_tests": False,
        "can_give_feedback": True,
        "can_view_agent_debug": True,
        "can_edit_docx_settings": True,
        "can_view_workflow": True,
        "can_manage_workflow": True,
        "can_approve_workflow": False,
    },
    "birim_yetkilisi": {
        "can_analyze": True,
        "can_download_outputs": True,
        "can_save_archive": True,
        "can_view_archive": True,
        "can_manage_resources": False,
        "can_run_tests": False,
        "can_give_feedback": True,
        "can_view_agent_debug": False,
        "can_edit_docx_settings": False,
        "can_view_workflow": True,
        "can_manage_workflow": True,
        "can_approve_workflow": False,
    },
    "onayci": {
        "can_analyze": True,
        "can_download_outputs": True,
        "can_save_archive": True,
        "can_view_archive": True,
        "can_manage_resources": False,
        "can_run_tests": False,
        "can_give_feedback": True,
        "can_view_agent_debug": True,
        "can_edit_docx_settings": True,
        "can_view_workflow": True,
        "can_manage_workflow": True,
        "can_approve_workflow": True,
    },
    "viewer": {
        "can_analyze": False,
        "can_download_outputs": False,
        "can_save_archive": False,
        "can_view_archive": True,
        "can_manage_resources": False,
        "can_run_tests": False,
        "can_give_feedback": False,
        "can_view_agent_debug": False,
        "can_edit_docx_settings": False,
        "can_view_workflow": True,
        "can_manage_workflow": False,
        "can_approve_workflow": False,
    },
}

DEFAULT_USERS = [
    {"username": "admin", "password": "admin123", "full_name": "Sistem Yöneticisi", "role": "admin"},
    {"username": "yaziisleri", "password": "yazi123", "full_name": "Yazı İşleri Personeli", "role": "yazi_isleri"},
    {"username": "birim", "password": "birim123", "full_name": "Birim Yetkilisi", "role": "birim_yetkilisi"},
    {"username": "onayci", "password": "onay123", "full_name": "Onay Yetkilisi", "role": "onayci"},
    {"username": "viewer", "password": "viewer123", "full_name": "Görüntüleyen Kullanıcı", "role": "viewer"},
]


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def make_password_record(password: str) -> Dict[str, str]:
    salt = secrets.token_hex(16)
    return {"salt": salt, "password_hash": _hash_password(password, salt)}


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    return secrets.compare_digest(_hash_password(password, salt), password_hash)


def users_path(data_dir: Path) -> Path:
    return data_dir / "users" / "users.json"


def audit_path(outputs_dir: Path) -> Path:
    return outputs_dir / "audit_logs" / "auth_audit.jsonl"


def ensure_default_users(data_dir: Path) -> Path:
    path = users_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path

    users = []
    now = datetime.now().isoformat(timespec="seconds")
    for item in DEFAULT_USERS:
        pwd = make_password_record(item["password"])
        users.append(
            {
                "username": item["username"],
                "full_name": item["full_name"],
                "role": item["role"],
                "is_active": True,
                "created_at": now,
                **pwd,
            }
        )
    path.write_text(json.dumps({"users": users}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_users(data_dir: Path) -> Dict[str, Dict[str, Any]]:
    path = ensure_default_users(data_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    users = {}
    for item in payload.get("users", []):
        users[str(item.get("username", "")).lower()] = item
    return users


def get_permissions(role: str) -> Dict[str, bool]:
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["viewer"])


def get_role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def log_auth_event(outputs_dir: Path, action: str, username: str, status: str, detail: str = "") -> None:
    try:
        path = audit_path(outputs_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "username": username,
            "status": status,
            "detail": detail,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def authenticate(data_dir: Path, username: str, password: str) -> Optional[Dict[str, Any]]:
    users = load_users(data_dir)
    user = users.get(username.strip().lower())
    if not user or not user.get("is_active", False):
        return None
    if verify_password(password, user.get("salt", ""), user.get("password_hash", "")):
        return {
            "username": user["username"],
            "full_name": user.get("full_name", user["username"]),
            "role": user.get("role", "viewer"),
        }
    return None


def is_authenticated() -> bool:
    return bool(st.session_state.get("auth_user"))


def get_current_user() -> Dict[str, Any]:
    return st.session_state.get("auth_user", {})


def logout(outputs_dir: Optional[Path] = None) -> None:
    user = get_current_user()
    if outputs_dir and user:
        log_auth_event(outputs_dir, "logout", user.get("username", "-"), "success")
    for key in ["auth_user", "analysis_result", "matched_sources", "rag_info", "rag_warning", "routing_result", "draft_result", "llm_status", "agent_trace", "pipeline_meta", "document_text", "file_meta"]:
        st.session_state.pop(key, None)


def render_login(data_dir: Path, outputs_dir: Path) -> None:
    ensure_default_users(data_dir)
    st.markdown("### Giriş Yap")
    st.info("Demo kullanıcıları: admin/admin123, yaziisleri/yazi123, birim/birim123, onayci/onay123, viewer/viewer123")

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Kullanıcı adı", placeholder="admin")
        password = st.text_input("Şifre", type="password", placeholder="admin123")
        submitted = st.form_submit_button("Giriş Yap", type="primary", use_container_width=True)

    if submitted:
        user = authenticate(data_dir, username, password)
        if user:
            st.session_state["auth_user"] = user
            log_auth_event(outputs_dir, "login", user["username"], "success")
            st.success("Giriş başarılı. Yönlendiriliyorsun...")
            st.rerun()
        else:
            log_auth_event(outputs_dir, "login", username, "failed", "invalid_credentials")
            st.error("Kullanıcı adı veya şifre hatalı.")

    with st.expander("Rol yetkileri"):
        rows = []
        for role, perms in ROLE_PERMISSIONS.items():
            rows.append(
                {
                    "Rol": get_role_label(role),
                    "Analiz": "✓" if perms.get("can_analyze") else "-",
                    "Arşiv": "✓" if perms.get("can_view_archive") else "-",
                    "Kaynak yönetimi": "✓" if perms.get("can_manage_resources") else "-",
                    "Test paneli": "✓" if perms.get("can_run_tests") else "-",
                    "DOCX çıktı": "✓" if perms.get("can_download_outputs") else "-",
                    "İş akışı": "✓" if perms.get("can_view_workflow") else "-",
                }
            )
        st.table(rows)
