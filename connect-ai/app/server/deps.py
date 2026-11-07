"""Build adapters from Config. Real adapters (Firestore, Vertex, Gmail, Meta) are separate."""

from __future__ import annotations

import logging

from app.server.adapters.clock import OffsetClock, SystemClock
from app.server.adapters.contacts_csv import CsvContacts
from app.server.adapters.llm_fake import FakeLlm
from app.server.adapters.mail_fake import FakeMail
from app.server.adapters.owner_sim import HttpOwnerSim
from app.server.adapters.response_stats import ResponseStats
from app.server.adapters.sms_sim import SimSms
from app.server.adapters.store_memory import MemoryStore
from app.server.adapters.wa_fake import FakeWhatsApp
from app.server.adapters.yext_http import HttpYext
from app.server.config import Config
from app.server.services.common import Deps

log = logging.getLogger("connect.deps")


def build_deps(cfg: Config) -> Deps:
    from app.server.main import _setup_logging

    _setup_logging(cfg.log_level)  # idempotent; deps may be built before the app factory runs
    if cfg.store_mode == "firestore":
        from app.server.adapters.store_firestore import FirestoreStore

        store = FirestoreStore(project=cfg.gcp_project_id)
    else:
        store = MemoryStore()
    base = SystemClock()
    clock = OffsetClock(base, store) if cfg.enable_simulator else base
    if cfg.yext_mode == "embedded":
        from app.server.adapters.yext_embedded import start_embedded_mock

        yext_url = start_embedded_mock()
    else:
        yext_url = cfg.yext_base_url or ""
    yext = HttpYext(yext_url, cfg.yext_api_key, cfg.yext_use_id_token)
    if cfg.yext_sandbox_direct:  # mapped entities are read and written directly in the real sandbox
        from app.server.adapters.yext_routed import RoutedYext
        from app.server.services.sandbox import entity_map

        mapping = entity_map(cfg.yext_sandbox_entity_map)
        yext = RoutedYext(yext, HttpYext(cfg.yext_sandbox_base_url, cfg.yext_sandbox_api_key or ""), mapping)
    sim_url = cfg.simulator_base_url or yext_url
    if cfg.mail_mode == "gmail" and cfg.service_role == "webhooks":
        from app.server.adapters.mail_unavailable import UnavailableMail

        mail = UnavailableMail()
    elif cfg.mail_mode == "gmail":
        from app.server.adapters.mail_gmail import GmailMail, build_service

        service = build_service(cfg.gmail_client_id or "", cfg.gmail_client_secret or "", cfg.gmail_refresh_token or "")
        mail = GmailMail(service, cfg.gmail_address, cfg.sender_name, cfg.gmail_pubsub_topic)
    else:
        mail = FakeMail(cfg.gmail_address)
    if cfg.llm_mode == "vertex":
        from app.server.adapters.llm_vertex import VertexLlm

        llm = VertexLlm(cfg.gcp_project_id or "", cfg.vertex_location, cfg.llm_model)
    else:
        llm = FakeLlm()
    if cfg.wa_mode == "meta":
        from app.server.adapters.wa_meta import MetaWhatsApp

        whatsapp = MetaWhatsApp(cfg.wa_phone_number_id or "", cfg.wa_access_token or "", cfg.wa_graph_version)
    else:
        whatsapp = FakeWhatsApp()
    if cfg.suggestions_mode == "fake":
        from app.server.adapters.suggestions_fake import FakeSuggestions

        suggestions = FakeSuggestions()
    else:
        from app.server.adapters.suggestions_baseline import BaselineSuggestions

        if cfg.suggestions_mode == "v2":
            from app.detect.detector import DetectorV2

            suggestions = DetectorV2(cfg.snapshot_date, cfg.stale_evidence_days)
        else:
            suggestions = BaselineSuggestions(cfg.snapshot_date, cfg.stale_evidence_days)
    if cfg.findability_mode == "fake":
        from app.server.adapters.findability_fake import FakeFindability

        findability = FakeFindability()
    else:
        from app.server.adapters.findability import ParquetFindability

        findability = ParquetFindability(cfg.snapshot_date, cfg.priority_recent_days)
    extras: dict = {}
    if cfg.yext_sandbox_mirror and not cfg.yext_sandbox_direct:  # direct mode already writes to the sandbox
        extras["sandbox"] = HttpYext(cfg.yext_sandbox_base_url, cfg.yext_sandbox_api_key or "")
        if cfg.yext_mode == "embedded":  # use the live sandbox entities locally, nothing stored in the repo
            from app.server.adapters.yext_embedded import add_entities
            from app.server.services.sandbox import import_entities

            ents = import_entities(extras["sandbox"], cfg.yext_sandbox_entity_map)
            add_entities(ents)
            if hasattr(suggestions, "extra_demo_ids"):
                suggestions.extra_demo_ids = [e["meta"]["id"] for e in ents]
    return Deps(
        cfg=cfg,
        store=store,
        mail=mail,
        llm=llm,
        yext=yext,
        contacts=CsvContacts(),
        suggestions=suggestions,
        findability=findability,
        clock=clock,
        stats=ResponseStats(store),
        whatsapp=whatsapp,
        sms=SimSms(store, clock),
        owner_sim=HttpOwnerSim(sim_url) if cfg.enable_simulator and sim_url else None,
        extras=extras,
    )
