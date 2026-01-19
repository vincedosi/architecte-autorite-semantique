"""
🛡️ Architecte d'Autorité Sémantique v7.1 (Persistence & Sidebar Master)
------------------------------------------------------------------
- Persistence : Chargement de config JSON directement en Sidebar avec fix de rafraîchissement.
- Sécurité : Mot de passe (SEOTOOLS).
- IA : Intégration Mistral AI pour GEO (Generative Engine Optimization).
- Graphique : 3 Orbites dynamiques avec labels explicites.
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
# 1. CONFIGURATION & MODELS
# ============================================================================
st.set_page_config(
    page_title="Architecte d'Autorité Sémantique",
    page_icon="🛡️",
    layout="wide"
)

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
# 2. INITIALISATION SESSION & AUTHENTIFICATION
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
    pwd = st.text_input("Mot de passe :", type="password")
    if st.button("Se connecter"):
        if pwd == "SEOTOOLS":
            st.session_state.authenticated = True
            st.rerun()
        else: st.error("Accès refusé.")
    return False

if not check_password(): st.stop()

# ============================================================================
# 3. MOTEUR IA & API ASYNC
# ============================================================================
class MistralManager:
    @staticmethod
    async def generate_content(api_key: str, entity: Entity):
        prompt = f"""Expert SEO Sémantique. Génère JSON pour l'entreprise {entity.name} (SIREN: {entity.siren}).
        Format: {{"desc_fr": "...", "desc_en": "...", "expertise_fr": "A, B, C", "expertise_en": "D, E, F"}}"""
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(
                    "https://api.mistral.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
                    timeout=30.0
                )
                return json.loads(r.json()['choices'][0]['message']['content']) if r.status_code == 200 else None
            except: return None

# ============================================================================
# 4. SIDEBAR : RECHERCHE + CHARGEMENT CONFIG (FIXED)
# ============================================================================
with st.sidebar:
    st.title("🛡️ AAS v7.1")
    
    # --- SECTION CHARGEMENT ---
    st.subheader("📥 Charger une Config")
    uploaded_cfg = st.file_uploader("Importer JSON", type="json", label_visibility="collapsed")
    if uploaded_cfg:
        try:
            data = json.load(uploaded_cfg)
            st.session_state.entity = Entity(**data['entity'])
            st.session_state.relations = [Relation(**r) for r in data.get('relations', [])]
            st.session_state.social_links.update(data.get('social_links', {}))
            st.success("Configuration chargée !")
            st.rerun() # Crucial pour remplir les champs
        except Exception as e:
            st.error(f"Erreur JSON : {e}")

    st.divider()
    
    # --- SECTION MISTRAL ---
    st.session_state.mistral_key = st.text_input("Clé API Mistral AI", value=st.session_state.mistral_key, type="password")
    
    st.divider()
    
    # --- SECTION RECHERCHE ---
    st.subheader("🔍 Recherche")
    q = st.text_input("Nom de l'organisation")
    if st.button("Lancer l'audit", type="primary", use_container_width=True) and q:
        with st.spinner("Audit en cours..."):
            try:
                r = requests.get(f"https://recherche-entreprises.api.gouv.fr/search?q={q}&per_page=1").json()['results'][0]
                e = st.session_state.entity
                e.name, e.siren = r['nom_complet'], r['siren']
                s = r.get('siege', {})
                e.address, e.city, e.postal_code = s.get('adresse',''), s.get('libelle_commune',''), s.get('code_postal','')
                e.siret, e.ape = s.get('siret',''), r.get('activite_principale','')
                st.session_state.entity = e
                st.rerun()
            except: st.error("Organisation non trouvée.")

    st.divider()
    if st.button("🗑️ Reset Complet", use_container_width=True):
        st.session_state.entity = Entity()
        st.session_state.relations = []
        st.session_state.social_links = {k:'' for k in st.session_state.social_links}
        st.rerun()

# ============================================================================
# 5. GRAPH RENDERER
# ============================================================================
def render_graph(entity, relations, socials):
    W, H = 850, 720
    CX, CY = W/2, H/2 - 20
    R_ID, R_REL, R_SOC = 180, 260, 330
    
    ids = [("Wikidata", entity.qid, "#22C55E", "W"), ("INSEE", entity.siren, "#F97316", "S"),
           ("ISNI", entity.isni, "#A855F7", "I"), ("ROR", entity.ror, "#EC4899", "R"),
           ("LEI", entity.lei, "#06B6D4", "L"), ("Web", entity.website, "#3B82F6", "W")]
    
    rel_active = [r for r in relations if r.include]
    cfg_soc = {'linkedin': ('#0077B5', 'In'), 'twitter': ('#000', 'X'), 'facebook': ('#1877F2', 'Fb'), 'instagram': ('#E4405F', 'Ig'), 'youtube': ('#FF0000', 'Yt')}
    soc_active = [(n.capitalize(), cfg_soc.get(n, ('#64748B', 'S'))) for n, url in socials.items() if url and url.strip()]

    svg = f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="background:white; border-radius:20px;">'
    svg += f'<circle cx="{CX}" cy="{CY}" r="{R_ID}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="10,5" />'
    
    # IDs Orbit
    for i, (lab, val, col, ico) in enumerate(ids):
        angle = (2 * math.pi * i) / len(ids) - (math.pi / 2)
        x, y = CX + R_ID * math.cos(angle), CY + R_ID * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="34" fill="{col if val else "#F8FAFC"}" opacity="{1 if val else 0.4}" />'
        svg += f'<text x="{x}" y="{y+7}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="20" fill="{"white" if val else "#94A3B8"}">{ico}</text>'
        svg += f'<text x="{x}" y="{y+50}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="10" fill="#1E293B">{lab}</text>'

    # Social Orbit
    for i, (lab, (col, ico)) in enumerate(soc_active):
        angle = (2 * math.pi * i) / len(soc_active) - (math.pi / 2) - 0.2
        x, y = CX + R_SOC * math.cos(angle), CY + R_SOC * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="24" fill="{col}" />'
        svg += f'<text x="{x}" y="{y+6}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="13" fill="white">{ico}</text>'
        svg += f'<text x="{x}" y="{y+40}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="9" fill="#64748B">{lab}</text>'

    # Centre
    score = entity.authority_score()
    svg += f'<circle cx="{CX}" cy="{CY}" r="78" fill="navy" />'
    svg += f'<text x="{CX}" y="{CY+15}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="38" fill="white">{score}%</text>'
    svg += '</svg>'
    return svg

# ============================================================================
# 8. MAIN UI
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique")

if st.session_state.entity.name:
    tabs = st.tabs(["🎯 Carte", "🆔 Identité", "📝 IA Magic", "🏢 Écosystème", "📱 Social", "💾 Export"])
    e = st.session_state.entity
    
    with tabs[0]: st.markdown(f'<div style="text-align:center;">{render_graph(e, st.session_state.relations, st.session_state.social_links)}</div>', unsafe_allow_html=True)

    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            e.org_type = st.selectbox("Type Schema", ["Organization", "InsuranceAgency", "BankOrCreditUnion"], index=0)
            e.name = st.text_input("Nom (FR)", e.name)
            e.name_en = st.text_input("Nom (EN)", e.name_en)
            e.siren = st.text_input("SIREN", e.siren)
            e.address = st.text_input("Adresse", e.address)
        with c2:
            e.qid = st.text_input("Wikidata", e.qid)
            e.website = st.text_input("URL Site", e.website)
            e.lei = st.text_input("LEI", e.lei)
            e.isni = st.text_input("ISNI", e.isni)
        st.session_state.entity = e

    with tabs[2]:
        st.markdown("### 🪄 Mistral AI GEO Optimizer")
        if st.button("Lancer la génération IA", use_container_width=True):
            content = asyncio.run(MistralManager.generate_content(st.session_state.mistral_key, e))
            if content:
                e.description_fr, e.description_en = content['desc_fr'], content['desc_en']
                e.expertise_fr, e.expertise_en = content['expertise_fr'], content['expertise_en']
                st.rerun()
        c1, c2 = st.columns(2)
        e.description_fr = c1.text_area("Desc FR", e.description_fr)
        e.description_en = c2.text_area("Desc EN", e.description_en)
        e.expertise_fr = c1.text_input("Expertise FR", e.expertise_fr)
        e.expertise_en = c2.text_input("Expertise EN", e.expertise_en)

    with tabs[3]:
        with st.expander("➕ Ajouter Filiale"):
            f1, f2 = st.columns(2)
            fn = f1.text_input("Nom")
            if st.button("Ajouter"):
                st.session_state.relations.append(Relation(name=fn))
                st.rerun()
        if st.session_state.relations:
            st.data_editor(pd.DataFrame([asdict(r) for r in st.session_state.relations]), use_container_width=True)

    with tabs[4]:
        sc1, sc2 = st.columns(2)
        for i, net in enumerate(st.session_state.social_links.keys()):
            with (sc1 if i % 2 == 0 else sc2):
                st.session_state.social_links[net] = st.text_input(f"Lien {net.capitalize()}", st.session_state.social_links[net])

    with tabs[5]:
        # EXPORT CONFIG (JSON)
        config_data = {"entity": asdict(e), "relations": [asdict(r) for r in st.session_state.relations], "social_links": st.session_state.social_links}
        st.download_button("💾 Sauvegarder la Config", json.dumps(config_data, indent=2, ensure_ascii=False), f"config_{e.name}.json")
        
        # EXPORT JSON-LD SEO
        json_ld = {
            "@context": "https://schema.org", "@type": e.org_type,
            "@id": f"{e.website}/#organization",
            "name": [{"@language": "fr", "@value": e.name}, {"@language": "en", "@value": e.name_en or e.name}],
            "description": [{"@language": "fr", "@value": e.description_fr}, {"@language": "en", "@value": e.description_en}],
            "taxID": f"FR{e.siren}",
            "identifier": [{"@type": "PropertyValue", "propertyID": "SIREN", "value": e.siren}],
            "sameAs": [f"https://www.wikidata.org/wiki/{e.qid}" if e.qid else None] + [v for v in st.session_state.social_links.values() if v],
            "knowsAbout": [{"@language": "fr", "@value": e.expertise_fr}, {"@language": "en", "@value": e.expertise_en}]
        }
        st.json(json_ld)
else:
    st.info("👈 Utilisez la barre latérale pour charger un dossier ou faire une recherche.")
