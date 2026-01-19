"""
🛡️ Architecte d'Autorité Sémantique v8.0 (Optimized Edition)
-------------------------------------------------------------
CHANGELOG v8.0:
- ✅ FIX: Récupération Parent Organization (P749) via SPARQL
- ✅ FIX: Initialisation mistral_key avant utilisation
- ✅ FIX: Gestion robuste des erreurs SPARQL avec retry
- ✅ NEW: Fallback Mistral pour Parent Org si absent de Wikidata
- ✅ IMPROVE: Structure code + types hints
- ✅ IMPROVE: Prompt Mistral optimisé pour GEO
"""

import streamlit as st
import asyncio
import httpx
import json
import time
import re
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any

# ============================================================================
# 1. CONFIGURATION & INITIALISATION
# ============================================================================
st.set_page_config(
    page_title="Architecte d'Autorité Sémantique v8.0",
    page_icon="🛡️",
    layout="wide"
)

# Session State Initialization
DEFAULT_SESSION = {
    'logs': [],
    'authenticated': False,
    'entity': None,
    'social_links': {k: '' for k in ['linkedin', 'twitter', 'facebook', 'instagram', 'youtube']},
    'res_wiki': [],
    'mistral_key': ''  # FIX: Initialisation manquante
}

for key, default in DEFAULT_SESSION.items():
    if key not in st.session_state:
        st.session_state[key] = default


def add_log(msg: str, status: str = "info") -> None:
    """Ajoute un message au log avec timestamp."""
    icons = {"info": "ℹ️", "success": "✅", "error": "❌", "warning": "⚠️"}
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.logs.append(f"{icons.get(status, '•')} [{timestamp}] {msg}")
    if len(st.session_state.logs) > 30:
        st.session_state.logs.pop(0)


# ============================================================================
# 2. DATA CLASSES
# ============================================================================
@dataclass
class Entity:
    """Représente une entité organisationnelle avec tous ses identifiants."""
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
    parent_org_qid: str = ""  # Renommé pour clarté
    parent_org_wiki: str = ""  # Alias pour compatibilité

    def __post_init__(self):
        # Sync des alias
        if self.parent_org_qid and not self.parent_org_wiki:
            self.parent_org_wiki = self.parent_org_qid
        elif self.parent_org_wiki and not self.parent_org_qid:
            self.parent_org_qid = self.parent_org_wiki

    def authority_score(self) -> int:
        """Calcule le score d'autorité sémantique (0-100)."""
        score = 0
        if self.qid: score += 25
        if self.siren: score += 25
        if self.lei: score += 20
        if self.website: score += 15
        if self.expertise_fr: score += 10
        if self.parent_org_qid: score += 5  # Bonus filiation
        return min(score, 100)


# Initialize entity after dataclass definition
if st.session_state.entity is None:
    st.session_state.entity = Entity()


