import streamlit as st
import pandas as pd
import numpy as np

#Chargement des données
@st.cache_data
def load_data_from_path(path):
    for sep in [';', ',', '\t', '|']:
        try:
            return pd.read_csv(path, sep=sep, engine='python', encoding='utf-8')
        except Exception:
            pass
    raise ValueError("Impossible de lire le fichier. Vérifiez le séparateur ou l'encodage.")

@st.cache_data
def load_data_from_upload(uploaded_file):
    for sep in [';', ',', '\t', '|']:
        try:
            return pd.read_csv(uploaded_file, sep=sep, engine='python')
        except Exception:
            uploaded_file.seek(0)
    raise ValueError("Impossible de lire le fichier uploadé.")

#Détection latitude / longitude
def find_lat_lon_cols(df):
    lat_col, lon_col = None, None

    for c in df.columns:
        cl = c.lower()
        if 'latitude' in cl and lat_col is None:
            lat_col = c
        if 'longitude' in cl and lon_col is None:
            lon_col = c

    #Cas colonne combinée
    if lat_col is None or lon_col is None:
        for c in df.columns:
            cl = c.lower()
            if 'latitude' in cl and 'longitude' in cl:
                non_null = df[c].dropna()
                if non_null.empty:
                    continue  # sécurisation iloc[0]

                sample = str(non_null.iloc[0])
                if ',' in sample:
                    lat_col = c + '_lat'
                    lon_col = c + '_lon'
                    df[lat_col] = (
                        df[c].astype(str)
                        .str.split(',', expand=True)[0]
                        .str.replace('[^0-9+-.]', '', regex=True)
                        .astype(float)
                    )
                    df[lon_col] = (
                        df[c].astype(str)
                        .str.split(',', expand=True)[1]
                        .str.replace('[^0-9+-.]', '', regex=True)
                        .astype(float)
                    )
                break

    # contrôle des bornes
    if lat_col and lon_col:
        df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
        df[lon_col] = pd.to_numeric(df[lon_col], errors='coerce')

        df.loc[~df[lat_col].between(-90, 90), lat_col] = np.nan
        df.loc[~df[lon_col].between(-180, 180), lon_col] = np.nan

    return df, lat_col, lon_col

#Interface Streamlit
st.set_page_config(
    layout='wide',
    page_title="Dashboard – Établissements scolaires (France)",
    initial_sidebar_state='expanded'
)

st.title("Data-story : Établissements du premier et second degré — France")
st.markdown("""
**Objectif :** analyser la répartition géographique et institutionnelle des établissements scolaires en France  
(public / privé, régions, départements).
""")

#Sidebar – chargement
uploaded = st.sidebar.file_uploader("Téléverser un fichier CSV", type=['csv'])
path = st.sidebar.text_input(
    "Chemin local du fichier CSV",
    "fr-en-adresse-et-geolocalisation-etablissements-premier-et-second-degre.csv"
)

# Séparation claire upload / chemin
try:
    if uploaded is not None:
        df = load_data_from_upload(uploaded)
    else:
        df = load_data_from_path(path)
except Exception as e:
    st.error(f"Erreur de chargement : {e}")
    st.stop()

df, lat_col, lon_col = find_lat_lon_cols(df)

#Filtres
st.sidebar.markdown('---')

if 'Libellé de la région' in df.columns:
    regions = sorted(df['Libellé de la région'].dropna().unique())
    selected_regions = st.sidebar.multiselect("Région", regions)
    if selected_regions:
        df = df[df['Libellé de la région'].isin(selected_regions)]

if 'Libellé du département ou de la collectivité' in df.columns:
    deps = sorted(df['Libellé du département ou de la collectivité'].dropna().unique())
    selected_deps = st.sidebar.multiselect("Département", deps)
    if selected_deps:
        df = df[df['Libellé du département ou de la collectivité'].isin(selected_deps)]

if 'Secteur' in df.columns:
    secteurs = sorted(df['Secteur'].dropna().unique())
    selected_secteur = st.sidebar.multiselect("Secteur", secteurs)
    if selected_secteur:
        df = df[df['Secteur'].isin(selected_secteur)]

