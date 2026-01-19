"""
🛡️ Architecte d'Autorité Sémantique v4.9 (Master JSON-LD)
------------------------------------------------------------------
- Export JSON-LD multilingue (FR/EN) conforme au format optimal.
- Gestion du taxID, leiCode et knowsAbout.
- Fusion intelligente Wikidata/INSEE.
- Graphique 3-Orbites avec labels explicites.
"""

import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import time
import math

# ============================================================================
# CONFIGURATION & STYLE
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
</style>
""", unsafe_allow_html=True)

# ============================================================================
# DATA MODELS
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
    creation_date: str = ""
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
    qid: str
    name: str
    url: str = ""
    relation_type: str = "lié"
    schema_type: str = "Organization"
    include: bool = True

# ============================================================================
# API MANAGER
# ============================================================================
class APIManager:
    WIKIDATA_API = "https://www.wikidata.org/w/api.php"
    WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
    INSEE_API = "https://recherche-entreprises.api.gouv.fr/search"
    HEADERS = {"User-Agent": "SemanticAuthority/4.9", "Accept": "application/json"}

    @st.cache_data(ttl=3600, show_spinner=False)
    def search_wikidata(_self, query: str) -> List[Dict]:
        try:
            p = {"action": "wbsearchentities", "search": query, "language": "fr", "format": "json", "limit": 10}
            r = requests.get(_self.WIKIDATA_API, params=p, headers=_self.HEADERS)
            return [{'qid': i['id'], 'label': i.get('label', ''), 'description': i.get('description', '')} for i in r.json().get('search', [])]
        except: return []

    @st.cache_data(ttl=1800, show_spinner=False)
    def search_insee(_self, query: str) -> List[Dict]:
        try:
            r = requests.get(_self.INSEE_API, params={"q": query, "per_page": 10})
            return r.json().get('results', [])
        except: return []

    @st.cache_data(ttl=3600, show_spinner=False)
    def get_wikidata_entity(_self, qid: str) -> Dict:
        q = f"""SELECT ?siren ?siret ?isni ?ror ?lei ?website ?inception ?hqLabel ?descFr ?descEn WHERE {{
          BIND(wd:{qid} AS ?item)
          OPTIONAL {{ ?item wdt:P1616 ?siren. }} OPTIONAL {{ ?item wdt:P1185 ?siret. }}
          OPTIONAL {{ ?item wdt:P213 ?isni. }} OPTIONAL {{ ?item wdt:P6782 ?ror. }}
          OPTIONAL {{ ?item wdt:P1278 ?lei. }} OPTIONAL {{ ?item wdt:P856 ?website. }}
          OPTIONAL {{ ?item wdt:P571 ?inception. }} OPTIONAL {{ ?item wdt:P159 ?hq. }}
          OPTIONAL {{ 
            ?item schema:description ?descFr.
            FILTER(LANG(?descFr) = "fr")
          }}
          OPTIONAL {{ 
            ?item schema:description ?descEn.
            FILTER(LANG(?descEn) = "en")
          }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
        }} LIMIT 1"""
        try:
            r = requests.get(_self.WIKIDATA_SPARQL, params={'query': q, 'format': 'json'}, timeout=10)
            b = r.json()['results']['bindings'][0]
            return {
                'siren': b.get('siren', {}).get('value', ''), 'siret': b.get('siret', {}).get('value', ''),
                'isni': b.get('isni', {}).get('value', ''), 'ror': b.get('ror', {}).get('value', ''),
                'lei': b.get('lei', {}).get('value', ''), 'website': b.get('website', {}).get('value', ''),
                'inception': b.get('inception', {}).get('value', ''), 'headquarters': b.get('hqLabel', {}).get('value', ''),
                'desc_fr': b.get('descFr', {}).get('value', ''), 'desc_en': b.get('descEn', {}).get('value', '')
            }
        except: return {}

# ============================================================================
# GRAPH RENDERER
# ============================================================================
def render_authority_graph(entity: Entity, relations: List[Relation], social_links: Dict[str, str]):
    W, H = 850, 700
    CX, CY = W/2, H/2 - 20
    R_ID, R_REL, R_SOC = 180, 255, 320
    
    ids = [("Wikidata", entity.qid, "#22C55E", "W"), ("INSEE", entity.siren, "#F97316", "S"),
           ("ISNI", entity.isni, "#A855F7", "I"), ("ROR", entity.ror, "#EC4899", "R"),
           ("LEI", entity.lei, "#06B6D4", "L"), ("Web", entity.website, "#3B82F6", "W")]
    
    rels_to_draw = [r for r in relations if r.include]
    socs = [(n.capitalize(), url) for n, url in social_links.items() if url and url.strip()]

    svg = f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="background:white; border-radius:20px;">'
    svg += '<defs><filter id="sh"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.15"/></filter>'
    svg += '<linearGradient id="gr" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#3B82F6"/><stop offset="100%" stop-color="#1E40AF"/></linearGradient></defs>'
    
    svg += f'<circle cx="{CX}" cy="{CY}" r="{R_ID}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="10,5" />'
    if rels_to_draw: svg += f'<circle cx="{CX}" cy="{CY}" r="{R_REL}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="5,5" />'
    if socs: svg += f'<circle cx="{CX}" cy="{CY}" r="{R_SOC}" fill="none" stroke="#F1F5F9" stroke-width="1" stroke-dasharray="2,2" />'

    for i, (lab, val, col, ico) in enumerate(ids):
        angle = (2 * math.pi * i) / len(ids) - (math.pi / 2)
        x, y = CX + R_ID * math.cos(angle), CY + R_ID * math.sin(angle)
        active = bool(val)
        svg += f'<circle cx="{x}" cy="{y}" r="34" fill="{col if active else "#F8FAFC"}" filter="url(#sh)" opacity="{1 if active else 0.6}" />'
        svg += f'<text x="{x}" y="{y+7}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="20" fill="{"white" if active else "#94A3B8"}">{ico}</text>'
        svg += f'<text x="{x}" y="{y+50}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="10" fill="#1E293B">{lab}</text>'

    for i, rel in enumerate(rels_to_draw):
        angle = (2 * math.pi * i) / len(rels_to_draw) - (math.pi / 2) + 0.2
        x, y = CX + R_REL * math.cos(angle), CY + R_REL * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="26" fill="#6366F1" filter="url(#sh)" />'
        svg += f'<text x="{x}" y="{y+40}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="9" fill="#4338CA">{rel.name[:15]}</text>'

    for i, (lab, url) in enumerate(socs):
        angle = (2 * math.pi * i) / len(socs) - (math.pi / 2) - 0.2
        x, y = CX + R_SOC * math.cos(angle), CY + R_SOC * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="24" fill="#000" filter="url(#sh)" />'
        svg += f'<text x="{x}" y="{y+38}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="9" fill="#64748B">{lab}</text>'

    score = entity.authority_score()
    svg += f'<circle cx="{CX}" cy="{CY}" r="78" fill="url(#gr)" filter="url(#sh)" />'
    svg += f'<text x="{CX}" y="{CY+15}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="38" fill="white">{score}%</text>'
    svg += '</svg>'
    return svg

# ============================================================================
# INITIALISATION
# ============================================================================
api = APIManager()
if 'entity' not in st.session_state: st.session_state.entity = Entity()
if 'relations' not in st.session_state: st.session_state.relations = []
if 'social_links' not in st.session_state: st.session_state.social_links = {k:'' for k in ['linkedin','twitter','facebook','instagram','youtube']}
if 'res_wiki' not in st.session_state: st.session_state.res_wiki = []
if 'res_insee' not in st.session_state: st.session_state.res_insee = []

# ============================================================================
# SIDEBAR
# ============================================================================
with st.sidebar:
    st.header("🔍 Audit Sémantique")
    src = st.radio("Source", ["Mixte", "Wikidata", "INSEE"], horizontal=True)
    q = st.text_input("Rechercher...")
    
    if st.button("Lancer l'audit", type="primary", use_container_width=True) and q:
        with st.spinner("Audit des bases..."):
            st.session_state.res_wiki = api.search_wikidata(q) if src in ["Mixte", "Wikidata"] else []
            st.session_state.res_insee = api.search_insee(q) if src in ["Mixte", "INSEE"] else []

    if st.session_state.res_wiki:
        st.markdown("**🌐 Wikidata**")
        for i, res in enumerate(st.session_state.res_wiki[:5]):
            if st.button(f"Fusionner {res['label'][:35]}", key=f"W_{i}", use_container_width=True):
                e = st.session_state.entity
                e.name = e.name or res['label']
                e.qid = res['qid']
                d = api.get_wikidata_entity(e.qid)
                e.siren = e.siren or d.get('siren','')
                e.website = e.website or d.get('website','')
                e.isni = e.isni or d.get('isni','')
                e.ror = e.ror or d.get('ror','')
                e.lei = e.lei or d.get('lei','')
                e.description_fr = e.description_fr or d.get('desc_fr','')
                e.description_en = e.description_en or d.get('desc_en','')
                st.session_state.entity = e
                st.rerun()

    if st.session_state.res_insee:
        st.markdown("**🏛️ INSEE**")
        for i, res in enumerate(st.session_state.res_insee[:5]):
            if st.button(f"Fusionner {res.get('nom_complet','')[:35]}", key=f"I_{i}", use_container_width=True):
                e = st.session_state.entity
                e.name = e.name or res.get('nom_complet','')
                e.siren = res.get('siren','')
                s = res.get('siege', {})
                e.address, e.postal_code, e.city = s.get('adresse', ''), s.get('code_postal', ''), s.get('libelle_commune', '')
                e.siret, e.ape = s.get('siret', ''), res.get('activite_principale', '')
                st.session_state.entity = e
                st.rerun()

# ============================================================================
# MAIN INTERFACE
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique")

if st.session_state.entity.name or st.session_state.entity.siren:
    st.success(f"Dossier Client chargé : **{st.session_state.entity.name}**")
    tabs = st.tabs(["🎯 Cartographie", "🆔 Identité & Légal", "📝 Descriptions", "🏢 Écosystème", "📱 Social Hub", "💾 Export"])
    
    with tabs[0]: # CARTO
        st.markdown(f'<div style="text-align:center;">{render_authority_graph(st.session_state.entity, st.session_state.relations, st.session_state.social_links)}</div>', unsafe_allow_html=True)

    with tabs[1]: # IDENTITE
        e = st.session_state.entity
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🏢 Identité Légale")
            e.org_type = st.selectbox("Type Schema.org", ["Organization", "InsuranceAgency", "LocalBusiness", "NGO"], index=0)
            e.name = st.text_input("Nom (FR)", e.name)
            e.name_en = st.text_input("Nom (EN)", e.name_en)
            e.siren = st.text_input("SIREN", e.siren)
            e.siret = st.text_input("SIRET", e.siret)
            e.address = st.text_input("Adresse", e.address)
            cx = st.columns(2)
            e.postal_code = cx[0].text_input("CP", e.postal_code)
            e.city = cx[1].text_input("Ville", e.city)
        with c2:
            st.markdown("##### 🌐 Identité Sémantique")
            e.qid = st.text_input("QID Wikidata", e.qid)
            e.website = st.text_input("URL Officielle", e.website)
            e.isni = st.text_input("ISNI", e.isni)
            e.ror = st.text_input("ROR", e.ror)
            e.lei = st.text_input("LEI", e.lei)
        st.session_state.entity = e

    with tabs[2]: # DESCRIPTIONS & EXPERTISE
        st.markdown("##### 📝 Contenu Multilingue & Expertise")
        e.description_fr = st.text_area("Description (FR)", e.description_fr, height=100)
        e.description_en = st.text_area("Description (EN)", e.description_en, height=100)
        st.divider()
        e.expertise_fr = st.text_input("Expertise / KnowsAbout (FR) - séparer par virgule", e.expertise_fr)
        e.expertise_en = st.text_input("Expertise / KnowsAbout (EN) - séparer par virgule", e.expertise_en)
        st.session_state.entity = e

    with tabs[3]: # ECO
        st.markdown("##### 🏢 Relations & Filiales")
        with st.expander("➕ Déclarer une nouvelle relation"):
            f1, f2, f3 = st.columns([2, 1, 1])
            new_n = f1.text_input("Nom")
            new_u = f2.text_input("URL / Wikidata")
            new_t = f3.selectbox("Type", ["Organization", "InsuranceAgency", "LocalBusiness"])
            if st.button("Ajouter"):
                st.session_state.relations.append(Relation(qid="", name=new_n, url=new_u, schema_type=new_t))
                st.rerun()
        if st.session_state.relations:
            df = pd.DataFrame([asdict(r) for r in st.session_state.relations])
            edited = st.data_editor(df, use_container_width=True, hide_index=True)

    with tabs[4]: # SOCIAL
        sc1, sc2 = st.columns(2)
        for i, net in enumerate(st.session_state.social_links.keys()):
            with (sc1 if i % 2 == 0 else sc2):
                st.session_state.social_links[net] = st.text_input(f"Lien {net.capitalize()}", st.session_state.social_links[net])

    with tabs[5]: # EXPORT JSON-LD OPTIMAL
        # --- LOGIQUE EXPORT MASTER v4.9 ---
        exp = {
            "@context": "https://schema.org",
            "@type": e.org_type,
            "@id": f"{e.website.rstrip('/')}/#organization" if e.website else None,
            "name": [
                {"@language": "fr", "@value": e.name},
                {"@language": "en", "@value": e.name_en or e.name}
            ],
            "url": e.website,
            "description": [
                {"@language": "fr", "@value": e.description_fr},
                {"@language": "en", "@value": e.description_en}
            ],
            
            "--- IDENTIFIANTS OFFICIELS (TRUST) ---": "",
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
            
            "--- EXPERTISE MAPPÉE (GEO CORE) ---": "",
            "knowsAbout": [
                {"@language": "fr", "@value": e.expertise_fr},
                {"@language": "en", "@value": e.expertise_en}
            ]
        }
        
        # Nettoyage des None et listes vides
        exp["identifier"] = [i for i in exp["identifier"] if i]
        exp["sameAs"] = [s for s in exp["sameAs"] if s]
        
        # Ajout Organigramme
        rels = [r for r in st.session_state.relations if r.include]
        if rels:
            exp["--- ORGANIGRAMME (CORRIGÉ) ---"] = ""
            exp["subOrganization"] = [
                {"@type": r.schema_type, "name": r.name, "url": r.url if "http" in r.url else None, "sameAs": r.url if "wikidata" in r.url else None}
                for r in rels
            ]
            # Nettoyage des sous-org
            for s in exp["subOrganization"]:
                if not s["url"]: del s["url"]
                if not s["sameAs"]: del s["sameAs"]

        st.json(exp)
        st.download_button("📥 Télécharger JSON-LD OPTIMAL", json.dumps(exp, indent=2, ensure_ascii=False), f"schema_{e.name}.json", "application/ld+json")
else:
    st.info("👈 Recherchez une entité pour démarrer l'audit.")
