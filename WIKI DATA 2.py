"""
🛡️ Architecte d'Autorité Sémantique v7.5 (Stability & Monitoring)
------------------------------------------------------------------
- Monitoring : Console de logs en temps réel (Sidebar).
- Fix Wikidata : Headers certifiés "Wikimedia Friendly".
- GEO AI : Mistral remplit Descriptions + Expertise + Maison Mère.
- Persistance : Chargement sidebar immédiat avec fix de rafraîchissement.
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
def add_log(msg, type="info"):
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{timestamp}] {msg}")
    if len(st.session_state.logs) > 20: st.session_state.logs.pop(0)

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
    siret: str = ""
    isni: str = ""
    ror: str = ""
    lei: str = ""
    address: str = ""
    city: str = ""
    postal_code: str = ""
    website: str = ""
    org_type: str = "Organization"
    parent_org_name: str = ""
    parent_org_wiki: str = ""

    def authority_score(self) -> int:
        score = 0
        if self.qid: score += 25
        if self.siren: score += 20
        if self.lei: score += 20
        if self.website: score += 15
        if self.isni or self.ror: score += 20
        return min(score, 100)

# ============================================================================
# 2. AUTHENTIFICATION
# ============================================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'entity' not in st.session_state: st.session_state.entity = Entity()
if 'relations' not in st.session_state: st.session_state.relations = []
if 'social_links' not in st.session_state: 
    st.session_state.social_links = {k:'' for k in ['linkedin','twitter','facebook','instagram','youtube']}
if 'mistral_key' not in st.session_state: st.session_state.mistral_key = ""

def check_password():
    if st.session_state.authenticated: return True
    st.title("🛡️ Accès Restreint")
    pwd = st.text_input("Veuillez entrer le mot de passe :", type="password")
    if st.button("Se connecter"):
        if pwd == "SEOTOOLS":
            st.session_state.authenticated = True
            st.rerun()
        else: st.error("Accès refusé.")
    return False

if not check_password(): st.stop()

# ============================================================================
# 3. MOTEUR API & IA (MISTRAL v7.5)
# ============================================================================
class APIManager:
    # Headers obligatoires pour Wikidata
    WIKI_HEADERS = {
        "User-Agent": "AAS_Bot/7.5 (https://votre-site.com; admin@votre-seo.com) httpx/python",
        "Accept": "application/json"
    }

    @staticmethod
    async def fetch_wikidata_search(client, query):
        add_log(f"Recherche Wikidata : {query}...")
        try:
            r = await client.get("https://www.wikidata.org/w/api.php", params={
                "action": "wbsearchentities", "search": query, "language": "fr", "format": "json", "limit": 5, "type": "item"
            }, headers=APIManager.WIKI_HEADERS)
            if r.status_code == 200:
                add_log("Wikidata : Résultats trouvés.", "success")
                return r.json().get('search', [])
            add_log(f"Erreur Wikidata API: {r.status_code}", "error")
            return []
        except Exception as e:
            add_log(f"Crash Wikidata : {str(e)}", "error")
            return []

class MistralEngine:
    @staticmethod
    async def optimize(api_key, entity):
        add_log("Appel Mistral AI pour optimisation GEO...")
        prompt = f"""Tu es un expert GEO. Analyse {entity.name}. SIREN: {entity.siren}.
        Réponds UNIQUEMENT en JSON avec ces clés : 
        {{"desc_fr": "...", "desc_en": "...", "expertise_fr": "...", "expertise_en": "...", "parent_name": "...", "parent_wiki": "Q..."}}"""
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post("https://api.mistral.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
                    timeout=25.0)
                if r.status_code == 200:
                    add_log("Mistral AI : Données générées avec succès.", "success")
                    return json.loads(r.json()['choices'][0]['message']['content'])
                add_log(f"Erreur Mistral API: {r.status_code}", "error")
                return None
            except Exception as e:
                add_log(f"Crash Mistral : {str(e)}", "error")
                return None

# ============================================================================
# 4. SIDEBAR (CONFIG, LOGS & RECHERCHE)
# ============================================================================
with st.sidebar:
    st.title("🛡️ AAS Admin v7.5")
    
    with st.expander("📟 Console de Logs", expanded=True):
        for log in reversed(st.session_state.logs):
            st.caption(log)
    
    st.subheader("📥 Charger Config")
    uploaded = st.file_uploader("JSON Config", type="json", label_visibility="collapsed")
    if uploaded:
        data = json.load(uploaded)
        st.session_state.entity = Entity(**data['entity'])
        st.session_state.social_links.update(data.get('social_links', {}))
        add_log("Importation configuration réussie.")
        st.rerun()

    st.divider()
    st.session_state.mistral_key = st.text_input("Clé Mistral", value=st.session_state.mistral_key, type="password")
    
    st.divider()
    st.subheader("🔍 Recherche")
    q = st.text_input("Nom de l'organisation")
    if st.button("Lancer l'audit", use_container_width=True, type="primary") and q:
        add_log(f"Audit lancé pour {q}")
        try:
            res = httpx.get(f"https://recherche-entreprises.api.gouv.fr/search?q={q}&per_page=1").json()['results'][0]
            e = st.session_state.entity
            e.name, e.siren = res['nom_complet'], res['siren']
            s = res.get('siege', {})
            e.address, e.city, e.postal_code = s.get('adresse',''), s.get('libelle_commune',''), s.get('code_postal','')
            st.session_state.entity = e
            add_log("INSEE : Données fusionnées.")
            st.rerun()
        except: add_log("INSEE : Recherche infructueuse.", "error")

# ============================================================================
# 5. GRAPH ENGINE (3 ORBITES)
# ============================================================================
def render_graph(entity, relations, socials):
    W, H = 850, 720
    CX, CY = W/2, H/2 - 20
    R_ID, R_REL, R_SOC = 180, 260, 330
    ids = [("Wikidata", entity.qid, "#22C55E", "W"), ("INSEE", entity.siren, "#F97316", "S"),
           ("ISNI", entity.isni, "#A855F7", "I"), ("ROR", entity.ror, "#EC4899", "R"),
           ("LEI", entity.lei, "#06B6D4", "L"), ("Web", entity.website, "#3B82F6", "W")]
    cfg_soc = {'linkedin': ('#0077B5', 'In'), 'twitter': ('#1DA1F2', 'X'), 'facebook': ('#1877F2', 'Fb'), 'instagram': ('#E4405F', 'Ig'), 'youtube': ('#FF0000', 'Yt')}
    soc_active = [(n.capitalize(), cfg_soc.get(n, ('#64748B', 'S'))) for n, url in socials.items() if url and url.strip()]
    
    svg = f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="background:white; border-radius:20px;">'
    svg += f'<circle cx="{CX}" cy="{CY}" r="{R_ID}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="10,5" />'
    
    for i, (lab, val, col, ico) in enumerate(ids):
        angle = (2 * math.pi * i) / len(ids) - (math.pi / 2)
        x, y = CX + R_ID * math.cos(angle), CY + R_ID * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="34" fill="{col if val else "#F8FAFC"}" opacity="{1 if val else 0.4}" />'
        svg += f'<text x="{x}" y="{y+7}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="20" fill="{"white" if val else "#94A3B8"}">{ico}</text>'
        svg += f'<text x="{x}" y="{y+50}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="10" fill="#1E293B">{lab}</text>'
    
    score = entity.authority_score()
    svg += f'<circle cx="{CX}" cy="{CY}" r="78" fill="navy" />'
    svg += f'<text x="{CX}" y="{CY+15}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="38" fill="white">{score}%</text>'
    svg += '</svg>'
    return svg

# ============================================================================
# 6. MAIN UI
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique")
e = st.session_state.entity

if e.name:
    tabs = st.tabs(["🎯 Carte", "🆔 Identité", "🪄 IA Magic (Mistral)", "🏢 Écosystème", "📱 Social Hub", "💾 Export"])
    
    with tabs[0]: st.markdown(f'<div style="text-align:center;">{render_graph(e, st.session_state.relations, st.session_state.social_links)}</div>', unsafe_allow_html=True)

    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            e.org_type = st.selectbox("Type Schema.org", ["Organization", "BankOrCreditUnion", "InsuranceAgency", "LocalBusiness"])
            e.name = st.text_input("Nom FR", e.name)
            e.legal_name = st.text_input("Raison Sociale", e.legal_name)
            e.siren = st.text_input("SIREN", e.siren)
        with c2:
            e.qid = st.text_input("Wikidata QID", e.qid)
            e.lei = st.text_input("Code LEI", e.lei)
            e.website = st.text_input("Site Web", e.website)
            e.ror = st.text_input("ROR ID", e.ror)
        
        st.divider()
        e.parent_org_name = st.text_input("Maison Mère", e.parent_org_name)
        e.parent_org_wiki = st.text_input("Wikidata Maison Mère", e.parent_org_wiki)
        st.session_state.entity = e

    with tabs[2]:
        if st.button("🪄 Remplir les champs (Desc + Expertise + Maison Mère)", use_container_width=True):
            res = asyncio.run(MistralEngine.optimize(st.session_state.mistral_key, e))
            if res:
                e.description_fr, e.description_en = res.get('desc_fr', ''), res.get('desc_en', '')
                e.expertise_fr, e.expertise_en = res.get('expertise_fr', ''), res.get('expertise_en', '')
                e.parent_org_name, e.parent_org_wiki = res.get('parent_name', ''), res.get('parent_wiki', '')
                st.success("Mise à jour effectuée !")
                st.rerun()
        c1, c2 = st.columns(2)
        e.description_fr = c1.text_area("Desc FR", e.description_fr)
        e.description_en = c2.text_area("Desc EN", e.description_en)
        e.expertise_fr = c1.text_input("Expertise FR", e.expertise_fr)
        e.expertise_en = c2.text_input("Expertise EN", e.expertise_en)

    with tabs[4]:
        sc1, sc2 = st.columns(2)
        for i, net in enumerate(st.session_state.social_links.keys()):
            with (sc1 if i%2==0 else sc2):
                st.session_state.social_links[net] = st.text_input(f"Lien {net.capitalize()}", st.session_state.social_links[net])

    with tabs[5]:
        json_ld = {
            "@context": "https://schema.org",
            "@type": e.org_type,
            "@id": f"{e.website.rstrip('/')}/#organization" if e.website else None,
            "name": [{"@language": "fr", "@value": e.name}, {"@language": "en", "@value": e.name_en or e.name}],
            "url": e.website,
            "description": [{"@language": "fr", "@value": e.description_fr}, {"@language": "en", "@value": e.description_en}],
            "taxID": f"FR{e.siren}" if e.siren else None,
            "leiCode": e.lei or None,
            "sameAs": [f"https://www.wikidata.org/wiki/{e.qid}" if e.qid else None] + [v for v in st.session_state.social_links.values() if v],
            "parentOrganization": {"@type": e.org_type, "name": e.parent_org_name, "sameAs": f"https://www.wikidata.org/wiki/{e.parent_org_wiki}" if e.parent_org_wiki else None} if e.parent_org_name else None,
            "knowsAbout": [{"@language": "fr", "@value": e.expertise_fr}, {"@language": "en", "@value": e.expertise_en}]
        }
        st.json(json_ld)
        cfg = {"entity": asdict(e), "social_links": st.session_state.social_links}
        st.download_button("💾 Sauvegarder Config", json.dumps(cfg, indent=2, ensure_ascii=False), f"config_{e.name}.json")
else:
    st.info("👈 Recherchez une entité ou importez une configuration.")
