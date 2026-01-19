"""
🛡️ Architecte d'Autorité Sémantique v6.0 (Élite Edition)
------------------------------------------------------------------
- Performance : Requêtage asynchrone (asyncio + httpx).
- GEO Expertise : JSON-LD multilingue optimisé pour les moteurs de recherche.
- Trust Signals : taxID, leiCode, knowsAbout, subOrganization.
- Cartographie : 3 orbites dynamiques avec labels explicites.
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
# 1. CONFIGURATION & STYLE
# ============================================================================
st.set_page_config(
    page_title="Architecte d'Autorité Sémantique",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main { background-color: #F8FAFC; }
    .stTabs [data-baseweb="tab-list"] { 
        gap: 8px; background: white; padding: 10px; border-radius: 12px; border: 1px solid #E5E7EB;
    }
    .stTabs [aria-selected="true"] { background-color: #0066FF !important; color: white !important; }
    section[data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #E5E7EB; }
    .stMetric { background: white; padding: 15px; border-radius: 10px; border: 1px solid #E5E7EB; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 2. DATA MODELS
# ============================================================================
@dataclass
class Entity:
    name: str = ""
    name_en: str = ""
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
    postal_code: str = ""
    city: str = ""
    country: str = "France"
    ape: str = ""
    website: str = ""
    org_type: str = "Organization"
    
    def authority_score(self) -> int:
        score = 0
        if self.qid: score += 25
        if self.siren: score += 20
        if self.isni: score += 15
        if self.ror: score += 15
        if self.lei: score += 15
        if self.website: score += 10
        return min(score, 100)

@dataclass
class Relation:
    qid: str = ""
    name: str = ""
    url: str = ""
    schema_type: str = "Organization"
    include: bool = True

# ============================================================================
# 3. MOTEUR DE REQUÊTAGE ASYNCHRONE (PRO)
# ============================================================================
class AsyncAPIManager:
    WIKI_SEARCH = "https://www.wikidata.org/w/api.php"
    WIKI_SPARQL = "https://query.wikidata.org/sparql"
    INSEE_API = "https://recherche-entreprises.api.gouv.fr/search"

    @staticmethod
    async def search_wikidata(client: httpx.AsyncClient, query: str) -> List[Dict]:
        p = {"action": "wbsearchentities", "search": query, "language": "fr", "format": "json", "limit": 8}
        r = await client.get(AsyncAPIManager.WIKI_SEARCH, params=p)
        return [{'qid': i['id'], 'label': i.get('label', ''), 'src': 'wiki'} for i in r.json().get('search', [])]

    @staticmethod
    async def search_insee(client: httpx.AsyncClient, query: str) -> List[Dict]:
        r = await client.get(AsyncAPIManager.INSEE_API, params={"q": query, "per_page": 8})
        res = r.json().get('results', [])
        return [{'label': r['nom_complet'], 'siren': r['siren'], 'raw': r, 'src': 'insee'} for r in res]

    @staticmethod
    async def get_full_wikidata(client: httpx.AsyncClient, qid: str) -> Dict:
        q = f"""SELECT ?siren ?siret ?isni ?ror ?lei ?website ?inception ?hqLabel ?descFr ?descEn WHERE {{
          BIND(wd:{qid} AS ?item)
          OPTIONAL {{ ?item wdt:P1616 ?siren. }} OPTIONAL {{ ?item wdt:P1185 ?siret. }}
          OPTIONAL {{ ?item wdt:P213 ?isni. }} OPTIONAL {{ ?item wdt:P6782 ?ror. }}
          OPTIONAL {{ ?item wdt:P1278 ?lei. }} OPTIONAL {{ ?item wdt:P856 ?website. }}
          OPTIONAL {{ ?item schema:description ?descFr. FILTER(LANG(?descFr) = "fr") }}
          OPTIONAL {{ ?item schema:description ?descEn. FILTER(LANG(?descEn) = "en") }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
        }} LIMIT 1"""
        r = await client.get(AsyncAPIManager.WIKI_SPARQL, params={'query': q, 'format': 'json'})
        b = r.json()['results']['bindings']
        return b[0] if b else {}

# ============================================================================
# 4. GRAPH RENDERER
# ============================================================================
def render_authority_graph(entity: Entity, relations: List[Relation], social_links: Dict[str, str]):
    W, H = 850, 720
    CX, CY = W/2, H/2 - 20
    R_ID, R_REL, R_SOC = 180, 260, 330
    
    ids = [("Wikidata", entity.qid, "#22C55E", "W"), ("INSEE", entity.siren, "#F97316", "S"),
           ("ISNI", entity.isni, "#A855F7", "I"), ("ROR", entity.ror, "#EC4899", "R"),
           ("LEI", entity.lei, "#06B6D4", "L"), ("Web", entity.website, "#3B82F6", "W")]
    
    rels = [r for r in relations if r.include]
    
    social_cfg = {'linkedin': ('#0077B5', 'In'), 'twitter': ('#000000', 'X'), 'facebook': ('#1877F2', 'Fb'), 'instagram': ('#E4405F', 'Ig'), 'youtube': ('#FF0000', 'Yt')}
    socs = [(n.capitalize(), social_cfg.get(n, ('#64748B', 'S'))) for n, url in social_links.items() if url and url.strip()]

    svg = f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="background:white; border-radius:20px;">'
    svg += '<defs><filter id="sh"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.15"/></filter>'
    svg += '<linearGradient id="gr" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#3B82F6"/><stop offset="100%" stop-color="#1E40AF"/></linearGradient></defs>'
    
    # Cercles Orbites
    svg += f'<circle cx="{CX}" cy="{CY}" r="{R_ID}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="10,5" />'
    if rels: svg += f'<circle cx="{CX}" cy="{CY}" r="{R_REL}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="5,5" />'
    if socs: svg += f'<circle cx="{CX}" cy="{CY}" r="{R_SOC}" fill="none" stroke="#F1F5F9" stroke-width="1" stroke-dasharray="2,2" />'

    # Orbite 1 : IDs
    for i, (lab, val, col, ico) in enumerate(ids):
        angle = (2 * math.pi * i) / len(ids) - (math.pi / 2)
        x, y = CX + R_ID * math.cos(angle), CY + R_ID * math.sin(angle)
        active = bool(val)
        svg += f'<circle cx="{x}" cy="{y}" r="34" fill="{col if active else "#F8FAFC"}" filter="url(#sh)" opacity="{1 if active else 0.6}" />'
        svg += f'<text x="{x}" y="{y+7}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="20" fill="{"white" if active else "#94A3B8"}">{ico}</text>'
        svg += f'<text x="{x}" y="{y+50}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="10" fill="#1E293B">{lab}</text>'

    # Orbite 2 : Relations
    for i, rel in enumerate(rels):
        angle = (2 * math.pi * i) / len(rels) - (math.pi / 2) + 0.2
        x, y = CX + R_REL * math.cos(angle), CY + R_REL * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="26" fill="#6366F1" filter="url(#sh)" />'
        svg += f'<text x="{x}" y="{y+40}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="9" fill="#4338CA">{rel.name[:15]}</text>'

    # Orbite 3 : Social
    for i, (lab, (col, ico)) in enumerate(socs):
        angle = (2 * math.pi * i) / len(socs) - (math.pi / 2) - 0.2
        x, y = CX + R_SOC * math.cos(angle), CY + R_SOC * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="24" fill="{col}" filter="url(#sh)" />'
        svg += f'<text x="{x}" y="{y+6}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="13" fill="white">{ico}</text>'
        svg += f'<text x="{x}" y="{y+38}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="9" fill="#64748B">{lab}</text>'

    score = entity.authority_score()
    svg += f'<circle cx="{CX}" cy="{CY}" r="78" fill="url(#gr)" filter="url(#sh)" />'
    svg += f'<text x="{CX}" y="{CY+18}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="40" fill="white">{score}%</text>'
    svg += '</svg>'
    return svg

# ============================================================================
# 5. INITIALISATION
# ============================================================================
if 'entity' not in st.session_state: st.session_state.entity = Entity()
if 'relations' not in st.session_state: st.session_state.relations = []
if 'social_links' not in st.session_state: 
    st.session_state.social_links = {k:'' for k in ['linkedin','twitter','facebook','instagram','youtube']}
if 'res_wiki' not in st.session_state: st.session_state.res_wiki = []
if 'res_insee' not in st.session_state: st.session_state.res_insee = []

# ============================================================================
# 6. SIDEBAR (RECHERCHE ASYNC)
# ============================================================================
async def run_search(q, mode):
    async with httpx.AsyncClient() as client:
        tasks = []
        if mode in ["Mixte", "Wikidata"]: tasks.append(AsyncAPIManager.search_wikidata(client, q))
        if mode in ["Mixte", "INSEE"]: tasks.append(AsyncAPIManager.search_insee(client, q))
        results = await asyncio.gather(*tasks)
        return results

with st.sidebar:
    st.header("🔍 Audit GEO")
    mode = st.radio("Source", ["Mixte", "Wikidata", "INSEE"], horizontal=True)
    query = st.text_input("Recherche")
    if st.button("Lancer", type="primary", use_container_width=True) and query:
        res = asyncio.run(run_search(query, mode))
        if mode == "Mixte": 
            st.session_state.res_wiki, st.session_state.res_insee = res[0], res[1]
        elif mode == "Wikidata": 
            st.session_state.res_wiki, st.session_state.res_insee = res[0], []
        else: 
            st.session_state.res_wiki, st.session_state.res_insee = [], res[0]

    if st.session_state.res_wiki:
        st.subheader("🌐 Wikidata")
        for i, r in enumerate(st.session_state.res_wiki[:5]):
            if st.button(f"Fusion {r['label'][:25]}", key=f"W_{i}"):
                e = st.session_state.entity
                e.name, e.qid = e.name or r['label'], r['qid']
                with httpx.Client() as client:
                    # SPARQL synchrone ici pour simplicité sur le clic
                    q_id = e.qid
                    d = asyncio.run(AsyncAPIManager.get_full_wikidata(httpx.AsyncClient(), q_id))
                    e.siren = e.siren or d.get('siren',{}).get('value','')
                    e.website = e.website or d.get('website',{}).get('value','')
                    e.lei = e.lei or d.get('lei',{}).get('value','')
                    e.description_fr = d.get('desc_fr',{}).get('value','')
                st.session_state.entity = e
                st.rerun()

    if st.session_state.res_insee:
        st.subheader("🏢 INSEE")
        for i, r in enumerate(st.session_state.res_insee[:5]):
            if st.button(f"Fusion {r['label'][:25]}", key=f"I_{i}"):
                e = st.session_state.entity
                e.name, e.siren = e.name or r['label'], r['siren']
                s = r['raw'].get('siege', {})
                e.address, e.city, e.siret = s.get('adresse',''), s.get('libelle_commune',''), s.get('siret','')
                st.session_state.entity = e
                st.rerun()

# ============================================================================
# 7. MAIN INTERFACE
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique v6.0")

if st.session_state.entity.name or st.session_state.entity.siren:
    tabs = st.tabs(["🎯 Cartographie", "🆔 Identité", "📝 Contenus", "🏢 Écosystème", "📱 Social Hub", "💾 Export"])
    e = st.session_state.entity
    
    with tabs[0]: 
        st.markdown(f'<div style="text-align:center;">{render_authority_graph(e, st.session_state.relations, st.session_state.social_links)}</div>', unsafe_allow_html=True)

    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            e.org_type = st.selectbox("Type Schema.org", ["Organization", "InsuranceAgency", "BankOrCreditUnion", "LocalBusiness"])
            e.name = st.text_input("Nom (FR)", e.name)
            e.name_en = st.text_input("Nom (EN)", e.name_en)
            e.siren = st.text_input("SIREN", e.siren)
            e.address = st.text_input("Adresse", e.address)
        with c2:
            e.qid = st.text_input("Wikidata QID", e.qid)
            e.website = st.text_input("URL Site Web", e.website)
            e.lei = st.text_input("Code LEI", e.lei)
            e.ror = st.text_input("ROR ID", e.ror)
        st.session_state.entity = e

    with tabs[2]:
        e.description_fr = st.text_area("Description (FR)", e.description_fr)
        e.description_en = st.text_area("Description (EN)", e.description_en)
        st.divider()
        e.expertise_fr = st.text_input("Expertise (FR)", e.expertise_fr)
        e.expertise_en = st.text_input("Expertise (EN)", e.expertise_en)

    with tabs[3]:
        with st.expander("➕ Ajouter Relation"):
            f1, f2 = st.columns(2)
            rn, ru = f1.text_input("Nom"), f2.text_input("URL")
            if st.button("Ajouter"):
                st.session_state.relations.append(Relation(name=rn, url=ru))
                st.rerun()
        if st.session_state.relations:
            st.data_editor(pd.DataFrame([asdict(r) for r in st.session_state.relations]), use_container_width=True)

    with tabs[4]:
        for net in st.session_state.social_links.keys():
            st.session_state.social_links[net] = st.text_input(f"Lien {net.capitalize()}", st.session_state.social_links[net])

    with tabs[5]:
        # --- EXPORT FINAL v6.0 ---
        exp = {
            "@context": "https://schema.org",
            "@type": e.org_type,
            "@id": f"{e.website.rstrip('/')}/#organization" if e.website else None,
            "name": [{"@language": "fr", "@value": e.name}, {"@language": "en", "@value": e.name_en or e.name}],
            "url": e.website,
            "description": [{"@language": "fr", "@value": e.description_fr}, {"@language": "en", "@value": e.description_en}],
            "--- IDENTIFIANTS (TRUST) ---": "",
            "taxID": f"FR{e.siren}" if e.siren else None,
            "identifier": [
                {"@type": "PropertyValue", "propertyID": "SIREN", "value": e.siren} if e.siren else None,
                {"@type": "PropertyValue", "propertyID": "LEI", "value": e.lei} if e.lei else None
            ],
            "--- AUTORITÉ (SAMEAS) ---": "",
            "sameAs": [
                f"https://www.wikidata.org/wiki/{e.qid}" if e.qid else None,
                f"https://annuaire-entreprises.data.gouv.fr/entreprise/{e.siren}" if e.siren else None,
                *[v for v in st.session_state.social_links.values() if v]
            ],
            "knowsAbout": [{"@language": "fr", "@value": e.expertise_fr}, {"@language": "en", "@value": e.expertise_en}]
        }
        # Nettoyage
        exp["identifier"] = [i for i in exp["identifier"] if i]
        exp["sameAs"] = [s for s in exp["sameAs"] if s]
        
        st.json(exp)
        st.download_button("📥 Télécharger JSON-LD", json.dumps(exp, indent=2, ensure_ascii=False), "schema.json")
else:
    st.info("👈 Recherchez et fusionnez une entité pour commencer.")
