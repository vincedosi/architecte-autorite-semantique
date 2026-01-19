"""
🛡️ Architecte d'Autorité Sémantique v9.2
=========================================
BANDEAU VERSION ULTRA VISIBLE + LOGS TEMPS RÉEL
"""

import streamlit as st
import requests
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Dict
from datetime import datetime

# ============================================================================
# ⚠️ VERSION - MODIFIER ICI POUR VÉRIFIER LE DÉPLOIEMENT
# ============================================================================
VERSION = "9.2.0"
BUILD_DATE = "2025-01-19"
BUILD_ID = "BUILD-2025JAN19-1530"  # Change ce ID à chaque push

# ============================================================================
# CONFIG
# ============================================================================
st.set_page_config(
    page_title=f"AAS v{VERSION}",
    page_icon="🛡️",
    layout="wide"
)

# ============================================================================
# 🚨 BANDEAU VERSION ULTRA VISIBLE 🚨
# ============================================================================
st.markdown(f"""
<div style="
    background: linear-gradient(90deg, #FF6B6B, #4ECDC4);
    color: white;
    padding: 15px 25px;
    border-radius: 10px;
    margin-bottom: 20px;
    text-align: center;
    font-size: 18px;
    font-weight: bold;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
">
    🛡️ AAS VERSION {VERSION} | Build: {BUILD_ID} | Date: {BUILD_DATE}
</div>
""", unsafe_allow_html=True)

# ============================================================================
# SESSION STATE
# ============================================================================
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'entity' not in st.session_state:
    st.session_state.entity = None
if 'wiki_results' not in st.session_state:
    st.session_state.wiki_results = []
if 'insee_results' not in st.session_state:
    st.session_state.insee_results = []
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'mistral_key' not in st.session_state:
    st.session_state.mistral_key = ''


