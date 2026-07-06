import streamlit as st
from pathlib import Path
import json
import os

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env", override=True)
except Exception:
    pass

from services.text_extractor import extract_text_from_uploaded_file
from services.cleaner import clean_text
from services.rag_service import LocalRAGService
from services.vector_rag_service import VectorRAGService
from services.document_analyzer import analyze_document
from services.analysis_utils import merge_llm_with_rule_analysis, document_debug_info
from services.routing_service import recommend_unit
from services.draft_generator import generate_official_draft, build_download_text
from services.llm_agent import analyze_and_draft_with_openai, analyze_and_draft_with_openrouter
from services.docx_exporter import build_official_docx_bytes
from services.case_archive import build_case_json_bytes, save_case_json
from services.archive_manager import (
    archive_stats,
    build_case_json_bytes as build_archived_case_json_bytes,
    build_cases_csv_bytes,
    build_cases_zip,
    delete_case_record,
    filter_case_records,
    list_case_records,
    read_case_payload,
)
from services.feedback_store import save_feedback, build_feedback_jsonl_bytes
from services.agent_pipeline import run_multi_agent_pipeline
from services.resource_manager import (
    RESOURCE_CATEGORIES,
    build_resources_zip,
    clear_vector_store,
    count_resources_by_category,
    delete_resource,
    list_resources,
    read_resource,
    save_resource,
)

from services.demo_packager import (
    build_demo_checklist_markdown,
    build_demo_markdown,
    build_demo_package_zip,
    build_project_snapshot,
)

from services.evaluation_manager import (
    aggregate_metrics,
    build_evaluation_csv_bytes,
    build_evaluation_json_bytes,
    build_evaluation_markdown,
    build_evaluation_payload,
    delete_test_case,
    evaluate_single_result,
    load_test_cases,
    save_evaluation_report,
    save_test_case,
)

from services.auth_service import (
    get_current_user,
    get_permissions,
    get_role_label,
    is_authenticated,
    logout,
    render_login,
)
from services.db_service import (
    build_db_export_zip,
    db_stats,
    init_database,
    list_analysis_runs,
    list_audit_events,
    list_feedback_records,
    log_event,
    save_analysis_run,
    save_archive_reference,
    save_feedback_record,
    save_resource_event,
)

from services.workflow_manager import (
    WORKFLOW_STATUSES,
    allowed_next_statuses,
    build_workflow_csv_bytes,
    build_workflow_zip,
    create_workflow_case,
    delete_workflow_case,
    filter_workflow_cases,
    get_workflow_case,
    list_workflow_cases,
    update_workflow_draft,
    update_workflow_status,
    workflow_stats,
)

DATA_DIR = BASE_DIR / "data"
VECTOR_STORE_DIR = BASE_DIR / "vector_store"
OUTPUTS_DIR = BASE_DIR / "outputs"

