"""
🛡️ Architecte d'Autorité Sémantique v7.6 (Resilience 2026 Edition)
------------------------------------------------------------------
- Fix : Bypass des erreurs SPARQL 2026 via Action API Fallback.
- Monitoring : Logs HTTP détaillés (403 Forbidden / 429 Rate Limit).
- Sécurité : Password SEOTOOLS + Clé Mistral.
- GEO : JSON-LD optimal multilingue avec filiation parentale.
"""

import streamlit as st
import asyncio
import httpx
import pandas as pd
import json
import math
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

# ============================================================================
# 1. INITIALISATION & LOGS
# ============================================================================
st.set_page_config(page_title="Architecte d'Autorité Sémantique", page_icon="🛡️", layout="wide")

if 'logs' not in st.session_state: st.session_state.logs = []
def add_log(msg, status="info"):
    icons = {"info": "ℹ️", "success": "✅", "error": "❌", "warning": "⚠️"}
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.logs.append(f"{icons.get(status, '•')} [{timestamp}] {msg}")
    if len(st.session_state.logs) > 25: st.session_state.logs.pop(0)

@dataclass
class Entity:
    name: str = ""
    name_en: str = ""
    legal_name: str = ""
    description_fr: str = ""
    description_en: str = ""
    expertise_fr: str = ""
    expertise_en: str = ""
    qid: str = ""
    siren: str = ""
    lei: str = ""
    website: str = ""
    org_type: str = "Organization"
    parent_org_name: str = ""
    parent_org_wiki: str = ""

    def authority_score(self) -> int:
        score = 0
        if self.qid: score += 25
        if self.siren: score += 25
        if self.lei: score += 20
        if self.website: score += 15
        if self.expertise_fr: score += 15
        return min(score, 100)

# ============================================================================
# 2. AUTHENTIFICATION
# ============================================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'entity' not in st.session_state: st.session_state.entity = Entity()
if 'social_links' not in st.session_state: 
    st.session_state.social_links = {k:'' for k in ['linkedin','twitter','facebook','instagram','youtube']}
if 'res_wiki' not in st.session_state: st.session_state.res_wiki = []

if not st.session_state.authenticated:
    st.title("🛡️ Accès Restreint AAS")
    pwd = st.text_input("Password :", type="password")
    if st.button("Unlock"):
        if pwd == "SEOTOOLS":
            st.session_state.authenticated = True
            st.rerun()
    st.stop()

# ============================================================================
# 3. MOTEUR API WIKIDATA 2026 (ACTION API + SPARQL)
# ============================================================================
class WikidataEngine:
    # Headers renforcés pour 2026 (obligatoire pour éviter 403)
    HEADERS = {
        "User-Agent": "SemanticAuthorityBot/7.6 (https://votre-agence-seo.com; contact@votre-domaine.fr) Python/httpx",
        "Accept": "application/json"
    }

    @staticmethod
    async def search(client, query):
        add_log(f"Recherche Wikidata pour: {query}")
        try:
            # On utilise l'API Action (plus robuste que SPARQL pour la recherche)
            url = "https://www.wikidata.org/w/api.php"
            params = {
                "action": "wbsearchentities",
                "search": query,
                "language": "fr",
                "format": "json",
                "limit": 5,
                "type": "item"
            }
            r = await client.get(url, params=params, headers=WikidataEngine.HEADERS, timeout=10.0)
            if r.status_code == 200:
                data = r.json()
                results = data.get('search', [])
                add_log(f"Wikidata : {len(results)} entités trouvées.", "success")
                return [{'qid': i['id'], 'label': i.get('label', ''), 'desc': i.get('description', '')} for i in results]
            add_log(f"Erreur Wikidata API: {r.status_code}", "error")
        except Exception as e:
            add_log(f"Crash Recherche : {str(e)}", "error")
        return []

    @staticmethod
    async def get_details(client, qid):
        add_log(f"Récupération détails QID: {qid}")
        # Stratégie hybride : Action API (Labels) + SPARQL (IDs complexes)
        # 1. Action API (Toujours stable)
        try:
            url = "https://www.wikidata.org/w/api.php"
            p = {"action": "wbgetentities", "ids": qid, "languages": "fr|en", "format": "json"}
            r = await client.get(url, params=p, headers=WikidataEngine.HEADERS)
            data = r.json().get('entities', {}).get(qid, {})
            label_fr = data.get('labels', {}).get('fr', {}).get('value', '')
            desc_fr = data.get('descriptions', {}).get('fr', {}).get('value', '')
        except: label_fr, desc_fr = "", ""

        # 2. SPARQL (Pour SIREN, LEI, Website)
        query = f"""SELECT ?siren ?lei ?website WHERE {{
          BIND(wd:{qid} AS ?item)
          OPTIONAL {{ ?item wdt:P1616 ?siren. }}
          OPTIONAL {{ ?item wdt:P1278 ?lei. }}
          OPTIONAL {{ ?item wdt:P856 ?website. }}
        }} LIMIT 1"""
        try:
            r = await client.get("https://query.wikidata.org/sparql", params={'query': query, 'format': 'json'}, headers=WikidataEngine.HEADERS)
            if r.status_code == 200:
                b = r.json()['results']['bindings']
                res = b[0] if b else {}
                return {
                    "name": label_fr, "desc": desc_fr,
                    "siren": res.get('siren', {}).get('value', ''),
                    "lei": res.get('lei', {}).get('value', ''),
                    "web": res.get('website', {}).get('value', '')
                }
            add_log(f"Erreur SPARQL: {r.status_code} (Migration 2026 en cours?)", "warning")
        except Exception as e:
            add_log("SPARQL indisponible, utilisation des données Action API.", "warning")
        
        return {"name": label_fr, "desc": desc_fr, "siren": "", "lei": "", "web": ""}

