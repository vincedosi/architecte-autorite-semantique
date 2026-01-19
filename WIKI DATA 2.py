"""
🛡️ Architecte d'Autorité Sémantique v9.1 (DEBUG VISIBLE)
---------------------------------------------------------
LOGS VISIBLES EN TEMPS RÉEL DANS L'INTERFACE
"""

import streamlit as st
import requests
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime

# ============================================================================
# VERSION
# ============================================================================
VERSION = "9.1.0"
BUILD_DATE = "2025-01-19"

# ============================================================================
# CONFIG
# ============================================================================
st.set_page_config(
    page_title=f"AAS v{VERSION}",
    page_icon="🛡️",
    layout="wide"
)

# ============================================================================
# SESSION STATE INIT
# ============================================================================
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'entity' not in st.session_state:
    st.session_state.entity = None
if 'social_links' not in st.session_state:
    st.session_state.social_links = {}
if 'mistral_key' not in st.session_state:
    st.session_state.mistral_key = ''
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'wiki_results' not in st.session_state:
    st.session_state.wiki_results = []
if 'insee_results' not in st.session_state:
    st.session_state.insee_results = []
if 'last_error' not in st.session_state:
    st.session_state.last_error = None


def log(msg: str, level: str = "INFO"):
    """Ajoute un log horodaté."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    icons = {"INFO": "ℹ️", "OK": "✅", "ERROR": "❌", "WARN": "⚠️", "DEBUG": "🔧", "HTTP": "🌐"}
    icon = icons.get(level, "•")
    entry = f"{icon} [{timestamp}] [{level}] {msg}"
    st.session_state.logs.append(entry)
    # Garder max 100 logs
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
    expertise_en: str = ""
    qid: str = ""
    siren: str = ""
    siret: str = ""
    lei: str = ""
    naf: str = ""
    website: str = ""
    org_type: str = "Organization"
    parent_org_name: str = ""
    parent_org_qid: str = ""
    address: str = ""

    def score(self) -> int:
        s = 0
        if self.qid: s += 20
        if self.siren: s += 20
        if self.lei: s += 15
        if self.website: s += 15
        if self.parent_org_qid: s += 15
        if self.expertise_fr: s += 15
        return min(s, 100)


if st.session_state.entity is None:
    st.session_state.entity = Entity()


# ============================================================================
# WIKIDATA API - AVEC LOGS DÉTAILLÉS
# ============================================================================
def wikidata_search(query: str) -> List[Dict]:
    """Recherche Wikidata avec logs détaillés."""
    
    log(f"=== WIKIDATA SEARCH START: '{query}' ===", "INFO")
    
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": query,
        "language": "fr",
        "uselang": "fr",
        "format": "json",
        "limit": 10,
        "type": "item",
        "origin": "*"  # CORS
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }
    
    log(f"URL: {url}", "DEBUG")
    log(f"Params: {params}", "DEBUG")
    
    # Retry loop
    for attempt in range(3):
        log(f"Tentative {attempt + 1}/3...", "HTTP")
        
        try:
            start_time = time.time()
            
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=30,
                verify=True
            )
            
            elapsed = round(time.time() - start_time, 2)
            log(f"Response en {elapsed}s - Status: {response.status_code}", "HTTP")
            
            # Log response headers
            log(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}", "DEBUG")
            log(f"Content-Length: {response.headers.get('Content-Length', 'N/A')}", "DEBUG")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    log(f"JSON parsé OK", "DEBUG")
                    
                    # Vérifier la structure
                    if 'search' in data:
                        results = data['search']
                        log(f"Trouvé {len(results)} résultats", "OK")
                        
                        output = []
                        for item in results:
                            qid = item.get('id', '?')
                            label = item.get('label', qid)
                            desc = item.get('description', '')
                            log(f"  → {qid}: {label}", "DEBUG")
                            output.append({
                                'qid': qid,
                                'label': label,
                                'desc': desc
                            })
                        
                        log(f"=== WIKIDATA SEARCH SUCCESS ===", "OK")
                        return output
                    else:
                        log(f"Pas de clé 'search' dans la réponse", "ERROR")
                        log(f"Clés disponibles: {list(data.keys())}", "DEBUG")
                        if 'error' in data:
                            log(f"Erreur API: {data['error']}", "ERROR")
                        
                except json.JSONDecodeError as e:
                    log(f"Erreur JSON: {str(e)}", "ERROR")
                    log(f"Response text (500 premiers chars): {response.text[:500]}", "DEBUG")
            
            elif response.status_code == 429:
                log(f"Rate limit (429) - Attente {2**attempt}s...", "WARN")
                time.sleep(2 ** attempt)
                continue
                
            elif response.status_code == 403:
                log(f"Forbidden (403) - Possible blocage User-Agent", "ERROR")
                log(f"Response: {response.text[:300]}", "DEBUG")
                
            elif response.status_code >= 500:
                log(f"Erreur serveur ({response.status_code}) - Retry...", "WARN")
                time.sleep(2)
                continue
                
            else:
                log(f"HTTP Error {response.status_code}", "ERROR")
                log(f"Response: {response.text[:300]}", "DEBUG")
                
        except requests.Timeout:
            log(f"TIMEOUT après 30s (tentative {attempt + 1})", "ERROR")
            if attempt < 2:
                log("Nouvelle tentative...", "WARN")
                time.sleep(2)
                continue
                
        except requests.ConnectionError as e:
            log(f"CONNECTION ERROR: {str(e)[:100]}", "ERROR")
            st.session_state.last_error = f"ConnectionError: {str(e)}"
            if attempt < 2:
                time.sleep(2)
                continue
                
        except requests.RequestException as e:
            log(f"REQUEST ERROR: {type(e).__name__}: {str(e)[:100]}", "ERROR")
            st.session_state.last_error = str(e)
            
        except Exception as e:
            log(f"UNEXPECTED ERROR: {type(e).__name__}: {str(e)[:100]}", "ERROR")
            st.session_state.last_error = str(e)
            import traceback
            log(f"Traceback: {traceback.format_exc()[:300]}", "DEBUG")
    
    log(f"=== WIKIDATA SEARCH FAILED ===", "ERROR")
    return []


def wikidata_get_entity(qid: str) -> Dict:
    """Récupère détails entité avec logs."""
    
    log(f"=== WIKIDATA GET ENTITY: {qid} ===", "INFO")
    
    result = {
        "name_fr": "", "name_en": "", "desc_fr": "", "desc_en": "",
        "siren": "", "lei": "", "website": "",
        "parent_name": "", "parent_qid": ""
    }
    
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "languages": "fr|en",
        "props": "labels|descriptions|claims",
        "format": "json",
        "origin": "*"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    try:
        log(f"Requête wbgetentities...", "HTTP")
        response = requests.get(url, params=params, headers=headers, timeout=30)
        log(f"Status: {response.status_code}", "HTTP")
        
        if response.status_code == 200:
            data = response.json()
            
            if 'entities' in data and qid in data['entities']:
                entity = data['entities'][qid]
                log(f"Entité trouvée", "OK")
                
                # Labels
                labels = entity.get('labels', {})
                result["name_fr"] = labels.get('fr', {}).get('value', '')
                result["name_en"] = labels.get('en', {}).get('value', '')
                log(f"Nom FR: {result['name_fr']}", "DEBUG")
                
                # Descriptions
                descs = entity.get('descriptions', {})
                result["desc_fr"] = descs.get('fr', {}).get('value', '')
                result["desc_en"] = descs.get('en', {}).get('value', '')
                
                # Claims
                claims = entity.get('claims', {})
                log(f"Nombre de claims: {len(claims)}", "DEBUG")
                
                # P1616 = SIREN
                if 'P1616' in claims:
                    try:
                        result["siren"] = claims['P1616'][0]['mainsnak']['datavalue']['value']
                        log(f"SIREN (P1616): {result['siren']}", "OK")
                    except (KeyError, IndexError) as e:
                        log(f"Erreur extraction SIREN: {e}", "WARN")
                
                # P1278 = LEI
                if 'P1278' in claims:
                    try:
                        result["lei"] = claims['P1278'][0]['mainsnak']['datavalue']['value']
                        log(f"LEI (P1278): {result['lei']}", "OK")
                    except:
                        pass
                
                # P856 = Website
                if 'P856' in claims:
                    try:
                        result["website"] = claims['P856'][0]['mainsnak']['datavalue']['value']
                        log(f"Website (P856): {result['website']}", "OK")
                    except:
                        pass
                
                # P749 = Parent Organization
                if 'P749' in claims:
                    try:
                        parent_value = claims['P749'][0]['mainsnak']['datavalue']['value']
                        log(f"P749 raw value: {parent_value}", "DEBUG")
                        
                        if isinstance(parent_value, dict):
                            result["parent_qid"] = parent_value.get('id', '')
                        elif isinstance(parent_value, str):
                            result["parent_qid"] = parent_value
                        
                        if result["parent_qid"]:
                            log(f"Parent QID (P749): {result['parent_qid']}", "OK")
                            # Récupérer le nom du parent
                            result["parent_name"] = wikidata_get_label(result["parent_qid"])
                            log(f"Parent Name: {result['parent_name']}", "OK")
                    except Exception as e:
                        log(f"Erreur extraction P749: {e}", "WARN")
                else:
                    log(f"Pas de P749 (Parent Organization)", "DEBUG")
                
                log(f"=== GET ENTITY SUCCESS ===", "OK")
            else:
                log(f"Entité {qid} non trouvée dans la réponse", "ERROR")
                log(f"Clés entities: {list(data.get('entities', {}).keys())}", "DEBUG")
        else:
            log(f"HTTP {response.status_code}", "ERROR")
            
    except Exception as e:
        log(f"Exception: {type(e).__name__}: {str(e)}", "ERROR")
    
    return result


def wikidata_get_label(qid: str) -> str:
    """Récupère le label d'un QID."""
    try:
        url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "languages": "fr|en",
            "props": "labels",
            "format": "json"
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            labels = data.get('entities', {}).get(qid, {}).get('labels', {})
            return labels.get('fr', {}).get('value', '') or labels.get('en', {}).get('value', qid)
    except Exception as e:
        log(f"Erreur get_label({qid}): {e}", "WARN")
    return qid