st.set_page_config(
    page_title="Kamu Evrak Agent Sistemi",
    page_icon="📄",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main-title {
        font-size: 34px;
        font-weight: 800;
        margin-bottom: 0px;
    }
    .sub-title {
        color: #666;
        font-size: 16px;
        margin-top: 4px;
        margin-bottom: 24px;
    }
    .result-card {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 16px;
        background: #fafafa;
        margin-bottom: 12px;
    }
    .small-muted {
        color: #666;
        font-size: 13px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-title">Kamu Evrak ve Yazışma Agent Sistemi — MVP-15</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Evrakı analiz eder, ilgili kaynaklarla eşleştirir, birim yönlendirmesi ve resmî yazı taslağı önerir.</div>',
    unsafe_allow_html=True,
)

if not is_authenticated():
    render_login(DATA_DIR, OUTPUTS_DIR)
    st.stop()

current_user = get_current_user()
permissions = get_permissions(current_user.get("role", "viewer"))
DB_PATH = init_database(BASE_DIR)
if not st.session_state.get("db_session_logged"):
    log_event(BASE_DIR, current_user.get("username", "-"), current_user.get("role", "-"), "session_opened", "success", "Streamlit session initialized")
    st.session_state["db_session_logged"] = True

with st.sidebar:
    st.header("Oturum")
    st.success(f"{current_user.get('full_name', '-')}\n\nRol: {get_role_label(current_user.get('role', '-'))}")
    if st.button("Çıkış Yap", use_container_width=True):
        logout(OUTPUTS_DIR)
        st.rerun()

    st.divider()
    st.header("Ayarlar")

    # Kullanıcı arayüzünü sade tutmak için teknik seçimler arka planda sabitlendi.
    # Varsayılan motor: OpenRouter LLM Agent + Embedding RAG.
    scenario = os.getenv("DEFAULT_SCENARIO", "Belediye")
    analysis_mode = os.getenv("DEFAULT_ANALYSIS_MODE", "Hızlı analiz")
    llm_mode = "OpenRouter LLM Agent"
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    openrouter_model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    draft_type_preference = os.getenv("DEFAULT_DRAFT_TYPE", "Otomatik seç")

    # RAG kaynakları her zaman aktif çalışır.
    use_regulations = True
    use_templates = True
    use_units = True
    top_k = int(os.getenv("RAG_TOP_K", "5"))
    rag_mode = os.getenv("RAG_MODE", "Embedding RAG")
    force_rebuild_index = os.getenv("FORCE_REBUILD_INDEX", "false").lower() in {"1", "true", "yes", "evet"}

    # Yönetim panelleri rol bazlı gösterilir. Teknik analiz/RAG seçimleri arka planda sabit kalır.
    show_resource_panel = False
    show_archive_panel = False
    show_evaluation_panel = False
    show_database_panel = False
    show_workflow_panel = False
    show_final_demo_panel = False

    st.subheader("Paneller")
    if permissions.get("can_manage_resources"):
        show_resource_panel = st.checkbox("Kaynak yönetimi panelini göster", value=False)
    if permissions.get("can_view_archive"):
        show_archive_panel = st.checkbox("Arşiv / geçmiş panelini göster", value=False)
    if permissions.get("can_view_workflow"):
        show_workflow_panel = st.checkbox("İş akışı / onay panelini göster", value=True)
    if permissions.get("can_run_tests"):
        show_evaluation_panel = st.checkbox("Test / değerlendirme panelini göster", value=False)
    if current_user.get("role") == "admin":
        show_database_panel = st.checkbox("Veritabanı panelini göster", value=False)

    if permissions.get("can_edit_docx_settings"):
        st.subheader("DOCX çıktı ayarları")
        institution_name = st.text_input("Kurum adı", value=os.getenv("INSTITUTION_NAME", "ÖRNEK BELEDİYESİ"))
        unit_name = st.text_input("Yazıyı hazırlayan birim", value=os.getenv("PREPARING_UNIT", "Yazı İşleri Müdürlüğü"))
        signer_name = st.text_input("İmza adı", value=os.getenv("SIGNER_NAME", "Yetkili Personel"))
        signer_title = st.text_input("İmza unvanı", value=os.getenv("SIGNER_TITLE", "Birim Yetkilisi"))
        document_number = st.text_input("Sayı", value=os.getenv("DOCUMENT_NUMBER", "E-00000000-000-000000"))
        include_analysis_appendix = st.checkbox("DOCX içine analiz ekini ekle", value=True)
    else:
        institution_name = os.getenv("INSTITUTION_NAME", "ÖRNEK BELEDİYESİ")
        unit_name = os.getenv("PREPARING_UNIT", "Yazı İşleri Müdürlüğü")
        signer_name = os.getenv("SIGNER_NAME", "Yetkili Personel")
        signer_title = os.getenv("SIGNER_TITLE", "Birim Yetkilisi")
        document_number = os.getenv("DOCUMENT_NUMBER", "E-00000000-000-000000")
        include_analysis_appendix = True


def render_resource_management_panel() -> None:
    """RAG kaynaklarını arayüzden yönetmek için basit admin paneli."""
    st.subheader("Kaynak Yönetimi Paneli")
    st.write(
        "Bu panelden RAG sisteminin kullandığı mevzuat, yazı şablonu ve birim görev tanımı kaynaklarını ekleyebilir, "
        "düzenleyebilir veya silebilirsin. Yeni kaynak ekledikten sonra bir sonraki analizde sol menüden "
        "vektör indexini yenile."
    )

    counts = count_resources_by_category(DATA_DIR)
    metric_cols = st.columns(len(counts))
    for col, (category, count) in zip(metric_cols, counts.items()):
        col.metric(category, count)

    st.divider()
    add_tab, edit_tab, list_tab, maintenance_tab = st.tabs([
        "Kaynak Ekle",
        "Kaynak Düzenle / Sil",
        "Kaynak Listesi",
        "Bakım / Dışa Aktar",
    ])

    with add_tab:
        st.markdown("#### Yeni RAG Kaynağı Ekle")
        add_col1, add_col2 = st.columns([0.35, 0.65])
        with add_col1:
            new_category = st.selectbox("Kaynak kategorisi", list(RESOURCE_CATEGORIES.keys()), key="new_resource_category")
            new_title = st.text_input("Kaynak başlığı", placeholder="Örn. Fen İşleri Görev Tanımı 2026")
            st.caption(RESOURCE_CATEGORIES[new_category]["description"])
            uploaded_resource = st.file_uploader(
                "Kaynak dosyası yükle: TXT, DOCX veya PDF",
                type=["txt", "docx", "pdf"],
                key="resource_upload",
            )
        with add_col2:
            default_content = ""
            if uploaded_resource is not None and st.button("Yüklenen Kaynak Metnini Al", use_container_width=True):
                try:
                    extracted_resource_text, _ = extract_text_from_uploaded_file(uploaded_resource)
                    st.session_state["new_resource_content"] = clean_text(extracted_resource_text)
                    if not st.session_state.get("new_resource_title"):
                        st.session_state["new_resource_title"] = Path(uploaded_resource.name).stem
                    st.success("Kaynak metni alındı. Kaydetmeden önce düzenleyebilirsin.")
                except Exception as exc:
                    st.error(f"Kaynak dosyası okunamadı: {exc}")
            default_content = st.session_state.get("new_resource_content", "")
            new_content = st.text_area(
                "Kaynak içeriği",
                value=default_content,
                height=260,
                placeholder="Buraya yönetmelik, şablon veya görev tanımı metnini yaz/yapıştır.",
                key="new_resource_content_area",
            )
            overwrite = st.checkbox("Aynı isim varsa üzerine yaz", value=False)
            if st.button("Kaynağı Kaydet", type="primary", use_container_width=True):
                title_to_save = new_title.strip() or st.session_state.get("new_resource_title", "") or "yeni_kaynak"
                try:
                    saved_path = save_resource(
                        DATA_DIR,
                        new_category,
                        title_to_save,
                        new_content,
                        overwrite=overwrite,
                    )
                    st.success(f"Kaynak kaydedildi: {saved_path.relative_to(BASE_DIR)}")
                    save_resource_event(BASE_DIR, current_user.get("username", "-"), "resource_created", new_category, title_to_save, str(saved_path.relative_to(BASE_DIR)))
                    st.info("Embedding RAG kullanıyorsan bir sonraki analizde 'Vektör indexi yeniden oluştur' seçeneğini işaretle.")
                except Exception as exc:
                    st.error(f"Kaynak kaydedilemedi: {exc}")

    with edit_tab:
        st.markdown("#### Mevcut Kaynağı Aç / Düzenle / Sil")
        resources = list_resources(DATA_DIR)
        if not resources:
            st.info("Henüz kaynak dosyası bulunamadı.")
        else:
            labels = [f"{r.category} / {r.file_name}" for r in resources]
            selected_label = st.selectbox("Kaynak seç", labels, key="selected_resource_label")
            selected = resources[labels.index(selected_label)]
            st.caption(f"Dosya: {selected.path.relative_to(BASE_DIR)} | Boyut: {selected.size_bytes} bayt | Güncelleme: {selected.modified_at}")
            selected_text = read_resource(DATA_DIR, selected.category, selected.file_name)
            edited_text = st.text_area("Kaynak metni", value=selected_text, height=340, key="edited_resource_text")
            e1, e2 = st.columns(2)
            with e1:
                if st.button("Değişiklikleri Kaydet", type="primary", use_container_width=True):
                    try:
                        save_resource(
                            DATA_DIR,
                            selected.category,
                            selected.file_name,
                            edited_text,
                            overwrite=True,
                            file_name=selected.file_name,
                        )
                        st.success("Kaynak güncellendi.")
                        save_resource_event(BASE_DIR, current_user.get("username", "-"), "resource_updated", selected.category, selected.file_name, str(selected.path.relative_to(BASE_DIR)))
                        st.info("Embedding RAG için vektör indexini yeniden oluşturmayı unutma.")
                    except Exception as exc:
                        st.error(f"Kaynak güncellenemedi: {exc}")
            with e2:
                confirm_delete = st.checkbox("Silme işlemini onaylıyorum", key="confirm_resource_delete")
                if st.button("Kaynağı Sil", use_container_width=True, disabled=not confirm_delete):
                    try:
                        moved_path = delete_resource(DATA_DIR, selected.category, selected.file_name, trash_dir=OUTPUTS_DIR / "deleted_resources")
                        st.warning(f"Kaynak silindi ve yedeğe taşındı: {moved_path.relative_to(BASE_DIR)}")
                        save_resource_event(BASE_DIR, current_user.get("username", "-"), "resource_deleted", selected.category, selected.file_name, str(moved_path.relative_to(BASE_DIR)))
                        st.info("Sayfayı yenileyerek listeyi güncelleyebilirsin.")
                    except Exception as exc:
                        st.error(f"Kaynak silinemedi: {exc}")

    with list_tab:
        st.markdown("#### RAG Kaynak Envanteri")
        resources = list_resources(DATA_DIR)
        if resources:
            table_rows = [r.to_dict() for r in resources]
            st.dataframe(table_rows, use_container_width=True, hide_index=True)
            with st.expander("Kaynak Ön İzlemeleri"):
                for r in resources:
                    st.markdown(f"**{r.category} / {r.file_name}**")
                    st.caption(r.preview or "Ön izleme yok.")
        else:
            st.info("Kaynak listesi boş.")

    with maintenance_tab:
        st.markdown("#### Bakım ve Dışa Aktarma")
        m1, m2 = st.columns(2)
        with m1:
            st.download_button(
                "Tüm RAG Kaynaklarını ZIP Olarak İndir",
                data=build_resources_zip(DATA_DIR),
                file_name="rag_kaynaklari.zip",
                mime="application/zip",
                use_container_width=True,
            )
        with m2:
            st.write("Vektör index temizliği, yeni/yenilenmiş kaynakların embedding tarafında yeniden işlenmesi için kullanılır.")
            if st.button("Vektör Store Temizle", use_container_width=True):
                try:
                    removed_count = clear_vector_store(VECTOR_STORE_DIR)
                    st.success(f"Vektör store temizlendi. Silinen öğe: {removed_count}")
                    save_resource_event(BASE_DIR, current_user.get("username", "-"), "vector_store_cleared", detail=f"removed={removed_count}")
                    st.info("Bir sonraki analizde Embedding RAG seçiliyse index yeniden oluşturulacaktır.")
                except Exception as exc:
                    st.error(f"Vektör store temizlenemedi: {exc}")


def render_archive_panel() -> None:
    """Önceki analiz kayıtlarını aramak, açmak ve dışa aktarmak için arşiv paneli."""
    st.subheader("Evrak Geçmişi ve Arşiv Paneli")
    st.write(
        "Bu panel daha önce **Bu Analizi Yerel Arşive Kaydet** butonuyla kaydedilen analizleri gösterir. "
        "Kayıtlar `outputs/cases/` klasöründe JSON olarak tutulur. Buradan arama yapabilir, eski taslağı açabilir, "
        "JSON/DOCX/CSV/ZIP çıktısı alabilir veya kaydı yedeğe taşıyarak silebilirsin."
    )

    records = list_case_records(OUTPUTS_DIR)
    stats = archive_stats(records)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Toplam kayıt", stats["total"])
    m2.metric("Evrak türü", stats["document_type_count"])
    m3.metric("Birim", stats["unit_count"])
    m4.metric("Son kayıt", stats["last_created_at"])

    if not records:
        st.info("Henüz arşiv kaydı yok. Bir analiz çalıştırıp 'Bu Analizi Yerel Arşive Kaydet' butonuna basınca burada görünecek.")
        return

    st.divider()
    st.markdown("#### Arama ve Filtreleme")
    f1, f2, f3, f4 = st.columns([0.34, 0.22, 0.22, 0.22])
    with f1:
        query = st.text_input("Arama", placeholder="Konu, özet, kişi, birim, dosya adı, evrak metni...")
    with f2:
        type_options = sorted({r.document_type for r in records if r.document_type})
        selected_types = st.multiselect("Evrak türü", type_options)
    with f3:
        unit_options = sorted({r.recommended_unit for r in records if r.recommended_unit})
        selected_units = st.multiselect("Birim", unit_options)
    with f4:
        risk_options = sorted({r.risk_level for r in records if r.risk_level})
        selected_risks = st.multiselect("Risk", risk_options)

    filtered = filter_case_records(
        OUTPUTS_DIR,
        records,
        query=query,
        document_types=selected_types,
        units=selected_units,
        risk_levels=selected_risks,
    )

    st.caption(f"Gösterilen kayıt: {len(filtered)} / {len(records)}")
    st.dataframe([r.to_dict() for r in filtered], use_container_width=True, hide_index=True)

    st.markdown("#### Arşiv Dışa Aktar")
    ex1, ex2 = st.columns(2)
    with ex1:
        st.download_button(
            "Filtrelenen Kayıtları CSV İndir",
            data=build_cases_csv_bytes(filtered),
            file_name="evrak_arsiv_indeksi.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with ex2:
        st.download_button(
            "Filtrelenen Kayıtları ZIP İndir",
            data=build_cases_zip(OUTPUTS_DIR, filtered),
            file_name="evrak_arsiv_kayitlari.zip",
            mime="application/zip",
            use_container_width=True,
        )

    if not filtered:
        st.warning("Filtrelere uygun arşiv kaydı bulunamadı.")
        return

    st.divider()
    st.markdown("#### Kayıt Aç")
    labels = [f"{r.created_at} | {r.document_type} | {r.recommended_unit} | {r.source_file} | {r.file_name}" for r in filtered]
    selected_label = st.selectbox("Açılacak arşiv kaydı", labels)
    selected_record = filtered[labels.index(selected_label)]
    payload = read_case_payload(OUTPUTS_DIR, selected_record.file_name)

    analysis = payload.get("analysis") or {}
    routing = payload.get("routing") or {}
    draft = payload.get("draft") or {}
    sources = payload.get("sources") or []
    file_meta = payload.get("file_meta") or {}

    a1, a2, a3 = st.columns(3)
    a1.metric("Evrak türü", analysis.get("document_type", "-"))
    a2.metric("Birim", routing.get("recommended_unit", "-"))
    a3.metric("Risk", analysis.get("risk_level", "-"))
    st.info(analysis.get("summary", "Özet bulunamadı."))

    case_tabs = st.tabs(["Taslak", "Analiz", "Kaynaklar", "Ham JSON", "Sil"])
    with case_tabs[0]:
        st.write(f"**Kaynak dosya:** {file_meta.get('file_name', '-')}")
        st.write(f"**Yazı türü:** {draft.get('draft_type', '-')}")
        st.write(f"**Konu:** {draft.get('subject', '-')}")
        st.text_area("Arşivlenmiş taslak metni", value=draft.get("body", ""), height=260, disabled=True)

        docx_bytes = build_official_docx_bytes(
            analysis=analysis,
            routing=routing,
            draft=draft,
            sources=sources,
            institution_name=institution_name,
            unit_name=unit_name,
            signer_name=signer_name,
            signer_title=signer_title,
            document_number=document_number,
            include_analysis_appendix=include_analysis_appendix,
        )
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "Bu Kaydı DOCX Olarak İndir",
                data=docx_bytes,
                file_name=f"{selected_record.path.stem}_taslak.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                "Bu Kaydı JSON Olarak İndir",
                data=build_archived_case_json_bytes(payload),
                file_name=selected_record.file_name,
                mime="application/json",
                use_container_width=True,
            )

    with case_tabs[1]:
        st.markdown("**Çıkarılan alanlar**")
        st.json(analysis.get("extracted_fields", {}), expanded=True)
        st.markdown("**Eksik bilgiler**")
        missing = analysis.get("missing_information") or []
        if missing:
            for item in missing:
                st.write(f"- {item}")
        else:
            st.success("Kayıtta belirgin eksik bilgi yok.")
        st.markdown("**Yönlendirme gerekçesi**")
        st.write(routing.get("reason", "-"))

    with case_tabs[2]:
        if sources:
            for i, src in enumerate(sources, start=1):
                score_percent = max(0, min(100, int(src.get("score", 0) * 100)))
                with st.expander(f"{i}. {src.get('title', '-')} — %{score_percent}"):
                    st.write(src.get("content", ""))
                    st.caption(f"Tür: {src.get('source_type', '-')} | Dosya: {src.get('file_name', '-')}")
        else:
            st.info("Bu kayıtta kaynak bilgisi yok.")

    with case_tabs[3]:
        st.json(payload, expanded=False)

    with case_tabs[4]:
        st.warning("Silme işlemi kaydı tamamen yok etmez; `outputs/deleted_cases/` klasörüne yedek olarak taşır.")
        confirm = st.checkbox("Bu arşiv kaydını silmeyi onaylıyorum", key=f"delete_case_{selected_record.file_name}")
        if st.button("Seçili Arşiv Kaydını Sil", disabled=not confirm, use_container_width=True):
            moved_path = delete_case_record(OUTPUTS_DIR, selected_record.file_name)
            st.warning(f"Kayıt yedeğe taşındı: {moved_path}")
            st.info("Listeyi güncellemek için sayfayı yenileyebilirsin.")





def render_workflow_panel() -> None:
    """EBYS benzeri iş akışı ve onay paneli."""
    st.subheader("İş Akışı ve Onay Paneli")
    st.write(
        "Bu panel, analiz edilen evrakların EBYS benzeri durumlar arasında ilerlemesini sağlar. "
        "Yazı İşleri yönlendirme yapar, birim yetkilisi inceleme notu girer, onay yetkilisi taslağı onaylar veya revizyona gönderir."
    )

    role = current_user.get("role", "viewer")
    username = current_user.get("username", "-")
    items = list_workflow_cases(OUTPUTS_DIR, role=role, username=username)
    stats = workflow_stats(items)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Toplam iş", stats.get("total", 0))
    m2.metric("Onay bekleyen", stats.get("waiting_approval", 0))
    m3.metric("Birimde", stats.get("in_unit_review", 0))
    m4.metric("Onaylandı", stats.get("approved", 0))
    m5.metric("Arşivlendi", stats.get("archived", 0))

    if not items:
        st.info("Henüz iş akışı kaydı yok. Bir evrak analizinden sonra 'İş Akışına Gönder / Onaya Al' butonunu kullanabilirsin.")
        return

    st.markdown("#### Arama ve Filtreleme")
    f1, f2, f3, f4 = st.columns([0.34, 0.22, 0.22, 0.22])
    with f1:
        query = st.text_input("İş akışı arama", placeholder="Konu, özet, birim, durum, kullanıcı...")
    with f2:
        selected_statuses = st.multiselect("Durum", sorted({i.get("status", "-") for i in items}))
    with f3:
        selected_units = st.multiselect("Birim", sorted({i.get("assigned_unit", "-") for i in items}))
    with f4:
        selected_priorities = st.multiselect("Öncelik", sorted({i.get("priority", "Normal") for i in items}))

    filtered = filter_workflow_cases(
        items,
        query=query,
        statuses=selected_statuses,
        units=selected_units,
        priorities=selected_priorities,
    )

    st.caption(f"Gösterilen iş: {len(filtered)} / {len(items)}")
    table_rows = [
        {
            "workflow_id": i.get("workflow_id"),
            "status": i.get("status"),
            "priority": i.get("priority"),
            "assigned_unit": i.get("assigned_unit"),
            "document_type": i.get("document_type"),
            "subject": i.get("subject"),
            "created_by": i.get("created_by"),
            "updated_at": i.get("updated_at"),
        }
        for i in filtered
    ]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    ex1, ex2 = st.columns(2)
    with ex1:
        st.download_button(
            "İş Akışı CSV İndir",
            data=build_workflow_csv_bytes(filtered),
            file_name="is_akisi_indeksi.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with ex2:
        st.download_button(
            "İş Akışı ZIP Yedek İndir",
            data=build_workflow_zip(OUTPUTS_DIR, filtered),
            file_name="is_akisi_yedek.zip",
            mime="application/zip",
            use_container_width=True,
        )

    if not filtered:
        st.warning("Filtrelere uygun iş kaydı bulunamadı.")
        return

    st.divider()
    st.markdown("#### İş Kaydı Aç")
    labels = [f"{i.get('updated_at')} | {i.get('status')} | {i.get('assigned_unit')} | {i.get('subject')} | {i.get('workflow_id')}" for i in filtered]
    selected_label = st.selectbox("Açılacak iş", labels, key="workflow_selected_item")
    selected = filtered[labels.index(selected_label)]
    workflow_id = selected.get("workflow_id")
    payload = get_workflow_case(OUTPUTS_DIR, workflow_id) or selected

    st.markdown(f"### {payload.get('subject', '-')}")
    w1, w2, w3, w4 = st.columns(4)
    w1.metric("Durum", payload.get("status", "-"))
    w2.metric("Birim", payload.get("assigned_unit", "-"))
    w3.metric("Öncelik", payload.get("priority", "Normal"))
    w4.metric("Risk", payload.get("risk_level", "-"))
    st.info(payload.get("summary", "Özet bulunamadı."))

    flow_tabs = st.tabs(["İşlem", "Taslak", "Analiz", "Geçmiş", "Ham JSON", "Sil"])

    with flow_tabs[0]:
        st.markdown("#### Durum Güncelle")
        current_status = payload.get("status", "")
        next_statuses = allowed_next_statuses(current_status, role)
        if not permissions.get("can_manage_workflow"):
            st.info("Bu rol iş akışı güncellemesi yapamaz; kayıtları yalnızca görüntüleyebilir.")
        elif not next_statuses:
            st.info("Bu durumdan geçilebilecek yeni bir durum yok veya rolünün yetkisi bulunmuyor.")
        else:
            u1, u2 = st.columns(2)
            with u1:
                new_status = st.selectbox("Yeni durum", next_statuses)
                new_unit = st.text_input("Atanacak / yönlendirilecek birim", value=str(payload.get("assigned_unit", "")))
                new_priority = st.selectbox("Öncelik", ["Düşük", "Normal", "Yüksek", "Acil"], index=["Düşük", "Normal", "Yüksek", "Acil"].index(payload.get("priority", "Normal") if payload.get("priority", "Normal") in ["Düşük", "Normal", "Yüksek", "Acil"] else "Normal"))
            with u2:
                action_note = st.text_area(
                    "İşlem notu",
                    height=150,
                    placeholder="Birim görüşü, onay/revizyon gerekçesi veya yönlendirme notu yaz.",
                )
            if st.button("İş Akışı Durumunu Güncelle", type="primary", use_container_width=True):
                try:
                    updated = update_workflow_status(
                        OUTPUTS_DIR,
                        workflow_id=workflow_id,
                        new_status=new_status,
                        username=username,
                        role=role,
                        note=action_note,
                        assigned_unit=new_unit,
                        priority=new_priority,
                    )
                    log_event(BASE_DIR, username, role, "workflow_status_changed", "success", f"{workflow_id}: {current_status} -> {new_status}", {"workflow_id": workflow_id})
                    st.success(f"Durum güncellendi: {updated.get('status')}")
                    st.info("Listeyi güncellemek için sayfayı yeniden çalıştırabilirsin.")
                except Exception as exc:
                    log_event(BASE_DIR, username, role, "workflow_status_changed", "failed", str(exc), {"workflow_id": workflow_id})
                    st.error(f"Durum güncellenemedi: {exc}")

    with flow_tabs[1]:
        draft = payload.get("draft") or {}
        st.write(f"**Yazı türü:** {draft.get('draft_type', '-')}")
        st.write(f"**Konu:** {draft.get('subject', payload.get('subject', '-'))}")
        can_edit_draft = permissions.get("can_manage_workflow") and role in {"admin", "yazi_isleri", "birim_yetkilisi", "onayci"}
        edited_body = st.text_area("İş akışı taslak metni", value=str(draft.get("body", "")), height=300, disabled=not can_edit_draft)
        if can_edit_draft:
            draft_note = st.text_input("Taslak güncelleme notu", placeholder="Örn. Onay öncesi üslup düzeltildi.")
            if st.button("Taslak Değişikliğini Kaydet", use_container_width=True):
                try:
                    update_workflow_draft(OUTPUTS_DIR, workflow_id, edited_body, username, role, note=draft_note)
                    log_event(BASE_DIR, username, role, "workflow_draft_updated", "success", workflow_id, {"workflow_id": workflow_id})
                    st.success("Taslak güncellendi.")
                except Exception as exc:
                    st.error(f"Taslak güncellenemedi: {exc}")

        docx_bytes = build_official_docx_bytes(
            analysis=payload.get("analysis") or {},
            routing=payload.get("routing") or {},
            draft={**draft, "body": edited_body},
            sources=payload.get("sources") or [],
            institution_name=institution_name,
            unit_name=unit_name,
            signer_name=signer_name,
            signer_title=signer_title,
            document_number=document_number,
            include_analysis_appendix=include_analysis_appendix,
        )
        st.download_button(
            "İş Akışı Taslağını DOCX İndir",
            data=docx_bytes,
            file_name=f"{workflow_id}_taslak.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    with flow_tabs[2]:
        st.json(payload.get("analysis") or {}, expanded=False)
        st.markdown("#### Yönlendirme")
        st.json(payload.get("routing") or {}, expanded=False)
        st.markdown("#### RAG Kaynakları")
        sources = payload.get("sources") or []
        for idx, src in enumerate(sources, start=1):
            with st.expander(f"{idx}. {src.get('title', '-')} — Skor %{int(float(src.get('score', 0)) * 100)}"):
                st.write(src.get("content", ""))

    with flow_tabs[3]:
        history = payload.get("history") or []
        if history:
            for event in history[::-1]:
                st.markdown(f"**{event.get('timestamp')} — {event.get('action')}**")
                st.write(f"Kullanıcı: {event.get('user')} / Rol: {event.get('role')}")
                st.write(f"Durum: {event.get('from_status')} → {event.get('to_status')}")
                if event.get("note"):
                    st.info(event.get("note"))
                st.divider()
        else:
            st.info("Geçmiş kaydı bulunamadı.")

    with flow_tabs[4]:
        st.json(payload, expanded=False)

    with flow_tabs[5]:
        if role != "admin":
            st.info("Sadece admin iş akışı kaydını silebilir.")
        else:
            st.warning("Silme işlemi kaydı tamamen yok etmez; outputs/deleted_workflows klasörüne yedek olarak taşır.")
            confirm_delete_wf = st.checkbox("Bu iş akışı kaydını silmeyi onaylıyorum", key=f"confirm_delete_wf_{workflow_id}")
            if st.button("Seçili İş Akışı Kaydını Sil", disabled=not confirm_delete_wf, use_container_width=True):
                try:
                    moved = delete_workflow_case(OUTPUTS_DIR, workflow_id, username, role)
                    log_event(BASE_DIR, username, role, "workflow_deleted", "success", str(moved), {"workflow_id": workflow_id})
                    st.warning(f"Kayıt yedeğe taşındı: {moved}")
                except Exception as exc:
                    st.error(f"Kayıt silinemedi: {exc}")

def render_database_panel() -> None:
    """MVP-14 kurumsal veri tabanı izleme ve dışa aktarma paneli."""
    st.subheader("Veritabanı Paneli")
    st.write(
        "Bu panel, demo dosya arşivine ek olarak analiz, geri bildirim ve denetim kayıtlarını yerel SQLite veritabanında tutar. "
        "Ürünleşme aşamasında aynı şema PostgreSQL'e taşınacaktır."
    )

    stats = db_stats(BASE_DIR)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Analiz kaydı", stats.get("document_runs", 0))
    m2.metric("Geri bildirim", stats.get("feedback_records", 0))
    m3.metric("Arşiv referansı", stats.get("archive_records", 0))
    m4.metric("Kaynak olayı", stats.get("resource_events", 0))
    m5.metric("Audit log", stats.get("audit_events", 0))
    st.caption(f"DB yolu: {stats.get('db_path')} | Son analiz: {stats.get('latest_analysis')}")

    db_tab1, db_tab2, db_tab3, db_tab4 = st.tabs(["Analiz Kayıtları", "Geri Bildirimler", "Audit Log", "Dışa Aktar"])
    with db_tab1:
        rows = list_analysis_runs(BASE_DIR, limit=50)
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("Henüz veritabanına kaydedilmiş analiz yok. Bir evrak analiz ettiğinde otomatik kayıt oluşur.")
    with db_tab2:
        rows = list_feedback_records(BASE_DIR, limit=50)
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("Henüz geri bildirim kaydı yok.")
    with db_tab3:
        rows = list_audit_events(BASE_DIR, limit=100)
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("Henüz audit log kaydı yok.")
    with db_tab4:
        st.download_button(
            "Veritabanı Yedeği ZIP İndir",
            data=build_db_export_zip(BASE_DIR),
            file_name="kamu_evrak_agent_db_export.zip",
            mime="application/zip",
            use_container_width=True,
        )
        st.info("ZIP içinde SQLite dosyası ve CSV raporları bulunur.")

def render_final_demo_panel() -> None:
    """Final demo akışı, konuşma metni ve paketleme çıktıları."""
    st.subheader("Final Demo ve Paketleme Paneli")
    st.write(
        "Bu panel final sunum/demo sırasında kullanılacak akışı, konuşma metnini, kontrol listesini ve demo paketini üretir. "
        "Artık sistemin ana parçaları hazır olduğu için bu adım, ürünü düzgün anlatılabilir ve teslim edilebilir hale getirir."
    )

    snapshot = build_project_snapshot(BASE_DIR)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sürüm", snapshot.get("version", "MVP-11"))
    m2.metric("RAG kaynakları", sum(snapshot.get("resource_counts", {}).values()))
    m3.metric("Arşiv kayıtları", snapshot.get("output_counts", {}).get("archived_cases", 0))
    m4.metric("Raporlar", snapshot.get("output_counts", {}).get("evaluation_reports", 0))

    demo_tab, checklist_tab, package_tab, roadmap_tab = st.tabs([
        "Demo Akışı",
        "Kontrol Listesi",
        "Paket İndir",
        "Sonraki Yol Haritası",
    ])

    with demo_tab:
        st.markdown("#### Final Demo Rehberi")
        demo_md = build_demo_markdown(BASE_DIR)
        st.markdown(demo_md)
        st.download_button(
            "Demo Rehberini Markdown İndir",
            data=demo_md.encode("utf-8"),
            file_name="demo_rehberi.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with checklist_tab:
        st.markdown("#### Demo Kontrol Listesi")
        checklist = build_demo_checklist_markdown()
        st.markdown(checklist)
        st.download_button(
            "Kontrol Listesini Markdown İndir",
            data=checklist.encode("utf-8"),
            file_name="demo_kontrol_listesi.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with package_tab:
        st.markdown("#### Demo Teslim Paketi")
        st.write(
            "Bu ZIP dosyası demo rehberi, kontrol listesi, proje özeti, test vakaları ve örnek RAG kaynaklarını içerir. "
            "Kod paketinden ayrı olarak jüri/sunum/demo dokümantasyonu için kullanılabilir."
        )
        st.json(snapshot, expanded=False)
        st.download_button(
            "Final Demo Paketini ZIP İndir",
            data=build_demo_package_zip(BASE_DIR),
            file_name="final_demo_paketi.zip",
            mime="application/zip",
            use_container_width=True,
        )

    with roadmap_tab:
        st.markdown("#### Demo Sonrası Ürünleşme Adımları")
        st.write("Bu MVP-11 ile yarışma/demo seviyesi tamamlanır. Gerçek ürünleşme için önerilen sonraki aşamalar:")
        st.markdown(
            """
1. Kullanıcı girişi ve rol yetkilendirme
2. Kurum/birim bazlı onay akışı
3. Hassas veri maskeleme ve KVKK log politikası
4. EBYS/DYS entegrasyon simülasyonu veya gerçek API entegrasyonu
6. Docker ile kurum içi kurulum paketi
7. Kurumsal tema, kullanıcı yönetimi ve audit log
8. Performans testi ve güvenlik testleri
            """
        )


def render_evaluation_panel() -> None:
    """Test veri setiyle sistemi ölçmek ve raporlamak için değerlendirme paneli."""
    st.subheader("Test Sistemi ve Başarı Metrikleri")
    st.write(
        "Bu panel, sistemin belirli test evrakları üzerindeki performansını ölçer. "
        "Sınıflandırma doğruluğu, birim yönlendirme doğruluğu, taslak üretim oranı ve çalışma süreleri hesaplanır. "
        "Sonuçlar demo raporu olarak JSON, CSV ve Markdown formatında indirilebilir."
    )

    test_cases_dir = DATA_DIR / "test_cases"
    cases = load_test_cases(test_cases_dir)

    metric_hint = st.columns(4)
    metric_hint[0].metric("Test vakası", len(cases))
    metric_hint[1].metric("Kaynak klasörü", "3")
    metric_hint[2].metric("RAG modu", rag_mode)
    metric_hint[3].metric("Agent modu", llm_mode)

    tab_cases, tab_run, tab_reports = st.tabs(["Test Vakaları", "Toplu Test Çalıştır", "Sonuç / Rapor"])

    with tab_cases:
        st.markdown("#### Test Vaka Listesi")
        if cases:
            st.dataframe(
                [
                    {
                        "case_id": c.get("case_id"),
                        "title": c.get("title"),
                        "expected_document_type": c.get("expected_document_type"),
                        "expected_unit": c.get("expected_unit"),
                        "text_len": len(str(c.get("document_text", ""))),
                    }
                    for c in cases
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Test vakası yok.")

        st.markdown("#### Yeni / Düzenlenecek Test Vakası")
        edit_labels = ["Yeni test vakası"] + [f"{c.get('case_id')} — {c.get('title')}" for c in cases]
        selected_edit = st.selectbox("Düzenlenecek vaka", edit_labels, key="eval_case_edit_select")
        selected_case = {}
        if selected_edit != "Yeni test vakası":
            selected_id = selected_edit.split(" — ")[0]
            selected_case = next((c for c in cases if str(c.get("case_id")) == selected_id), {})

        e1, e2 = st.columns(2)
        with e1:
            case_id = st.text_input("Vaka ID", value=str(selected_case.get("case_id", f"TC-{len(cases)+1:03d}")))
            title = st.text_input("Başlık", value=str(selected_case.get("title", "")))
            expected_document_type = st.text_input("Beklenen evrak türü", value=str(selected_case.get("expected_document_type", "")))
            expected_unit = st.text_input("Beklenen birim", value=str(selected_case.get("expected_unit", "")))
        with e2:
            keywords_text = st.text_area(
                "Taslakta beklenen anahtar kelimeler / satır satır",
                value="\n".join(selected_case.get("expected_draft_keywords") or []),
                height=120,
            )
            document_text_case = st.text_area(
                "Test evrak metni",
                value=str(selected_case.get("document_text", "")),
                height=220,
            )

        c_save, c_delete = st.columns(2)
        with c_save:
            if st.button("Test Vakasını Kaydet", use_container_width=True):
                case = {
                    "case_id": case_id.strip(),
                    "title": title.strip(),
                    "document_text": document_text_case.strip(),
                    "expected_document_type": expected_document_type.strip(),
                    "expected_unit": expected_unit.strip(),
                    "expected_draft_keywords": [x.strip() for x in keywords_text.splitlines() if x.strip()],
                }
                if not case["document_text"]:
                    st.warning("Test evrak metni boş olamaz.")
                else:
                    saved_path = save_test_case(test_cases_dir, case)
                    st.success(f"Test vakası kaydedildi: {saved_path.relative_to(BASE_DIR)}")
                    st.info("Listeyi yenilemek için sayfayı yeniden çalıştırabilirsin.")
        with c_delete:
            confirm_delete_case = st.checkbox("Seçili test vakasını silmeyi onaylıyorum", key="confirm_delete_test_case")
            if st.button("Seçili Test Vakasını Sil", disabled=(selected_edit == "Yeni test vakası" or not confirm_delete_case), use_container_width=True):
                removed = delete_test_case(test_cases_dir, selected_case.get("case_id", ""))
                st.warning(f"Silinen test vakası: {removed}")

    with tab_run:
        st.markdown("#### Toplu Test")
        st.write("Test, sol menüde seçtiğin RAG/Agent ayarlarıyla çalışır. LLM Agent seçiliyse her vaka için API isteği yapılabilir.")
        selected_case_ids = st.multiselect(
            "Çalıştırılacak vakalar",
            [str(c.get("case_id")) for c in cases],
            default=[str(c.get("case_id")) for c in cases],
        )
        eval_force_rule = st.checkbox(
            "Değerlendirmeyi hızlı/kural tabanlı çalıştır",
            value=(llm_mode == "Kural tabanlı"),
            help="API maliyeti/limit riski olmadan hızlı metrik almak için kullanılabilir.",
        )
        eval_llm_mode = "Kural tabanlı" if eval_force_rule else llm_mode

        if st.button("Toplu Testi Çalıştır", type="primary", use_container_width=True):
            if not selected_case_ids:
                st.warning("En az bir test vakası seç.")
            else:
                source_dirs = []
                if use_regulations:
                    source_dirs.append(DATA_DIR / "regulations")
                if use_templates:
                    source_dirs.append(DATA_DIR / "templates")
                if use_units:
                    source_dirs.append(DATA_DIR / "unit_definitions")

                run_cases = [c for c in cases if str(c.get("case_id")) in selected_case_ids]
                results = []
                progress = st.progress(0)
                status_box = st.empty()
                for i, case in enumerate(run_cases, start=1):
                    status_box.info(f"Çalışıyor: {case.get('case_id')} — {case.get('title')}")
                    pipeline_output = run_multi_agent_pipeline(
                        document_text=str(case.get("document_text", "")),
                        source_dirs=source_dirs,
                        vector_store_dir=VECTOR_STORE_DIR,
                        rag_mode=rag_mode,
                        force_rebuild_index=force_rebuild_index and i == 1,
                        top_k=top_k,
                        scenario=scenario,
                        llm_mode=eval_llm_mode,
                        openai_model=openai_model,
                        openrouter_model=openrouter_model,
                        draft_type_preference="Otomatik seç",
                    )
                    results.append(evaluate_single_result(case, pipeline_output))
                    progress.progress(i / len(run_cases))

                payload = build_evaluation_payload(
                    results,
                    settings={
                        "scenario": scenario,
                        "rag_mode": rag_mode,
                        "llm_mode": eval_llm_mode,
                        "top_k": top_k,
                        "use_regulations": use_regulations,
                        "use_templates": use_templates,
                        "use_units": use_units,
                    },
                )
                report_path = save_evaluation_report(OUTPUTS_DIR, payload)
                st.session_state["evaluation_payload"] = payload
                status_box.success(f"Test tamamlandı. Rapor kaydedildi: {report_path.relative_to(BASE_DIR)}")

    with tab_reports:
        st.markdown("#### Değerlendirme Sonucu")
        payload = st.session_state.get("evaluation_payload")
        if not payload:
            st.info("Henüz bu oturumda test çalıştırılmadı. 'Toplu Test Çalıştır' sekmesinden başlatabilirsin.")
            return

        metrics = payload.get("metrics") or {}
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Sınıflandırma", f"%{int(float(metrics.get('classification_accuracy', 0)) * 100)}")
        m2.metric("Yönlendirme", f"%{int(float(metrics.get('routing_accuracy', 0)) * 100)}")
        m3.metric("Taslak üretimi", f"%{int(float(metrics.get('draft_generation_rate', 0)) * 100)}")
        m4.metric("Ortalama süre", f"{metrics.get('avg_duration_ms', 0)} ms")

        m5, m6, m7, m8 = st.columns(4)
        m5.metric("Taslak kelime skoru", f"%{int(float(metrics.get('avg_draft_keyword_score', 0)) * 100)}")
        m6.metric("Ortalama güven", f"%{int(float(metrics.get('avg_confidence', 0)) * 100)}")
        m7.metric("Geçen", metrics.get("passed_cases", 0))
        m8.metric("İyileştirilecek", metrics.get("failed_cases", 0))

        results = payload.get("results") or []
        st.dataframe(results, use_container_width=True, hide_index=True)

        report_md = build_evaluation_markdown(payload)
        with st.expander("Markdown Değerlendirme Raporu", expanded=True):
            st.markdown(report_md)

        d1, d2, d3 = st.columns(3)
        with d1:
            st.download_button(
                "Raporu JSON İndir",
                data=build_evaluation_json_bytes(payload),
                file_name="evaluation_report.json",
                mime="application/json",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                "Sonuçları CSV İndir",
                data=build_evaluation_csv_bytes(results),
                file_name="evaluation_results.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with d3:
            st.download_button(
                "Raporu Markdown İndir",
                data=report_md.encode("utf-8"),
                file_name="evaluation_report.md",
                mime="text/markdown",
                use_container_width=True,
            )


if show_resource_panel:
    render_resource_management_panel()
    st.divider()

if show_archive_panel:
    render_archive_panel()
    st.divider()

if show_workflow_panel:
    render_workflow_panel()
    st.divider()

if show_evaluation_panel:
    render_evaluation_panel()
    st.divider()

if show_database_panel:
    render_database_panel()
    st.divider()

if show_final_demo_panel:
    render_final_demo_panel()
    st.divider()

can_analyze = permissions.get("can_analyze", False)
can_download_outputs = permissions.get("can_download_outputs", False)
can_save_archive = permissions.get("can_save_archive", False)
can_give_feedback = permissions.get("can_give_feedback", False)
can_view_agent_debug = permissions.get("can_view_agent_debug", False)
can_manage_workflow = permissions.get("can_manage_workflow", False)

if not can_analyze:
    st.info("Bu rol evrak analizi çalıştıramaz. Arşiv / geçmiş panelinden yetkili olduğun kayıtları görüntüleyebilirsin.")

left, right = st.columns([0.42, 0.58])

with left:
    st.subheader("1. Evrak Yükleme")
    uploaded_file = st.file_uploader(
        "PDF, TXT veya DOCX evrak yükle",
        type=["pdf", "txt", "docx"],
        accept_multiple_files=False,
    )

    manual_text = st.text_area(
        "Dosya yoksa evrak metnini buraya yapıştır",
        height=220,
        placeholder="Örnek: T.C. ... Belediyesine\nMahallemizde bulunan yolun...",
    )

    extract_clicked = st.button("Metni Hazırla", use_container_width=True, disabled=not can_analyze)

    if extract_clicked:
        if uploaded_file is not None:
            try:
                extracted_text, meta = extract_text_from_uploaded_file(uploaded_file)
                st.session_state["document_text"] = clean_text(extracted_text)
                st.session_state["file_meta"] = meta
                st.success("Metin başarıyla çıkarıldı.")
            except Exception as exc:
                st.error(f"Metin çıkarma sırasında hata oluştu: {exc}")
        elif manual_text.strip():
            st.session_state["document_text"] = clean_text(manual_text)
            st.session_state["file_meta"] = {"file_name": "manuel_giris", "file_type": "text/plain", "page_count": None}
            st.success("Manuel metin hazırlandı.")
        else:
            st.warning("Lütfen dosya yükle veya metin yapıştır.")

    document_text = st.session_state.get("document_text", "")
    file_meta = st.session_state.get("file_meta", {})

    if document_text:
        st.markdown("#### Evrak Bilgisi")
        st.write(f"**Dosya:** {file_meta.get('file_name', '-')}")
        st.write(f"**Tür:** {file_meta.get('file_type', '-')}")
        if file_meta.get("page_count"):
            st.write(f"**Sayfa sayısı:** {file_meta.get('page_count')}")

with right:
    st.subheader("2. Çıkarılan / Düzenlenebilir Metin")
    document_text = st.text_area(
        "OCR veya dosya metni",
        value=st.session_state.get("document_text", ""),
        height=360,
        key="editable_document_text",
        placeholder="Metin burada görünecek. OCR hatası varsa burada düzeltebilirsin.",
    )

    run_analysis = st.button("Analiz Et ve Taslak Oluştur", type="primary", use_container_width=True, disabled=not can_analyze)

if run_analysis:
    if not can_analyze:
        st.warning("Bu kullanıcı rolünün analiz çalıştırma yetkisi yok.")
    elif not document_text.strip():
        st.warning("Analiz için önce evrak metni gerekli.")
    else:
        with st.spinner("Çok-agent iş akışı çalışıyor: Reader → RAG → Sınıflandırma → Yönlendirme → Taslak → Kontrol..."):
            source_dirs = []
            if use_regulations:
                source_dirs.append(DATA_DIR / "regulations")
            if use_templates:
                source_dirs.append(DATA_DIR / "templates")
            if use_units:
                source_dirs.append(DATA_DIR / "unit_definitions")

            pipeline_output = run_multi_agent_pipeline(
                document_text=document_text,
                source_dirs=source_dirs,
                vector_store_dir=VECTOR_STORE_DIR,
                rag_mode=rag_mode,
                force_rebuild_index=force_rebuild_index,
                top_k=top_k,
                scenario=scenario,
                llm_mode=llm_mode,
                openai_model=openai_model,
                openrouter_model=openrouter_model,
                draft_type_preference=draft_type_preference,
            )

            st.session_state["analysis_result"] = pipeline_output["analysis"]
            st.session_state["matched_sources"] = pipeline_output["matched_sources"]
            st.session_state["rag_info"] = pipeline_output["rag_info"]
            st.session_state["rag_warning"] = pipeline_output["rag_warning"]
            st.session_state["routing_result"] = pipeline_output["routing"]
            st.session_state["draft_result"] = pipeline_output["draft"]
            st.session_state["llm_status"] = pipeline_output["llm_status"]
            st.session_state["agent_trace"] = pipeline_output["agent_trace"]
            st.session_state["pipeline_meta"] = pipeline_output["pipeline_meta"]
            st.session_state["document_text"] = document_text
            try:
                run_id = save_analysis_run(
                    base_dir=BASE_DIR,
                    username=current_user.get("username", "-"),
                    role=current_user.get("role", "-"),
                    document_text=document_text,
                    file_meta=st.session_state.get("file_meta", {}),
                    analysis=pipeline_output["analysis"],
                    routing=pipeline_output["routing"],
                    draft=pipeline_output["draft"],
                    sources=pipeline_output["matched_sources"],
                    llm_status=pipeline_output["llm_status"],
                    agent_trace=pipeline_output["agent_trace"],
                    pipeline_meta=pipeline_output["pipeline_meta"],
                    rag_info=pipeline_output["rag_info"],
                )
                st.session_state["current_run_id"] = run_id
            except Exception as exc:
                st.warning(f"Veritabanı analiz kaydı oluşturulamadı: {exc}")

analysis_result = st.session_state.get("analysis_result")
matched_sources = st.session_state.get("matched_sources")
routing_result = st.session_state.get("routing_result")
draft_result = st.session_state.get("draft_result")
rag_info = st.session_state.get("rag_info")
rag_warning = st.session_state.get("rag_warning")
llm_status = st.session_state.get("llm_status")
agent_trace = st.session_state.get("agent_trace")
pipeline_meta = st.session_state.get("pipeline_meta")
file_meta = st.session_state.get("file_meta", {})

if analysis_result:
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "Evrak Analizi",
        "Eksik Bilgiler",
        "RAG Kaynakları",
        "Birim Yönlendirme",
        "Resmî Yazı Taslağı",
        "Agent Durumu",
        "Agent Akışı",
        "Geri Bildirim",
    ])

    with tab1:
        c1, c2, c3 = st.columns(3)
        c1.metric("Evrak türü", analysis_result["document_type"])
        c2.metric("Güven", f"%{int(analysis_result['confidence'] * 100)}")
        c3.metric("Risk seviyesi", analysis_result["risk_level"])

        st.markdown("#### Kısa Özet")
        st.info(analysis_result["summary"])

        st.markdown("#### Çıkarılan Alanlar")
        st.json(analysis_result["extracted_fields"], expanded=True)

    with tab2:
        missing = analysis_result.get("missing_information", [])
        if missing:
            st.warning("Evrakta eksik veya belirsiz görünen bilgiler bulundu:")
            for item in missing:
                st.write(f"- {item}")
        else:
            st.success("Temel alanlarda belirgin eksik bilgi tespit edilmedi.")

        st.markdown("#### Kullanıcıya Öneri")
        st.write(analysis_result["user_recommendation"])

    with tab3:
        if rag_warning:
            st.warning(rag_warning)

        if rag_info:
            c1, c2, c3 = st.columns(3)
            c1.metric("RAG backend", str(rag_info.get("backend", "-")))
            c2.metric("Index durumu", str(rag_info.get("status", "-")))
            c3.metric("Parça sayısı", str(rag_info.get("chunk_count", "-")))

        if matched_sources:
            for idx, src in enumerate(matched_sources, start=1):
                score_percent = max(0, min(100, int(src.get("score", 0) * 100)))
                with st.expander(f"{idx}. {src['title']} — Benzerlik: %{score_percent}", expanded=idx == 1):
                    st.write(src["content"])
                    st.caption(
                        f"Kaynak türü: {src.get('source_type', '-')} | "
                        f"Dosya: {src.get('file_name', '-')} | "
                        f"Chunk: {src.get('chunk_index', '-')}"
                    )
        else:
            st.warning("Eşleşen kaynak bulunamadı. data klasöründeki kaynak dosyalarını kontrol et.")

    with tab4:
        st.markdown("#### Önerilen Birim")
        st.success(routing_result["recommended_unit"])
        st.write(f"**Güven skoru:** %{int(routing_result['confidence'] * 100)}")
        st.write(f"**Gerekçe:** {routing_result['reason']}")
        st.write("**Alternatif birimler:**")
        for unit in routing_result["alternative_units"]:
            st.write(f"- {unit}")

    with tab5:
        st.markdown("#### Taslak Bilgisi")
        st.write(f"**Yazı türü:** {draft_result['draft_type']}")
        st.write(f"**Konu:** {draft_result['subject']}")
        editable_draft = st.text_area(
            "Düzenlenebilir taslak metin",
            value=draft_result["body"],
            height=360,
            key="editable_draft_text",
        )

        download_text = build_download_text(
            analysis=analysis_result,
            routing=routing_result,
            draft={**draft_result, "body": editable_draft},
            sources=matched_sources,
        )

        final_draft = {**draft_result, "body": editable_draft}

        docx_bytes = build_official_docx_bytes(
            analysis=analysis_result,
            routing=routing_result,
            draft=final_draft,
            sources=matched_sources,
            institution_name=institution_name,
            unit_name=unit_name,
            signer_name=signer_name,
            signer_title=signer_title,
            document_number=document_number,
            include_analysis_appendix=include_analysis_appendix,
        )

        case_json_bytes = build_case_json_bytes(
            document_text=st.session_state.get("document_text", ""),
            file_meta=file_meta,
            analysis=analysis_result,
            routing=routing_result,
            draft=final_draft,
            sources=matched_sources,
            llm_status=llm_status,
        )

        if can_download_outputs:
            dl1, dl2, dl3 = st.columns(3)
            with dl1:
                st.download_button(
                    label="TXT Olarak İndir",
                    data=download_text,
                    file_name="resmi_yazi_taslagi.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with dl2:
                st.download_button(
                    label="DOCX Resmî Yazı İndir",
                    data=docx_bytes,
                    file_name="resmi_yazi_taslagi.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            with dl3:
                st.download_button(
                    label="Analiz JSON İndir",
                    data=case_json_bytes,
                    file_name="evrak_analiz_kaydi.json",
                    mime="application/json",
                    use_container_width=True,
                )
        else:
            st.info("Bu rolün çıktı indirme yetkisi yok.")

        if can_save_archive and st.button("Bu Analizi Yerel Arşive Kaydet", use_container_width=True):
            saved_path = save_case_json(
                outputs_dir=OUTPUTS_DIR,
                document_text=st.session_state.get("document_text", ""),
                file_meta=file_meta,
                analysis=analysis_result,
                routing=routing_result,
                draft=final_draft,
                sources=matched_sources,
                llm_status=llm_status,
            )
            st.success(f"Analiz kaydı oluşturuldu: {saved_path}")
            try:
                save_archive_reference(
                    base_dir=BASE_DIR,
                    username=current_user.get("username", "-"),
                    run_id=st.session_state.get("current_run_id", ""),
                    archive_path=str(saved_path),
                    analysis=analysis_result,
                    routing=routing_result,
                    payload={"archive_path": str(saved_path)},
                )
            except Exception as exc:
                st.warning(f"Veritabanı arşiv referansı kaydedilemedi: {exc}")

        if can_manage_workflow:
            st.divider()
            st.markdown("#### İş Akışı")
            workflow_note = st.text_input(
                "İş akışına gönderme notu",
                value="Taslak onay sürecine aktarılmıştır.",
                key="workflow_create_note",
            )
            if st.button("İş Akışına Gönder / Onaya Al", type="secondary", use_container_width=True):
                try:
                    wf = create_workflow_case(
                        outputs_dir=OUTPUTS_DIR,
                        username=current_user.get("username", "-"),
                        role=current_user.get("role", "-"),
                        document_text=st.session_state.get("document_text", ""),
                        file_meta=file_meta,
                        analysis=analysis_result,
                        routing=routing_result,
                        draft=final_draft,
                        sources=matched_sources or [],
                        run_id=st.session_state.get("current_run_id", ""),
                        note=workflow_note,
                    )
                    log_event(
                        BASE_DIR,
                        current_user.get("username", "-"),
                        current_user.get("role", "-"),
                        "workflow_created",
                        "success",
                        wf.get("workflow_id", ""),
                        {"workflow_id": wf.get("workflow_id")},
                    )
                    st.success(f"İş akışı kaydı oluşturuldu: {wf.get('workflow_id')}")
                    st.info("Sol menüden 'İş akışı / onay panelini göster' seçeneğiyle kaydı takip edebilirsin.")
                except Exception as exc:
                    st.error(f"İş akışı kaydı oluşturulamadı: {exc}")
        else:
            st.info("Bu rol iş akışına yeni kayıt gönderemez.")

        st.caption("Not: Bu sistem karar vermez; yalnızca öneri ve taslak üretir. Nihai onay yetkili kullanıcıdadır.")

    with tab6:
        st.markdown("#### Agent Durumu")
        if not can_view_agent_debug:
            st.info("Bu rol agent teknik detaylarını görüntüleyemez.")
        elif llm_status:
            if llm_status.get("status") == "success":
                st.success(llm_status.get("detail"))
            elif llm_status.get("status") == "fallback":
                st.warning(llm_status.get("detail"))
            else:
                st.info(llm_status.get("detail"))
            final_review = llm_status.get("final_review") or {}
            if final_review:
                st.markdown("#### Son Kontrol Durumu")
                label = final_review.get("label", "İnsan Onayı Gerekli")
                if final_review.get("severity") == "warning":
                    st.warning(label)
                else:
                    st.info(label)
                if final_review.get("blocking_issues"):
                    st.markdown("**Kritik uyarılar:**")
                    for issue in final_review.get("blocking_issues", []):
                        st.write(f"- {issue}")
                if final_review.get("issues"):
                    st.markdown("**Kontrol/eksik bilgi notları:**")
                    for issue in final_review.get("issues", []):
                        st.write(f"- {issue}")
                st.caption(final_review.get("safety_note", ""))
            st.json(llm_status, expanded=False)
        else:
            st.info("Bu analizde agent durum bilgisi bulunamadı.")

        st.markdown("#### Metin Kontrolü")
        debug = (llm_status or {}).get("text_debug") or document_debug_info(st.session_state.get("document_text", ""))
        c1, c2, c3 = st.columns(3)
        c1.metric("Karakter", debug.get("character_count", 0))
        c2.metric("Kelime", debug.get("word_count", 0))
        c3.metric("Satır", debug.get("line_count", 0))
        with st.expander("Modelin gördüğü metnin ilk 500 karakteri"):
            st.code(debug.get("first_500_chars", ""), language="text")

        st.markdown("#### Çalışma Mantığı")
        st.write(
            "MVP-14 sürümünde OpenRouter LLM Agent ve Embedding RAG arka planda sabit çalışır; kullanıcı arayüzü sadeleştirilmiştir. İş akışı çok-agent yapısına ayrılmıştır; Reader, RAG, Classifier/Extractor, Routing, Drafting ve Review agentları sıralı çalışır. Reader Agent metni kontrol eder, RAG Agent kaynakları getirir, "
            "Classifier/Extractor Agent alanları çıkarır, Routing Agent birim önerir, Drafting Agent taslak üretir ve Review Agent son güvenlik kontrolünü yapar."
        )

    with tab7:
        st.markdown("#### Çok-Agent İş Akışı")
        if not can_view_agent_debug:
            st.info("Bu rol agent akış detaylarını görüntüleyemez.")
        elif pipeline_meta:
            c1, c2, c3 = st.columns(3)
            c1.metric("Pipeline", pipeline_meta.get("version", "-"))
            c2.metric("Agent sayısı", pipeline_meta.get("agent_count", "-"))
            c3.metric("Süre", f"{pipeline_meta.get('duration_ms', 0)} ms")

        if can_view_agent_debug and agent_trace:
            status_icon = {"success": "✅", "info": "🟡", "warning": "⚠️", "fallback": "↩️", "error": "❌", "not_used": "ℹ️"}
            for idx, step in enumerate(agent_trace, start=1):
                icon = status_icon.get(step.get("status"), "ℹ️")
                with st.expander(f"{idx}. {icon} {step.get('agent')} — {step.get('summary')}", expanded=idx <= 2):
                    st.write(f"**Durum:** {step.get('status')}")
                    st.write(f"**Süre:** {step.get('duration_ms')} ms")
                    st.json(step.get("details", {}), expanded=False)
        elif can_view_agent_debug:
            st.info("Bu analiz için agent akışı kaydı bulunamadı.")

    with tab8:
        st.markdown("#### Kullanıcı Geri Bildirimi / Öğrenme Verisi")
        if not can_give_feedback:
            st.info("Bu rol geri bildirim kaydı oluşturamaz.")
            st.stop()
        st.write(
            "Bu bölüm sistemin çıktısını insan değerlendirmesiyle kaydeder. Oluşan JSONL dosyası RAG kaynak iyileştirme, test seti ve hata analizi için kullanılabilir."
        )

        fb1, fb2 = st.columns(2)
        with fb1:
            corrected_type = st.text_input("Doğru evrak türü", value=str(analysis_result.get("document_type", "")))
            corrected_unit = st.text_input("Doğru yönlendirilecek birim", value=str(routing_result.get("recommended_unit", "")))
            draft_quality = st.selectbox("Taslak kalitesi", ["İyi", "Düzenleme gerekli", "Kullanılamaz"], index=0)
        with fb2:
            classification_ok = st.checkbox("Evrak türü doğru", value=True)
            routing_ok = st.checkbox("Birim yönlendirme doğru", value=True)
            draft_ok = st.checkbox("Taslak genel olarak uygun", value=True)

        corrected_summary = st.text_area("Düzeltilmiş kısa özet / not", value=str(analysis_result.get("summary", "")), height=120)
        feedback_notes = st.text_area("Ek geri bildirim", height=120, placeholder="Yanlış sınıflandırma, eksik alan, taslak üslubu vb. notlarını yaz.")

        col_save, col_download = st.columns(2)
        with col_save:
            if st.button("Geri Bildirimi Kaydet", use_container_width=True):
                feedback = {
                    "classification_ok": classification_ok,
                    "routing_ok": routing_ok,
                    "draft_ok": draft_ok,
                    "corrected_document_type": corrected_type,
                    "corrected_unit": corrected_unit,
                    "corrected_summary": corrected_summary,
                    "draft_quality": draft_quality,
                    "notes": feedback_notes,
                }
                saved_path = save_feedback(
                    outputs_dir=OUTPUTS_DIR,
                    document_text=st.session_state.get("document_text", ""),
                    file_meta=file_meta,
                    analysis=analysis_result,
                    routing=routing_result,
                    draft=draft_result,
                    feedback=feedback,
                )
                st.success(f"Geri bildirim kaydedildi: {saved_path}")
                try:
                    save_feedback_record(
                        base_dir=BASE_DIR,
                        username=current_user.get("username", "-"),
                        role=current_user.get("role", "-"),
                        run_id=st.session_state.get("current_run_id", ""),
                        feedback=feedback,
                        payload={
                            "document_text": st.session_state.get("document_text", ""),
                            "file_meta": file_meta,
                            "analysis": analysis_result,
                            "routing": routing_result,
                            "draft": draft_result,
                            "feedback": feedback,
                        },
                    )
                except Exception as exc:
                    st.warning(f"Veritabanı geri bildirim kaydı oluşturulamadı: {exc}")
        with col_download:
            st.download_button(
                label="Feedback JSONL İndir",
                data=build_feedback_jsonl_bytes(OUTPUTS_DIR),
                file_name="feedback_dataset.jsonl",
                mime="application/jsonl",
                use_container_width=True,
            )
else:
    st.info("Başlamak için evrak yükle veya metin yapıştır, ardından 'Metni Hazırla' ve 'Analiz Et ve Taslak Oluştur' butonlarını kullan.")