# ============================================================================
# 4. MISTRAL AI & SIDEBAR
# ============================================================================
class MistralEngine:
    @staticmethod
    async def optimize(api_key, entity):
        add_log("Génération GEO via Mistral AI...")
        prompt = f"Expert SEO. Analyse l'entreprise {entity.name}. Réponds en JSON: {{'desc_fr':'...', 'desc_en':'...', 'expertise_fr':'A, B', 'expertise_en':'C, D', 'parent':'Nom', 'parent_wiki':'QID'}}"
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post("https://api.mistral.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
                    timeout=20.0)
                return json.loads(r.json()['choices'][0]['message']['content'])
            except: return None

with st.sidebar:
    st.header("⚙️ Administration AAS")
    with st.expander("📟 Console Logs Temps Réel", expanded=True):
        for log in reversed(st.session_state.logs):
            st.caption(log)
    
    st.subheader("📥 Importer Dossier")
    uploaded = st.file_uploader("Config JSON", type="json", label_visibility="collapsed")
    if uploaded:
        d = json.load(uploaded)
        st.session_state.entity = Entity(**d['entity'])
        st.session_state.social_links.update(d.get('social_links', {}))
        add_log("Dossier chargé avec succès.", "success")
        st.rerun()

    st.divider()
    st.session_state.mistral_key = st.text_input("Mistral API Key", value=st.session_state.mistral_key, type="password")
    
    st.divider()
    st.subheader("🔍 Recherche")
    q = st.text_input("Nom de l'organisation")
    if st.button("Lancer l'audit", use_container_width=True, type="primary"):
        async def do_search():
            async with httpx.AsyncClient() as client:
                st.session_state.res_wiki = await WikidataEngine.search(client, q)
        asyncio.run(do_search())

    if st.session_state.get('res_wiki'):
        for r in st.session_state.res_wiki:
            if st.button(f"Fusionner {r['label']}", key=r['qid'], use_container_width=True):
                async def do_details():
                    async with httpx.AsyncClient() as client:
                        d = await WikidataEngine.get_details(client, r['qid'])
                        e = st.session_state.entity
                        e.name, e.qid = d['name'] or r['label'], r['qid']
                        e.description_fr = d['desc']
                        e.siren, e.lei, e.website = d['siren'], d['lei'], d['web']
                asyncio.run(do_details())
                st.rerun()

# ============================================================================
# 5. MAIN UI & EXPORT
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique v7.6")
e = st.session_state.entity

if e.name or e.siren:
    tabs = st.tabs(["🆔 Identité", "🪄 GEO Magic", "📱 Social", "💾 Export JSON-LD"])
    
    with tabs[0]:
        c1, c2 = st.columns(2)
        with c1:
            e.org_type = st.selectbox("Type", ["Organization", "BankOrCreditUnion", "InsuranceAgency"])
            e.name = st.text_input("Nom", e.name)
            e.siren = st.text_input("SIREN", e.siren)
        with c2:
            e.qid = st.text_input("QID", e.qid)
            e.lei = st.text_input("LEI", e.lei)
            e.website = st.text_input("Website", e.website)
        
        st.divider()
        e.parent_org_name = st.text_input("Maison Mère", e.parent_org_name)
        e.parent_org_wiki = st.text_input("QID Maison Mère", e.parent_org_wiki)
        
    with tabs[1]:
        st.info("Mistral AI va combler les vides et mapper l'expertise.")
        if st.button("🪄 Auto-Optimize via Mistral"):
            res = asyncio.run(MistralEngine.optimize(st.session_state.mistral_key, e))
            if res:
                e.description_fr, e.description_en = res.get('desc_fr',''), res.get('desc_en','')
                e.expertise_fr, e.expertise_en = res.get('expertise_fr',''), res.get('expertise_en','')
                e.parent_org_name = e.parent_org_name or res.get('parent','')
                e.parent_org_wiki = e.parent_org_wiki or res.get('parent_wiki','')
                st.rerun()
        e.description_fr = st.text_area("Description FR", e.description_fr)
        e.expertise_fr = st.text_input("Expertise FR", e.expertise_fr)

    with tabs[3]:
        # JSON-LD FINAL (Formaté sans indices parasites)
        json_ld = {
            "@context": "https://schema.org",
            "@type": e.org_type,
            "@id": f"{e.website.rstrip('/')}/#organization" if e.website else None,
            "name": [{"@language": "fr", "@value": e.name}, {"@language": "en", "@value": e.name_en or e.name}],
            "url": e.website,
            "taxID": f"FR{e.siren}" if e.siren else None,
            "identifier": [{"@type": "PropertyValue", "propertyID": "SIREN", "value": e.siren}] if e.siren else [],
            "sameAs": [f"https://www.wikidata.org/wiki/{e.qid}" if e.qid else None] + [v for v in st.session_state.social_links.values() if v],
            "parentOrganization": {"@type": e.org_type, "name": e.parent_org_name, "sameAs": f"https://www.wikidata.org/wiki/{e.parent_org_wiki}" if e.parent_org_wiki else None} if e.parent_org_name else None,
            "knowsAbout": [{"@language": "fr", "@value": e.expertise_fr}, {"@language": "en", "@value": e.expertise_en}]
        }
        st.json(json_ld)
        # Download Config
        cfg = {"entity": asdict(e), "social_links": st.session_state.social_links}
        st.download_button("💾 Save Config", json.dumps(cfg, indent=2, ensure_ascii=False), f"config_{e.name}.json")
else:
    st.info("👈 Utilise la barre latérale pour lancer un audit.")