def insee_search(query: str) -> List[Dict]:
    """Recherche INSEE."""
    log(f"=== INSEE SEARCH: '{query}' ===", "INFO")
    
    try:
        url = "https://recherche-entreprises.api.gouv.fr/search"
        params = {"q": query, "per_page": 10}
        
        response = requests.get(url, params=params, timeout=15)
        log(f"INSEE Status: {response.status_code}", "HTTP")
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            log(f"INSEE: {len(results)} résultats", "OK")
            
            return [{
                'siren': item.get('siren', ''),
                'siret': item.get('siege', {}).get('siret', ''),
                'name': item.get('nom_complet', ''),
                'legal_name': item.get('nom_raison_sociale', ''),
                'naf': item.get('activite_principale', ''),
                'address': f"{item.get('siege', {}).get('adresse', '')} {item.get('siege', {}).get('code_postal', '')} {item.get('siege', {}).get('commune', '')}",
                'active': item.get('etat_administratif') == 'A'
            } for item in results]
        else:
            log(f"INSEE Error {response.status_code}", "ERROR")
    except Exception as e:
        log(f"INSEE Exception: {e}", "ERROR")
    
    return []


# ============================================================================
# AUTH
# ============================================================================
if not st.session_state.authenticated:
    st.title(f"🛡️ AAS v{VERSION}")
    st.caption(f"Build: {BUILD_DATE}")
    pwd = st.text_input("Mot de passe:", type="password")
    if st.button("Déverrouiller", type="primary"):
        if pwd == "SEOTOOLS":
            st.session_state.authenticated = True
            log("Authentification réussie", "OK")
            st.rerun()
        else:
            st.error("❌ Mot de passe incorrect")
    st.stop()