st.sidebar.markdown(f"**Lignes après filtres : {len(df):,}**")

#KPIs
col1, col2, col3 = st.columns(3)
col1.metric("Nombre d'établissements", f"{len(df):,}")

if 'Secteur' in df.columns and not df['Secteur'].mode().empty:
    col2.metric("Secteur majoritaire", df['Secteur'].mode()[0])

if 'Libellé de la région' in df.columns and not df['Libellé de la région'].mode().empty:
    col3.metric("Région dominante", df['Libellé de la région'].mode()[0])

#Carte

import pydeck as pdk

def secteur_to_color(secteur):
    if pd.isna(secteur):
        return [160, 160, 160]   #gris
    s = secteur.lower()
    if "public" in s:
        return [30, 144, 255]    #bleu
    if "priv" in s:
        return [255, 165, 0]     #orange
    return [160, 160, 160]

st.header("Carte – Répartition géographique")

if lat_col and lon_col:
    df_map = (
        df
        .dropna(subset=[lat_col, lon_col])
        .rename(columns={lat_col: "latitude", lon_col: "longitude"})
    )

    if df_map.empty:
        st.info("Aucun établissement géolocalisé après application des filtres.")
    else:
        #couleur selon secteur
        if "Secteur" in df_map.columns:
            df_map["color"] = df_map["Secteur"].apply(secteur_to_color)
        else:
            df_map["color"] = [[160, 160, 160]] * len(df_map)

        #couche pydeck
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df_map,
            get_position='[longitude, latitude]',
            get_color='color',
            get_radius=90,
            radius_min_pixels=4,
            radius_max_pixels=25,
            pickable=True,
            auto_highlight=True
        )

        tooltip = {
            "html": """
            <b>Commune :</b> {Libellé de la commune}<br/>
            <b>Région :</b> {Libellé de la région}<br/>
            <b>Secteur :</b> {Secteur}<br/>
            <b>Tutelle :</b> {Libellé de la tutelle}
            """,
            "style": {
                "backgroundColor": "black",
                "color": "white",
                "fontSize": "12px"
            }
        }

        view_state = pdk.ViewState(
            latitude=df_map["latitude"].mean(),
            longitude=df_map["longitude"].mean(),
            zoom=5
        )

        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip=tooltip
        )

        st.pydeck_chart(deck)
        st.write(f"Points affichés : {len(df_map):,}")

        #Légende
        st.markdown("""
        **Légende :**
        - 🔵 Établissements publics  
        - 🟠 Établissements privés  
        """)
else:
    st.info("Aucune colonne latitude/longitude valide détectée pour afficher la carte.")


#Explorations
st.header("Explorations")

if 'Libellé de la commune' in df.columns:
    st.subheader("Top 15 des communes")
    st.bar_chart(df['Libellé de la commune'].value_counts().head(15))

if 'Libellé de la tutelle' in df.columns:
    st.subheader("Répartition par tutelle")
    st.bar_chart(df['Libellé de la tutelle'].value_counts().head(20))

#Data-storytelling : analyse écrite
st.markdown("### Analyse")

st.markdown("""
L'analyse met en évidence une forte concentration des établissements scolaires dans les régions les plus densément
peuplées, notamment l'Île-de-France et les grandes métropoles régionales.  
Le secteur public demeure largement majoritaire sur l'ensemble du territoire, tandis que le privé est davantage
présent dans certaines zones urbaines et historiquement favorisées.  

Des disparités territoriales apparaissent clairement : les communes rurales disposent de moins d'établissements,
ce qui peut avoir un impact sur l'accessibilité à l'éducation.  
Ces observations soulignent l'importance de politiques éducatives adaptées aux réalités locales.
""")

#Données & export
st.header("Données brutes")
st.dataframe(df.head(200))

csv = df.to_csv(index=False, sep=';').encode('utf-8')
st.download_button(
    "Télécharger les données filtrées (CSV)",
    csv,
    file_name="etablissements_filtrés.csv",
    mime="text/csv"
)

#Source & licence
st.markdown("---")
st.markdown("""
**Source des données :** Ministère de l'Éducation nationale (data.gouv.fr)""")