def log(msg: str, level: str = "INFO"):
    """Log avec timestamp."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    icons = {"INFO": "ℹ️", "OK": "✅", "ERROR": "❌", "WARN": "⚠️", "HTTP": "🌐", "DEBUG": "🔧"}
    entry = f"{icons.get(level, '•')} [{ts}] {msg}"
    st.session_state.logs.append(entry)
    if len(st.session_state.logs) > 100:
        st.session_state.logs = st.session_state.logs[-100:]


# ============================================================================
# DATA CLASS
# ============================================================================
@dataclass
class Entity:
    name: str = ""
    name_en: str = ""
    legal_name: str = ""
    description_fr: str = ""
    description_en: str = ""
    expertise_fr: str = ""
    qid: str = ""
    siren: str = ""
    siret: str = ""
    lei: str = ""
    website: str = ""
    org_type: str = "Organization"
    parent_org_name: str = ""
    parent_org_qid: str = ""
    address: str = ""

    def score(self) -> int:
        s = 0
        if self.qid: s += 25
        if self.siren: s += 25
        if self.lei: s += 15
        if self.website: s += 15
        if self.parent_org_qid: s += 20
        return min(s, 100)


if st.session_state.entity is None:
    st.session_state.entity = Entity()


# ============================================================================
# WIKIDATA API
# ============================================================================
def wikidata_search(query: str) -> List[Dict]:
    """Recherche Wikidata avec logs."""
    
    log(f"{'='*50}", "INFO")
    log(f"WIKIDATA SEARCH: '{query}'", "INFO")
    log(f"Version: {VERSION} | Build: {BUILD_ID}", "DEBUG")
    
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": query,
        "language": "fr",
        "uselang": "fr",
        "format": "json",
        "limit": 10,
        "type": "item",
        "origin": "*"
    }
    
    headers = {
        "User-Agent": f"AAS-Bot/{VERSION} (Streamlit Cloud; contact@example.com)",
        "Accept": "application/json"
    }
    
    log(f"URL: {url}", "DEBUG")
    log(f"Params: action=wbsearchentities, search={query}", "DEBUG")
    
    for attempt in range(3):
        try:
            log(f"Tentative {attempt+1}/3...", "HTTP")
            
            t0 = time.time()
            response = requests.get(url, params=params, headers=headers, timeout=30)
            elapsed = round(time.time() - t0, 2)
            
            log(f"HTTP {response.status_code} en {elapsed}s", "HTTP")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'search' in data:
                    results = data['search']
                    log(f"✅ {len(results)} résultats trouvés!", "OK")
                    
                    for item in results[:3]:
                        log(f"  → {item['id']}: {item.get('label', '?')}", "DEBUG")
                    
                    return [{
                        'qid': item['id'],
                        'label': item.get('label', item['id']),
                        'desc': item.get('description', '')
                    } for item in results]
                else:
                    log(f"❌ Pas de 'search' dans réponse", "ERROR")
                    log(f"Clés: {list(data.keys())}", "DEBUG")
                    if 'error' in data:
                        log(f"API Error: {data['error']}", "ERROR")
                    return []
            
            elif response.status_code == 429:
                wait = 2 ** attempt
                log(f"Rate limit 429 - Attente {wait}s", "WARN")
                time.sleep(wait)
                continue
            
            else:
                log(f"❌ HTTP {response.status_code}", "ERROR")
                log(f"Response: {response.text[:200]}", "DEBUG")
                
        except requests.Timeout:
            log(f"⏱️ TIMEOUT 30s (tentative {attempt+1})", "ERROR")
            if attempt < 2:
                time.sleep(2)
                continue
        except requests.ConnectionError as e:
            log(f"🔌 CONNECTION ERROR: {str(e)[:80]}", "ERROR")
        except Exception as e:
            log(f"💥 EXCEPTION: {type(e).__name__}: {str(e)[:80]}", "ERROR")
    
    log(f"❌ ÉCHEC après 3 tentatives", "ERROR")
    return []


def wikidata_get_entity(qid: str) -> Dict:
    """Récupère détails entité."""
    
    log(f"GET ENTITY: {qid}", "INFO")
    
    result = {
        "name_fr": "", "name_en": "", "desc_fr": "",
        "siren": "", "lei": "", "website": "",
        "parent_name": "", "parent_qid": ""
    }
    
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "languages": "fr|en",
        "props": "labels|descriptions|claims",
        "format": "json"
    }
    headers = {"User-Agent": f"AAS-Bot/{VERSION}"}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        log(f"HTTP {response.status_code}", "HTTP")
        
        if response.status_code == 200:
            data = response.json()
            entity = data.get('entities', {}).get(qid, {})
            
            if entity:
                labels = entity.get('labels', {})
                descs = entity.get('descriptions', {})
                claims = entity.get('claims', {})
                
                result["name_fr"] = labels.get('fr', {}).get('value', '')
                result["name_en"] = labels.get('en', {}).get('value', '')
                result["desc_fr"] = descs.get('fr', {}).get('value', '')
                
                log(f"Nom: {result['name_fr']}", "OK")
                log(f"Claims disponibles: {len(claims)}", "DEBUG")
                
                # SIREN P1616
                if 'P1616' in claims:
                    try:
                        result["siren"] = claims['P1616'][0]['mainsnak']['datavalue']['value']
                        log(f"SIREN: {result['siren']}", "OK")
                    except:
                        pass
                
                # LEI P1278
                if 'P1278' in claims:
                    try:
                        result["lei"] = claims['P1278'][0]['mainsnak']['datavalue']['value']
                        log(f"LEI: {result['lei']}", "OK")
                    except:
                        pass
                
                # Website P856
                if 'P856' in claims:
                    try:
                        result["website"] = claims['P856'][0]['mainsnak']['datavalue']['value']
                        log(f"Website: {result['website']}", "OK")
                    except:
                        pass
                
                # Parent P749
                if 'P749' in claims:
                    try:
                        pval = claims['P749'][0]['mainsnak']['datavalue']['value']
                        if isinstance(pval, dict):
                            result["parent_qid"] = pval.get('id', '')
                        log(f"Parent QID: {result['parent_qid']}", "OK")
                        
                        if result["parent_qid"]:
                            # Get parent name
                            p_resp = requests.get(url, params={
                                "action": "wbgetentities",
                                "ids": result["parent_qid"],
                                "languages": "fr|en",
                                "props": "labels",
                                "format": "json"
                            }, headers=headers, timeout=10)
                            if p_resp.status_code == 200:
                                p_data = p_resp.json()
                                p_labels = p_data.get('entities', {}).get(result["parent_qid"], {}).get('labels', {})
                                result["parent_name"] = p_labels.get('fr', {}).get('value', '') or p_labels.get('en', {}).get('value', '')
                                log(f"Parent: {result['parent_name']}", "OK")
                    except Exception as e:
                        log(f"Erreur P749: {e}", "WARN")
                else:
                    log("Pas de Parent (P749)", "DEBUG")
                
                log(f"✅ Entity chargée", "OK")
            else:
                log(f"Entity {qid} non trouvée", "ERROR")
    except Exception as e:
        log(f"Exception: {e}", "ERROR")
    
    return result


def insee_search(query: str) -> List[Dict]:
    """Recherche INSEE."""
    log(f"INSEE SEARCH: '{query}'", "INFO")
    
    try:
        response = requests.get(
            "https://recherche-entreprises.api.gouv.fr/search",
            params={"q": query, "per_page": 10},
            timeout=15
        )
        log(f"INSEE HTTP {response.status_code}", "HTTP")
        
        if response.status_code == 200:
            results = response.json().get('results', [])
            log(f"INSEE: {len(results)} résultats", "OK")
            return [{
                'siren': r.get('siren', ''),
                'name': r.get('nom_complet', ''),
                'address': f"{r.get('siege', {}).get('adresse', '')} {r.get('siege', {}).get('code_postal', '')} {r.get('siege', {}).get('commune', '')}",
                'active': r.get('etat_administratif') == 'A'
            } for r in results]
    except Exception as e:
        log(f"INSEE Error: {e}", "ERROR")
    return []


# ============================================================================
# AUTH
# ============================================================================
if not st.session_state.authenticated:
    st.markdown(f"""
    <div style="text-align: center; padding: 50px;">
        <h1>🔐 Accès Restreint</h1>
        <p style="color: #888;">Version {VERSION} | Build {BUILD_ID}</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Mot de passe:", type="password")
        if st.button("🔓 Déverrouiller", type="primary", use_container_width=True):
            if pwd == "SEOTOOLS":
                st.session_state.authenticated = True
                log("Auth OK", "OK")
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect")
    st.stop()