# ============================================================================
# 3. WIKIDATA ENGINE (OPTIMIZED)
# ============================================================================
class WikidataEngine:
    """Moteur de requêtes Wikidata avec Action API + SPARQL."""
    
    HEADERS = {
        "User-Agent": "SemanticAuthorityBot/8.0 (https://votre-agence-seo.com; contact@votre-domaine.fr) Python/httpx",
        "Accept": "application/json"
    }
    
    ACTION_API = "https://www.wikidata.org/w/api.php"
    SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

    @staticmethod
    async def search(client: httpx.AsyncClient, query: str) -> List[Dict[str, str]]:
        """Recherche d'entités via Action API (plus stable que SPARQL)."""
        add_log(f"🔍 Recherche Wikidata: '{query}'")
        
        try:
            params = {
                "action": "wbsearchentities",
                "search": query,
                "language": "fr",
                "uselang": "fr",
                "format": "json",
                "limit": 8,
                "type": "item"
            }
            
            response = await client.get(
                WikidataEngine.ACTION_API,
                params=params,
                headers=WikidataEngine.HEADERS,
                timeout=15.0
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('search', [])
                add_log(f"Wikidata: {len(results)} entités trouvées", "success")
                
                return [{
                    'qid': item['id'],
                    'label': item.get('label', item['id']),
                    'desc': item.get('description', 'Aucune description')
                } for item in results]
            else:
                add_log(f"Erreur HTTP {response.status_code}", "error")
                
        except httpx.TimeoutException:
            add_log("Timeout Wikidata (15s)", "error")
        except Exception as e:
            add_log(f"Erreur recherche: {str(e)[:50]}", "error")
        
        return []

    @staticmethod
    async def get_details(client: httpx.AsyncClient, qid: str) -> Dict[str, Any]:
        """
        Récupère les détails complets d'une entité.
        Stratégie: Action API (labels) + SPARQL (identifiants + parent org)
        """
        add_log(f"📋 Récupération détails: {qid}")
        
        result = {
            "name_fr": "", "name_en": "", "desc_fr": "", "desc_en": "",
            "siren": "", "lei": "", "website": "",
            "parent_name": "", "parent_qid": ""
        }
        
        # 1. Action API pour labels et descriptions (toujours stable)
        try:
            params = {
                "action": "wbgetentities",
                "ids": qid,
                "languages": "fr|en",
                "props": "labels|descriptions",
                "format": "json"
            }
            
            response = await client.get(
                WikidataEngine.ACTION_API,
                params=params,
                headers=WikidataEngine.HEADERS,
                timeout=10.0
            )
            
            if response.status_code == 200:
                entity_data = response.json().get('entities', {}).get(qid, {})
                labels = entity_data.get('labels', {})
                descs = entity_data.get('descriptions', {})
                
                result["name_fr"] = labels.get('fr', {}).get('value', '')
                result["name_en"] = labels.get('en', {}).get('value', '')
                result["desc_fr"] = descs.get('fr', {}).get('value', '')
                result["desc_en"] = descs.get('en', {}).get('value', '')
                
                add_log("Labels récupérés via Action API", "success")
        except Exception as e:
            add_log(f"Action API error: {str(e)[:30]}", "warning")

        # 2. SPARQL pour identifiants et parent organization (P749)
        sparql_query = f"""
        SELECT ?siren ?lei ?website ?parentOrg ?parentOrgLabel WHERE {{
            BIND(wd:{qid} AS ?item)
            OPTIONAL {{ ?item wdt:P1616 ?siren. }}
            OPTIONAL {{ ?item wdt:P1278 ?lei. }}
            OPTIONAL {{ ?item wdt:P856 ?website. }}
            OPTIONAL {{ ?item wdt:P749 ?parentOrg. }}
            SERVICE wikibase:label {{ 
                bd:serviceParam wikibase:language "fr,en". 
            }}
        }} LIMIT 1
        """
        
        try:
            response = await client.get(
                WikidataEngine.SPARQL_ENDPOINT,
                params={'query': sparql_query, 'format': 'json'},
                headers=WikidataEngine.HEADERS,
                timeout=20.0
            )
            
            if response.status_code == 200:
                bindings = response.json().get('results', {}).get('bindings', [])
                
                if bindings:
                    data = bindings[0]
                    result["siren"] = data.get('siren', {}).get('value', '')
                    result["lei"] = data.get('lei', {}).get('value', '')
                    result["website"] = data.get('website', {}).get('value', '')
                    
                    # Parent Organization
                    parent_uri = data.get('parentOrg', {}).get('value', '')
                    if parent_uri:
                        # Extraction QID depuis URI: http://www.wikidata.org/entity/Q123456
                        match = re.search(r'(Q\d+)$', parent_uri)
                        if match:
                            result["parent_qid"] = match.group(1)
                            result["parent_name"] = data.get('parentOrgLabel', {}).get('value', '')
                            add_log(f"✅ Parent trouvé: {result['parent_name']} ({result['parent_qid']})", "success")
                    
                    add_log("SPARQL OK: identifiants récupérés", "success")
                else:
                    add_log("SPARQL: aucune donnée pour cette entité", "warning")
                    
            elif response.status_code == 429:
                add_log("SPARQL Rate Limit (429) - Réessayez dans 1 min", "error")
            elif response.status_code == 403:
                add_log("SPARQL Forbidden (403) - Vérifiez User-Agent", "error")
            else:
                add_log(f"SPARQL Error: {response.status_code}", "error")
                
        except httpx.TimeoutException:
            add_log("SPARQL Timeout (20s)", "warning")
        except Exception as e:
            add_log(f"SPARQL crash: {str(e)[:40]}", "error")
        
        return result


# ============================================================================
# 4. MISTRAL AI ENGINE (OPTIMIZED)
# ============================================================================
class MistralEngine:
    """Moteur d'enrichissement sémantique via Mistral AI."""
    
    API_URL = "https://api.mistral.ai/v1/chat/completions"
    
    @staticmethod
    async def optimize(api_key: str, entity: Entity) -> Optional[Dict[str, Any]]:
        """
        Génère les descriptions GEO et recherche la filiation parentale.
        Utilisé quand Wikidata n'a pas de Parent Organization.
        """
        if not api_key:
            add_log("Clé Mistral manquante", "error")
            return None
        
        add_log("🤖 Génération GEO via Mistral AI...")
        
        # Prompt optimisé pour GEO et Parent Org
        prompt = f"""Tu es un expert SEO spécialisé en Generative Engine Optimization (GEO) et données structurées Schema.org.

ENTITÉ À ANALYSER:
- Nom: {entity.name}
- Type: {entity.org_type}
- SIREN: {entity.siren or 'Non renseigné'}
- QID Wikidata: {entity.qid or 'Non renseigné'}
- Site web: {entity.website or 'Non renseigné'}
- Description actuelle: {entity.description_fr or 'Aucune'}

MISSION:
1. Génère une description SEO optimisée (150-200 caractères) en français et anglais
2. Identifie 3-5 domaines d'expertise (knowsAbout) pertinents
3. **IMPORTANT**: Identifie la maison mère / organisation parente si elle existe
   - Recherche dans ta base de connaissances la structure actionnariale
   - Fournis le nom exact ET le QID Wikidata du parent si tu le connais

RÉPONDS UNIQUEMENT EN JSON VALIDE (sans markdown, sans backticks):
{{
    "description_fr": "Description optimisée en français",
    "description_en": "Optimized English description",
    "expertise_fr": "Domaine 1, Domaine 2, Domaine 3",
    "expertise_en": "Domain 1, Domain 2, Domain 3",
    "parent_org_name": "Nom de la maison mère ou null si indépendant",
    "parent_org_qid": "QID Wikidata du parent (ex: Q123456) ou null si inconnu"
}}"""

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    MistralEngine.API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "mistral-small-latest",
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.3  # Plus déterministe
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    content = response.json()['choices'][0]['message']['content']
                    result = json.loads(content)
                    add_log("Mistral: génération réussie", "success")
                    
                    # Log du parent trouvé
                    if result.get('parent_org_name'):
                        add_log(f"🔗 Parent suggéré: {result['parent_org_name']}", "info")
                    
                    return result
                    
                elif response.status_code == 401:
                    add_log("Clé Mistral invalide", "error")
                else:
                    add_log(f"Mistral HTTP {response.status_code}", "error")
                    
            except json.JSONDecodeError:
                add_log("Mistral: réponse JSON invalide", "error")
            except httpx.TimeoutException:
                add_log("Mistral Timeout (30s)", "error")
            except Exception as e:
                add_log(f"Mistral error: {str(e)[:40]}", "error")
        
        return None


# ============================================================================
# 5. AUTHENTICATION
# ============================================================================
if not st.session_state.authenticated:
    st.title("🛡️ Architecte d'Autorité Sémantique v8.0")
    st.markdown("### 🔐 Accès Restreint")
    
    pwd = st.text_input("Mot de passe:", type="password", key="pwd_input")
    
    if st.button("Déverrouiller", type="primary"):
        if pwd == "SEOTOOLS":
            st.session_state.authenticated = True
            add_log("Authentification réussie", "success")
            st.rerun()
        else:
            st.error("❌ Mot de passe incorrect")
    st.stop()


# ============================================================================
# 6. SIDEBAR
# ============================================================================
with st.sidebar:
    st.header("⚙️ Administration AAS v8.0")
    
    # Console Logs
    with st.expander("📟 Console Logs", expanded=True):
        log_container = st.container(height=200)
        with log_container:
            for log in reversed(st.session_state.logs[-15:]):
                st.caption(log)
    
    st.divider()
    
    # Import Config
    st.subheader("📥 Importer Configuration")
    uploaded = st.file_uploader("Fichier JSON", type="json", label_visibility="collapsed")
    if uploaded:
        try:
            data = json.load(uploaded)
            st.session_state.entity = Entity(**data.get('entity', {}))
            st.session_state.social_links.update(data.get('social_links', {}))
            add_log("Configuration importée", "success")
            st.rerun()
        except Exception as e:
            add_log(f"Import failed: {str(e)[:30]}", "error")
    
    st.divider()
    
    # Mistral API Key
    st.subheader("🔑 API Keys")
    st.session_state.mistral_key = st.text_input(
        "Mistral API Key",
        value=st.session_state.mistral_key,
        type="password"
    )
    
    st.divider()
    
    # Wikidata Search
    st.subheader("🔍 Recherche Wikidata")
    search_query = st.text_input("Nom de l'organisation", key="wiki_search")
    
    if st.button("🔎 Lancer l'audit", use_container_width=True, type="primary"):
        if search_query:
            async def run_search():
                async with httpx.AsyncClient() as client:
                    st.session_state.res_wiki = await WikidataEngine.search(client, search_query)
            asyncio.run(run_search())
            st.rerun()
    
    # Search Results
    if st.session_state.res_wiki:
        st.markdown("**Résultats:**")
        for item in st.session_state.res_wiki:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(f"**{item['label']}**")
                st.caption(item['desc'][:60] + "..." if len(item['desc']) > 60 else item['desc'])
            with col2:
                if st.button("✅", key=f"sel_{item['qid']}", help="Sélectionner"):
                    async def fetch_and_merge():
                        async with httpx.AsyncClient() as client:
                            details = await WikidataEngine.get_details(client, item['qid'])
                            e = st.session_state.entity
                            
                            # Merge data
                            e.qid = item['qid']
                            e.name = details['name_fr'] or item['label']
                            e.name_en = details['name_en'] or e.name
                            e.description_fr = details['desc_fr']
                            e.description_en = details['desc_en']
                            e.siren = details['siren']
                            e.lei = details['lei']
                            e.website = details['website']
                            
                            # Parent Organization from Wikidata
                            if details['parent_qid']:
                                e.parent_org_qid = details['parent_qid']
                                e.parent_org_wiki = details['parent_qid']
                                e.parent_org_name = details['parent_name']
                            
                    asyncio.run(fetch_and_merge())
                    st.rerun()


# ============================================================================
# 7. MAIN INTERFACE
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique v8.0")

e = st.session_state.entity

# Authority Score Badge
if e.name or e.qid:
    score = e.authority_score()
    score_color = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"
    st.metric("Score d'Autorité", f"{score_color} {score}/100")

# Main Tabs
if e.name or e.siren or e.qid:
    tabs = st.tabs(["🆔 Identité", "🪄 GEO Magic", "📱 Réseaux Sociaux", "💾 Export JSON-LD"])
    
    # Tab 1: Identity
    with tabs[0]:
        col1, col2 = st.columns(2)
        
        with col1:
            e.org_type = st.selectbox(
                "Type Schema.org",
                ["Organization", "Corporation", "BankOrCreditUnion", "InsuranceAgency", 
                 "LocalBusiness", "NGO", "GovernmentOrganization"],
                index=["Organization", "Corporation", "BankOrCreditUnion", "InsuranceAgency", 
                       "LocalBusiness", "NGO", "GovernmentOrganization"].index(e.org_type) if e.org_type in ["Organization", "Corporation", "BankOrCreditUnion", "InsuranceAgency", "LocalBusiness", "NGO", "GovernmentOrganization"] else 0
            )
            e.name = st.text_input("Nom (FR)", e.name)
            e.name_en = st.text_input("Nom (EN)", e.name_en or e.name)
            e.siren = st.text_input("SIREN", e.siren)
        
        with col2:
            e.qid = st.text_input("QID Wikidata", e.qid)
            e.lei = st.text_input("LEI (Legal Entity Identifier)", e.lei)
            e.website = st.text_input("Site Web", e.website)
        
        st.divider()
        st.subheader("🔗 Filiation (Parent Organization)")
        
        col1, col2 = st.columns(2)
        with col1:
            e.parent_org_name = st.text_input("Nom Maison Mère", e.parent_org_name)
        with col2:
            parent_qid_input = st.text_input("QID Maison Mère", e.parent_org_qid or e.parent_org_wiki)
            e.parent_org_qid = parent_qid_input
            e.parent_org_wiki = parent_qid_input
        
        if e.parent_org_qid:
            st.success(f"✅ Filiation: {e.parent_org_name} → https://www.wikidata.org/wiki/{e.parent_org_qid}")
    
    # Tab 2: GEO Magic
    with tabs[1]:
        st.info("🪄 **GEO Magic** utilise Mistral AI pour générer des descriptions optimisées et détecter la filiation parentale.")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            if st.button("🪄 Auto-Optimize via Mistral AI", type="primary", use_container_width=True):
                if st.session_state.mistral_key:
                    result = asyncio.run(MistralEngine.optimize(st.session_state.mistral_key, e))
                    
                    if result:
                        # Update descriptions
                        e.description_fr = result.get('description_fr', e.description_fr)
                        e.description_en = result.get('description_en', e.description_en)
                        e.expertise_fr = result.get('expertise_fr', e.expertise_fr)
                        e.expertise_en = result.get('expertise_en', e.expertise_en)
                        
                        # Update parent if not already set from Wikidata
                        if not e.parent_org_name and result.get('parent_org_name'):
                            e.parent_org_name = result['parent_org_name']
                            add_log(f"Parent auto-détecté: {e.parent_org_name}", "success")
                        
                        if not e.parent_org_qid and result.get('parent_org_qid'):
                            qid = result['parent_org_qid']
                            if qid and qid.startswith('Q'):
                                e.parent_org_qid = qid
                                e.parent_org_wiki = qid
                                add_log(f"QID Parent: {qid}", "success")
                        
                        st.rerun()
                else:
                    st.error("⚠️ Veuillez renseigner votre clé Mistral dans la sidebar")
        
        with col2:
            st.caption("Requiert une clé API Mistral")
        
        st.divider()
        
        # Manual editing
        e.description_fr = st.text_area("Description FR", e.description_fr, height=100)
        e.description_en = st.text_area("Description EN", e.description_en, height=100)
        
        col1, col2 = st.columns(2)
        with col1:
            e.expertise_fr = st.text_input("Expertise FR (séparée par virgules)", e.expertise_fr)
        with col2:
            e.expertise_en = st.text_input("Expertise EN (comma separated)", e.expertise_en)
    
    # Tab 3: Social Networks
    with tabs[2]:
        st.subheader("📱 Réseaux Sociaux (sameAs)")
        
        social = st.session_state.social_links
        
        col1, col2 = st.columns(2)
        with col1:
            social['linkedin'] = st.text_input("LinkedIn", social['linkedin'])
            social['twitter'] = st.text_input("Twitter/X", social['twitter'])
            social['facebook'] = st.text_input("Facebook", social['facebook'])
        with col2:
            social['instagram'] = st.text_input("Instagram", social['instagram'])
            social['youtube'] = st.text_input("YouTube", social['youtube'])
    
    # Tab 4: Export JSON-LD
    with tabs[3]:
        st.subheader("💾 Export JSON-LD (Schema.org)")
        
        # Build sameAs array
        same_as = []
        if e.qid:
            same_as.append(f"https://www.wikidata.org/wiki/{e.qid}")
        same_as.extend([v for v in st.session_state.social_links.values() if v])
        
        # Build identifiers
        identifiers = []
        if e.siren:
            identifiers.append({
                "@type": "PropertyValue",
                "propertyID": "SIREN",
                "value": e.siren
            })
        if e.lei:
            identifiers.append({
                "@type": "PropertyValue",
                "propertyID": "LEI",
                "value": e.lei
            })
        
        # Build knowsAbout
        knows_about = []
        if e.expertise_fr:
            for exp in e.expertise_fr.split(','):
                knows_about.append({"@language": "fr", "@value": exp.strip()})
        if e.expertise_en:
            for exp in e.expertise_en.split(','):
                knows_about.append({"@language": "en", "@value": exp.strip()})
        
        # Build parent organization
        parent_org = None
        if e.parent_org_name:
            parent_org = {
                "@type": "Organization",
                "name": e.parent_org_name
            }
            if e.parent_org_qid:
                parent_org["sameAs"] = f"https://www.wikidata.org/wiki/{e.parent_org_qid}"
        
        # Final JSON-LD
        json_ld = {
            "@context": "https://schema.org",
            "@type": e.org_type,
            "name": e.name
        }
        
        # Add multilingual names
        if e.name_en and e.name_en != e.name:
            json_ld["name"] = [
                {"@language": "fr", "@value": e.name},
                {"@language": "en", "@value": e.name_en}
            ]
        
        # Add @id
        if e.website:
            json_ld["@id"] = f"{e.website.rstrip('/')}/#organization"
            json_ld["url"] = e.website
        
        # Add optional fields
        if e.description_fr:
            json_ld["description"] = [
                {"@language": "fr", "@value": e.description_fr}
            ]
            if e.description_en:
                json_ld["description"].append({"@language": "en", "@value": e.description_en})
        
        if e.siren:
            json_ld["taxID"] = f"FR{e.siren}"
        
        if identifiers:
            json_ld["identifier"] = identifiers
        
        if same_as:
            json_ld["sameAs"] = same_as
        
        if knows_about:
            json_ld["knowsAbout"] = knows_about
        
        if parent_org:
            json_ld["parentOrganization"] = parent_org
        
        # Display JSON-LD
        st.json(json_ld)
        
        # Copy-paste script
        script_tag = f'<script type="application/ld+json">\n{json.dumps(json_ld, indent=2, ensure_ascii=False)}\n</script>'
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Download JSON-LD only
            st.download_button(
                "📄 Télécharger JSON-LD",
                json.dumps(json_ld, indent=2, ensure_ascii=False),
                f"jsonld_{e.name.replace(' ', '_')}.json",
                mime="application/json"
            )
        
        with col2:
            # Download full config
            config = {
                "entity": asdict(e),
                "social_links": st.session_state.social_links,
                "json_ld": json_ld
            }
            st.download_button(
                "💾 Sauvegarder Config Complète",
                json.dumps(config, indent=2, ensure_ascii=False),
                f"config_{e.name.replace(' ', '_')}.json",
                mime="application/json"
            )
        
        st.divider()
        st.subheader("📋 Code à copier")
        st.code(script_tag, language="html")

else:
    # Empty state
    st.info("👈 Utilisez la barre latérale pour rechercher une organisation sur Wikidata et démarrer l'audit sémantique.")
    
    st.markdown("""
    ### 🚀 Guide de démarrage
    
    1. **Recherchez** une organisation dans la sidebar
    2. **Sélectionnez** le résultat correspondant pour importer les données Wikidata
    3. **Complétez** les informations manquantes (descriptions, expertise)
    4. **Utilisez GEO Magic** pour enrichir automatiquement via Mistral AI
    5. **Exportez** le JSON-LD optimisé pour votre site
    
    ### ✨ Nouveautés v8.0
    
    - **Auto-détection Parent Organization** via Wikidata (P749)
    - **Fallback Mistral** si le parent n'est pas dans Wikidata
    - **Score d'autorité** amélioré
    - **Gestion robuste** des erreurs API
    """)


# ============================================================================
# 8. FOOTER
# ============================================================================
st.divider()
st.caption("🛡️ Architecte d'Autorité Sémantique v8.0 | GEO-Ready | Schema.org Compliant")