# ============================================================================
# MAIN LAYOUT
# ============================================================================
st.title(f"🛡️ Architecte d'Autorité Sémantique")
st.caption(f"Version {VERSION} | Build {BUILD_DATE} | Streamlit Cloud")

# Layout: 2 colonnes (main + logs)
col_main, col_logs = st.columns([2, 1])

with col_logs:
    st.subheader("📟 Console Logs")
    
    # Boutons de contrôle
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🗑️ Clear Logs", use_container_width=True):
            st.session_state.logs = []
            st.rerun()
    with c2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    # Zone de logs scrollable
    log_container = st.container(height=500)
    with log_container:
        if st.session_state.logs:
            for entry in reversed(st.session_state.logs):
                if "[ERROR]" in entry:
                    st.error(entry)
                elif "[OK]" in entry:
                    st.success(entry)
                elif "[WARN]" in entry:
                    st.warning(entry)
                else:
                    st.text(entry)
        else:
            st.info("Aucun log. Lancez une recherche.")
    
    # Dernière erreur
    if st.session_state.last_error:
        st.error(f"**Dernière erreur:** {st.session_state.last_error}")

with col_main:
    # Recherche
    st.subheader("🔍 Recherche")
    
    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        search_query = st.text_input("Nom de l'organisation", placeholder="Ex: Boursorama, IKEA, BNP...")
    with search_col2:
        search_source = st.selectbox("Source", ["Wikidata", "INSEE", "Les deux"])
    
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    with btn_col1:
        search_btn = st.button("🔎 Rechercher", type="primary", use_container_width=True)
    with btn_col2:
        test_btn = st.button("🧪 Test API", use_container_width=True)
    with btn_col3:
        reset_btn = st.button("🗑️ Reset", use_container_width=True)
    
    # Test API
    if test_btn:
        log("=== TEST API WIKIDATA ===", "INFO")
        log("Test avec query='test'...", "INFO")
        
        with st.spinner("Test en cours..."):
            results = wikidata_search("test")
        
        if results:
            st.success(f"✅ API Wikidata OK! ({len(results)} résultats)")
        else:
            st.error("❌ API Wikidata ne répond pas")
    
    # Reset
    if reset_btn:
        st.session_state.entity = Entity()
        st.session_state.wiki_results = []
        st.session_state.insee_results = []
        st.session_state.last_error = None
        log("Reset effectué", "INFO")
        st.rerun()
    
    # Recherche
    if search_btn and search_query:
        log(f"Recherche lancée: '{search_query}' (source: {search_source})", "INFO")
        
        if search_source in ["Wikidata", "Les deux"]:
            with st.spinner("Recherche Wikidata..."):
                st.session_state.wiki_results = wikidata_search(search_query)
        
        if search_source in ["INSEE", "Les deux"]:
            with st.spinner("Recherche INSEE..."):
                st.session_state.insee_results = insee_search(search_query)
        
        st.rerun()
    
    # Résultats Wikidata
    if st.session_state.wiki_results:
        st.subheader(f"🌐 Résultats Wikidata ({len(st.session_state.wiki_results)})")
        
        for i, item in enumerate(st.session_state.wiki_results):
            col1, col2, col3 = st.columns([1, 3, 1])
            with col1:
                st.code(item['qid'])
            with col2:
                st.write(f"**{item['label']}**")
                st.caption(item['desc'][:80] if item['desc'] else "Pas de description")
            with col3:
                if st.button("✅ Sélect.", key=f"sel_wiki_{i}"):
                    log(f"Sélection: {item['qid']}", "INFO")
                    
                    with st.spinner(f"Chargement {item['qid']}..."):
                        details = wikidata_get_entity(item['qid'])
                    
                    e = st.session_state.entity
                    e.qid = item['qid']
                    e.name = details['name_fr'] or item['label']
                    e.name_en = details['name_en']
                    e.description_fr = details['desc_fr']
                    e.description_en = details['desc_en']
                    e.siren = e.siren or details['siren']
                    e.lei = details['lei']
                    e.website = e.website or details['website']
                    e.parent_org_qid = details['parent_qid']
                    e.parent_org_name = details['parent_name']
                    
                    log(f"Entity mise à jour: {e.name}", "OK")
                    st.rerun()
    
    # Résultats INSEE
    if st.session_state.insee_results:
        st.subheader(f"🏛️ Résultats INSEE ({len(st.session_state.insee_results)})")
        
        for i, item in enumerate(st.session_state.insee_results):
            col1, col2, col3 = st.columns([1, 3, 1])
            with col1:
                status = "🟢" if item['active'] else "🔴"
                st.write(f"{status} {item['siren']}")
            with col2:
                st.write(f"**{item['name']}**")
                st.caption(item['address'][:60])
            with col3:
                if st.button("✅ Sélect.", key=f"sel_insee_{i}"):
                    e = st.session_state.entity
                    e.name = e.name or item['name']
                    e.legal_name = item['legal_name']
                    e.siren = item['siren']
                    e.siret = item['siret']
                    e.naf = item['naf']
                    e.address = item['address']
                    log(f"INSEE chargé: {item['name']}", "OK")
                    st.rerun()
    
    # Entity Details
    st.divider()
    e = st.session_state.entity
    
    if e.name or e.qid or e.siren:
        st.subheader("📋 Entité Sélectionnée")
        
        # Métriques
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Score", f"{e.score()}/100")
        with m2:
            st.metric("QID", e.qid or "—")
        with m3:
            st.metric("SIREN", e.siren or "—")
        with m4:
            st.metric("Parent", e.parent_org_qid or "—")
        
        # Tabs
        tabs = st.tabs(["🆔 Identité", "🔗 Filiation", "💾 JSON-LD"])
        
        with tabs[0]:
            c1, c2 = st.columns(2)
            with c1:
                e.name = st.text_input("Nom", e.name)
                e.legal_name = st.text_input("Raison sociale", e.legal_name)
                e.siren = st.text_input("SIREN", e.siren)
                e.qid = st.text_input("QID", e.qid)
            with c2:
                e.website = st.text_input("Site web", e.website)
                e.lei = st.text_input("LEI", e.lei)
                e.address = st.text_input("Adresse", e.address)
                e.org_type = st.selectbox("Type", ["Organization", "Corporation", "LocalBusiness", "BankOrCreditUnion"])
        
        with tabs[1]:
            st.write("**Parent Organization (P749)**")
            c1, c2 = st.columns(2)
            with c1:
                e.parent_org_name = st.text_input("Nom maison mère", e.parent_org_name)
            with c2:
                e.parent_org_qid = st.text_input("QID maison mère", e.parent_org_qid)
            
            if e.parent_org_qid:
                st.success(f"✅ Lié à: [{e.parent_org_name}](https://www.wikidata.org/wiki/{e.parent_org_qid})")
        
        with tabs[2]:
            # JSON-LD
            json_ld = {
                "@context": "https://schema.org",
                "@type": e.org_type,
                "name": e.name
            }
            if e.website:
                json_ld["url"] = e.website
            if e.siren:
                json_ld["taxID"] = f"FR{e.siren}"
            if e.qid:
                json_ld["sameAs"] = f"https://www.wikidata.org/wiki/{e.qid}"
            if e.parent_org_name:
                json_ld["parentOrganization"] = {
                    "@type": "Organization",
                    "name": e.parent_org_name,
                    "sameAs": f"https://www.wikidata.org/wiki/{e.parent_org_qid}" if e.parent_org_qid else None
                }
            
            st.json(json_ld)
            st.download_button("💾 Télécharger", json.dumps(json_ld, indent=2, ensure_ascii=False), "jsonld.json")
    else:
        st.info("👆 Recherchez une organisation ci-dessus")

st.divider()
st.caption(f"🛡️ AAS v{VERSION} | {BUILD_DATE} | Wikidata + INSEE")