# ============================================================================
# MAIN LAYOUT
# ============================================================================

# 2 colonnes: Main (gauche) + Logs (droite)
main_col, log_col = st.columns([3, 2])

# ============================================================================
# COLONNE LOGS (DROITE)
# ============================================================================
with log_col:
    st.markdown(f"""
    <div style="
        background: #1E1E1E;
        border: 2px solid #4ECDC4;
        border-radius: 10px;
        padding: 10px;
    ">
        <h3 style="color: #4ECDC4; margin: 0;">📟 Console Logs v{VERSION}</h3>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.logs = []
            st.rerun()
    with c2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    # Affichage logs
    log_box = st.container(height=450)
    with log_box:
        if st.session_state.logs:
            for entry in reversed(st.session_state.logs[-30:]):
                if "ERROR" in entry or "❌" in entry:
                    st.markdown(f"<span style='color:#FF6B6B'>{entry}</span>", unsafe_allow_html=True)
                elif "OK" in entry or "✅" in entry:
                    st.markdown(f"<span style='color:#4ECDC4'>{entry}</span>", unsafe_allow_html=True)
                elif "WARN" in entry or "⚠️" in entry:
                    st.markdown(f"<span style='color:#FFE66D'>{entry}</span>", unsafe_allow_html=True)
                else:
                    st.text(entry)
        else:
            st.info(f"Logs vides. Build: {BUILD_ID}")

# ============================================================================
# COLONNE PRINCIPALE (GAUCHE)
# ============================================================================
with main_col:
    st.subheader("🔍 Recherche")
    
    # Search bar
    search_query = st.text_input("Organisation", placeholder="Ex: Boursorama, IKEA, BNP Paribas...")
    
    src_col, btn_col = st.columns([1, 2])
    with src_col:
        source = st.selectbox("Source", ["Wikidata", "INSEE", "Les deux"], label_visibility="collapsed")
    with btn_col:
        b1, b2, b3 = st.columns(3)
        with b1:
            search_btn = st.button("🔎 Rechercher", type="primary", use_container_width=True)
        with b2:
            test_btn = st.button("🧪 Test API", use_container_width=True)
        with b3:
            reset_btn = st.button("🗑️ Reset", use_container_width=True)
    
    # Actions
    if test_btn:
        log(f"=== TEST API v{VERSION} ===", "INFO")
        with st.spinner("Test..."):
            results = wikidata_search("test")
        if results:
            st.success(f"✅ Wikidata OK! {len(results)} résultats")
        else:
            st.error("❌ Wikidata ne répond pas - voir logs")
    
    if reset_btn:
        st.session_state.entity = Entity()
        st.session_state.wiki_results = []
        st.session_state.insee_results = []
        log("Reset", "INFO")
        st.rerun()
    
    if search_btn and search_query:
        if source in ["Wikidata", "Les deux"]:
            with st.spinner("Wikidata..."):
                st.session_state.wiki_results = wikidata_search(search_query)
        if source in ["INSEE", "Les deux"]:
            with st.spinner("INSEE..."):
                st.session_state.insee_results = insee_search(search_query)
        st.rerun()
    
    # Résultats Wikidata
    if st.session_state.wiki_results:
        st.markdown(f"**🌐 Wikidata ({len(st.session_state.wiki_results)})**")
        for i, item in enumerate(st.session_state.wiki_results[:8]):
            c1, c2, c3 = st.columns([2, 5, 2])
            with c1:
                st.code(item['qid'], language=None)
            with c2:
                st.write(f"**{item['label']}**")
                if item['desc']:
                    st.caption(item['desc'][:60])
            with c3:
                if st.button("✅", key=f"w{i}", help="Sélectionner"):
                    log(f"Selection: {item['qid']}", "INFO")
                    with st.spinner("Chargement..."):
                        details = wikidata_get_entity(item['qid'])
                    e = st.session_state.entity
                    e.qid = item['qid']
                    e.name = details['name_fr'] or item['label']
                    e.name_en = details['name_en']
                    e.description_fr = details['desc_fr']
                    e.siren = e.siren or details['siren']
                    e.lei = details['lei']
                    e.website = e.website or details['website']
                    e.parent_org_qid = details['parent_qid']
                    e.parent_org_name = details['parent_name']
                    st.rerun()
    
    # Résultats INSEE
    if st.session_state.insee_results:
        st.markdown(f"**🏛️ INSEE ({len(st.session_state.insee_results)})**")
        for i, item in enumerate(st.session_state.insee_results[:6]):
            c1, c2, c3 = st.columns([2, 5, 2])
            with c1:
                st.write("🟢" if item['active'] else "🔴", item['siren'])
            with c2:
                st.write(f"**{item['name']}**")
            with c3:
                if st.button("✅", key=f"i{i}"):
                    e = st.session_state.entity
                    e.name = e.name or item['name']
                    e.siren = item['siren']
                    e.address = item['address']
                    log(f"INSEE: {item['name']}", "OK")
                    st.rerun()
    
    # Entity
    st.divider()
    e = st.session_state.entity
    
    if e.name or e.qid or e.siren:
        st.subheader("📋 Entité")
        
        # Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Score", f"{e.score()}%")
        m2.metric("QID", e.qid or "—")
        m3.metric("SIREN", e.siren or "—")
        m4.metric("Parent", e.parent_org_qid or "—")
        
        # Tabs
        tabs = st.tabs(["Identité", "Filiation", "JSON-LD"])
        
        with tabs[0]:
            c1, c2 = st.columns(2)
            with c1:
                e.name = st.text_input("Nom", e.name)
                e.siren = st.text_input("SIREN", e.siren)
                e.qid = st.text_input("QID", e.qid)
            with c2:
                e.website = st.text_input("Website", e.website)
                e.lei = st.text_input("LEI", e.lei)
                e.org_type = st.selectbox("Type", ["Organization", "Corporation", "LocalBusiness", "BankOrCreditUnion"])
        
        with tabs[1]:
            c1, c2 = st.columns(2)
            with c1:
                e.parent_org_name = st.text_input("Parent Name", e.parent_org_name)
            with c2:
                e.parent_org_qid = st.text_input("Parent QID", e.parent_org_qid)
            if e.parent_org_qid:
                st.success(f"✅ [{e.parent_org_name}](https://www.wikidata.org/wiki/{e.parent_org_qid})")
        
        with tabs[2]:
            json_ld = {
                "@context": "https://schema.org",
                "@type": e.org_type,
                "name": e.name,
                "url": e.website or None,
                "taxID": f"FR{e.siren}" if e.siren else None,
                "sameAs": f"https://www.wikidata.org/wiki/{e.qid}" if e.qid else None,
                "parentOrganization": {
                    "@type": "Organization",
                    "name": e.parent_org_name,
                    "sameAs": f"https://www.wikidata.org/wiki/{e.parent_org_qid}"
                } if e.parent_org_name else None
            }
            # Clean None values
            json_ld = {k: v for k, v in json_ld.items() if v is not None}
            
            st.json(json_ld)
            st.download_button("💾 Download", json.dumps(json_ld, indent=2), "schema.json")
    else:
        st.info("👆 Recherchez une organisation")

# ============================================================================
# FOOTER
# ============================================================================
st.divider()
st.markdown(f"""
<div style="text-align: center; color: #888; padding: 10px;">
    🛡️ <strong>AAS v{VERSION}</strong> | Build: <code>{BUILD_ID}</code> | {BUILD_DATE} | Wikidata + INSEE
</div>
""", unsafe_allow_html=True)
